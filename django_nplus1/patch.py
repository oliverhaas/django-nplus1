"""Hooks on Django's ORM that report loads and reads to the active detection scope.

Installed once from ``AppConfig.ready()``. Without an active scope every hook runs Django's own code.
"""

import contextlib
import functools
import importlib
import itertools
import operator
import sys
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from asgiref.sync import SyncToAsync
from django.apps import apps
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.models import Model, Prefetch, query
from django.db.models.fields.related_descriptors import (
    ForwardManyToOneDescriptor,
    ReverseOneToOneDescriptor,
    create_forward_many_to_many_manager,
    create_reverse_many_to_one_manager,
)
from django.db.models.query_utils import DeferredAttribute

from django_nplus1 import corpus, signals, util
from django_nplus1.fields import emit_field_loads
from django_nplus1.util import CallSite, get_caller, to_key

if TYPE_CHECKING:
    import types
    from collections.abc import AsyncIterator, Callable, Generator, Iterator, Sequence

# (model, relation name, instance key) of the instance a relation is read on.
Relation = tuple[type[Model], str, str]

# True inside QuerySet._prefetch_related_objects. Prefetching for a queryset of one
# row, as in ``prefetch_related(...).get(pk=x)``, is not an N+1.
_in_queryset_prefetch: ContextVar[bool] = ContextVar("nplus1_in_queryset_prefetch", default=False)

# Id of the running prefetch_related_objects() call. Converging lookups load one row
# twice within a call, which is not an N+1, unlike the same load in every loop pass.
_prefetch_call_id: ContextVar[int | None] = ContextVar("nplus1_prefetch_call_id", default=None)
_prefetch_call_seq = itertools.count()

# The select_related() call sites of the queryset being evaluated, for RelatedPopulator.
_current_select_sites: ContextVar[dict[str, CallSite] | None] = ContextVar(
    "nplus1_current_select_sites",
    default=None,
)

# The select_related() path of the RelatedPopulator being built, e.g. "user__occupation".
_populator_path: ContextVar[str] = ContextVar("nplus1_populator_path", default="")

# The declaration site of the Prefetch whose rows are being fetched.
_prefetch_site: ContextVar[CallSite | None] = ContextVar("nplus1_prefetch_site", default=None)

# True inside prefetch_one_level(). Its relation reads only match rows to instances,
# but a deferred field it reads is still loaded one row at a time.
_in_prefetch_level: ContextVar[bool] = ContextVar("nplus1_in_prefetch_level", default=False)

# The queryset whose rows .iterator() or .aiterator() is fetching. With chunk_size and
# prefetch_related(), Django prefetches for each chunk before it hands out the rows.
_iterating: ContextVar[query.QuerySet[Any] | None] = ContextVar("nplus1_iterating", default=None)

# "relation" or "deferred" while a descriptor loads a value that isn't cached. The
# queries it runs belong to that one lazy load, not to a get() call or an eager load.
_in_descriptor_load: ContextVar[str | None] = ContextVar("nplus1_in_descriptor_load", default=None)

# True while Django opens a connection. Backend setup and connection_created receivers
# (e.g. django.contrib.postgres' type OID lookups) run per connection, not per caller.
_in_connection_setup: ContextVar[bool] = ContextVar("nplus1_in_connection_setup", default=False)

# The rows of one prefetch_one_level() call or one select_related() evaluation form a
# group. Reading the relation on any row of a group marks the group used.
_group_seq = itertools.count()

# Under Django 6.1 fetch modes a read loads one row only through fetch_one().
# FETCH_PEERS loads every peer in one query and FETCH_RAISE loads nothing.
_FETCH_MODES = hasattr(DeferredAttribute, "fetch_one")


@contextlib.contextmanager
def _setting[T](var: ContextVar[T], value: T) -> Generator[None]:
    token = var.set(value)
    try:
        yield
    finally:
        var.reset(token)


def _patch(original: Any, patched: Any) -> None:
    module = importlib.import_module(original.__module__)
    setattr(module, original.__name__, patched)


def _relation(instance: Model, name: str) -> Relation:
    return type(instance), name, to_key(instance)


def _send_lazy(relation: Relation, **context: Any) -> None:
    if _in_prefetch_level.get() and not context.get("deferred"):
        return
    model, name, key = relation
    signals.emit(signals.LAZY_LOAD, model, key, name, **context)


def _send_touch(relation: Relation) -> None:
    model, name, key = relation
    signals.emit(signals.TOUCH, model, name, [key])


def parse_load(args: Any, kwargs: Any, context: Any, ret: Any) -> list[str]:
    return [to_key(row) for row in ret if isinstance(row, Model)]


def parse_get(args: Any, kwargs: Any, context: Any, ret: Any) -> list[str]:
    return [to_key(ret)] if isinstance(ret, Model) else []


def parse_get_call(args: Any, kwargs: Any, context: Any, ret: Any) -> tuple[type[Model], CallSite]:
    return args[0].model, context["caller"]


def is_single(low: int, high: int | None) -> bool:
    return high is not None and high - low == 1


# A relation's querysets carry a "_nplus1_relation" tag, so evaluating one counts as a
# lazy load. Plain data in __dict__ pickles and copies like the rest of the queryset.
def _tag(queryset: Any, instance: Model | None, name: str) -> None:
    # Querysets built inside prefetch_related_objects() belong to the prefetch.
    if instance is not None and signals.active() and _prefetch_call_id.get() is None:
        queryset.__dict__["_nplus1_relation"] = _relation(instance, name)


def _patch_to_one_descriptor(descriptor_cls: Any, cache_owner: Callable[[Any], Any]) -> None:
    """Report reads of a to-one relation: a touch when cached, a lazy load when not."""
    original_get = descriptor_cls.__get__
    original_get_queryset = descriptor_cls.get_queryset

    @functools.wraps(original_get)
    def get(self: Any, instance: Model | None, cls: type | None = None) -> Any:
        if instance is None or not signals.active():
            return original_get(self, instance, cls)
        owner = cache_owner(self)
        if owner.is_cached(instance):
            _send_touch(_relation(instance, owner.cache_name))
            return original_get(self, instance, cls)
        with _setting(_in_descriptor_load, "relation"):
            return original_get(self, instance, cls)

    # Django 6.0 passes the instance as a hint, 6.1 as a keyword-only argument.
    @functools.wraps(original_get_queryset)
    def get_queryset(self: Any, **kwargs: Any) -> Any:
        queryset = original_get_queryset(self, **kwargs)
        _tag(queryset, kwargs.get("instance"), cache_owner(self).cache_name)
        return queryset

    descriptor_cls.__get__ = get
    descriptor_cls.get_queryset = get_queryset


_patch_to_one_descriptor(ForwardManyToOneDescriptor, operator.attrgetter("field"))
_patch_to_one_descriptor(ReverseOneToOneDescriptor, operator.attrgetter("related"))


def _tag_manager(manager_cls: Any, name: str) -> Any:
    original = manager_cls.get_queryset

    @functools.wraps(original)
    def get_queryset(self: Any) -> Any:
        queryset = original(self)
        _tag(queryset, self.instance, name)
        return queryset

    manager_cls.get_queryset = get_queryset
    return manager_cls


def _create_forward_many_to_many_manager(superclass: Any, rel: Any, reverse: bool) -> Any:
    manager_cls = create_forward_many_to_many_manager(superclass, rel, reverse)
    return _tag_manager(manager_cls, rel.get_accessor_name() if reverse else rel.field.name)


def _create_reverse_many_to_one_manager(superclass: Any, rel: Any) -> Any:
    return _tag_manager(create_reverse_many_to_one_manager(superclass, rel), rel.get_accessor_name())


_patch(create_forward_many_to_many_manager, _create_forward_many_to_many_manager)
_patch(create_reverse_many_to_one_manager, _create_reverse_many_to_one_manager)


def _patch_contenttypes() -> None:
    from django.contrib.contenttypes import fields as contenttypes_fields

    create_generic_related_manager = contenttypes_fields.create_generic_related_manager
    generic_foreign_key = contenttypes_fields.GenericForeignKey
    # Django 6.1 moved GenericForeignKey.__get__ to a separate descriptor class.
    descriptor_cls: Any = getattr(contenttypes_fields, "GenericForeignKeyDescriptor", generic_foreign_key)
    original_get = descriptor_cls.__get__

    def _create_generic_related_manager(superclass: Any, rel: Any) -> Any:
        return _tag_manager(create_generic_related_manager(superclass, rel), rel.field.name)

    def has_target(field: Any, instance: Model) -> bool:
        return instance.__dict__.get(field.model._meta.get_field(field.ct_field).attname) is not None

    @functools.wraps(original_get)
    def get(self: Any, instance: Model | None, cls: type | None = None) -> Any:
        if instance is None or not signals.active():
            return original_get(self, instance, cls)
        field = self if isinstance(self, generic_foreign_key) else self.field
        relation = _relation(instance, field.cache_name)
        if field.is_cached(instance):
            _send_touch(relation)
        elif not _FETCH_MODES and has_target(field, instance):
            _send_lazy(relation)
        with _setting(_in_descriptor_load, "relation"):
            return original_get(self, instance, cls)

    _patch(create_generic_related_manager, _create_generic_related_manager)
    descriptor_cls.__get__ = get
    if not _FETCH_MODES:
        return
    original_fetch_one = descriptor_cls.fetch_one

    @functools.wraps(original_fetch_one)
    def fetch_one(self: Any, instance: Model) -> None:
        if signals.active() and has_target(self.field, instance):
            _send_lazy(_relation(instance, self.field.cache_name))
        original_fetch_one(self, instance)

    descriptor_cls.fetch_one = fetch_one


if apps.is_installed("django.contrib.contenttypes"):
    _patch_contenttypes()


_original_clone = query.QuerySet._clone  # type: ignore[attr-defined]


def _clone(self: query.QuerySet[Any]) -> query.QuerySet[Any]:
    clone = _original_clone(self)
    state = self.__dict__
    if "_nplus1_relation" in state:
        clone.__dict__["_nplus1_relation"] = state["_nplus1_relation"]
    # Corpus mode reports unused fields at the line that started the queryset chain.
    if "_nplus1_site" in state:
        clone.__dict__["_nplus1_site"] = state["_nplus1_site"]
    elif corpus.is_enabled():
        clone.__dict__["_nplus1_site"] = get_caller()
    return clone


query.QuerySet._clone = _clone  # type: ignore[attr-defined]


def _send_loads(queryset: query.QuerySet[Any], rows: list[Any]) -> None:
    single = is_single(queryset.query.low_mark, queryset.query.high_mark)
    signals.send(
        signals.IGNORE_LOAD if single else signals.LOAD,
        args=(queryset,),
        kwargs={},
        context={},
        ret=rows,
        parser=parse_load,
    )
    # Rows a descriptor loads on attribute access have no queryset to add .only() to.
    if corpus.is_enabled() and _in_descriptor_load.get() is None:
        instances = [row for row in rows if isinstance(row, Model)]
        if instances:
            site = _prefetch_site.get() or queryset.__dict__.get("_nplus1_site") or get_caller()
            emit_field_loads(instances, site)


_original_fetch_all = query.QuerySet._fetch_all


def _fetch_all(self: query.QuerySet[Any]) -> None:
    if not signals.active():
        _original_fetch_all(self)
        return
    relation = self.__dict__.get("_nplus1_relation")
    if self._result_cache is None:
        if relation is not None:
            _send_lazy(relation)
        iterable: Any = self._iterable_class(self)
        with _setting(_current_select_sites, self.query.__dict__.get("_nplus1_select_sites")):
            rows = list(iterable)
        self._result_cache = rows
        # A prefetch that reads deferred fields of these rows loads them one by one.
        _send_loads(self, rows)
    elif relation is not None and self._prefetch_done:  # type: ignore[attr-defined]
        _send_touch(relation)
    _original_fetch_all(self)


query.QuerySet._fetch_all = _fetch_all  # type: ignore[method-assign]

_original_iterator = query.QuerySet._iterator  # type: ignore[attr-defined]
_END = object()


def _iterator(self: query.QuerySet[Any], use_chunked_fetch: bool, chunk_size: int | None) -> Iterator[Any]:
    rows = _original_iterator(self, use_chunked_fetch, chunk_size)
    if not signals.active():
        yield from rows
        return
    relation = self.__dict__.get("_nplus1_relation")
    if relation is not None:
        _send_lazy(relation)
    sites = self.query.__dict__.get("_nplus1_select_sites")
    try:
        while True:
            with _setting(_current_select_sites, sites), _setting(_iterating, self):
                row = next(rows, _END)
            if row is _END:
                return
            _send_loads(self, [row])
            yield row
    finally:
        rows.close()


query.QuerySet._iterator = _iterator  # type: ignore[attr-defined]

_original_aiterator = query.QuerySet.aiterator


async def _aiterator(self: query.QuerySet[Any], chunk_size: int = 2000) -> AsyncIterator[Any]:
    rows = _original_aiterator(self, chunk_size)
    try:
        if not signals.active():
            async for row in rows:
                yield row
            return
        relation = self.__dict__.get("_nplus1_relation")
        if relation is not None:
            _send_lazy(relation)
        sites = self.query.__dict__.get("_nplus1_select_sites")
        while True:
            with _setting(_current_select_sites, sites), _setting(_iterating, self):
                row = await anext(rows, _END)
            if row is _END:
                return
            _send_loads(self, [row])
            yield row
    finally:
        await rows.aclose()  # type: ignore[attr-defined]


query.QuerySet.aiterator = _aiterator  # type: ignore[method-assign]


def _touching_prefetched(method: Any) -> Any:
    """Count reads that a prefetched relation answers from its cache as touches."""

    @functools.wraps(method)
    def wrapper(self: query.QuerySet[Any], *args: Any, **kwargs: Any) -> Any:
        if self._result_cache is not None and self._prefetch_done:  # type: ignore[attr-defined]
            relation = self.__dict__.get("_nplus1_relation")
            if relation is not None:
                _send_touch(relation)
        return method(self, *args, **kwargs)

    return wrapper


for _name in ("__getitem__", "contains", "count", "exists"):
    setattr(query.QuerySet, _name, _touching_prefetched(getattr(query.QuerySet, _name)))

_original_get = query.QuerySet.get


def _send_get_call(queryset: query.QuerySet[Any], kwargs: dict[str, Any], caller: CallSite | None) -> None:
    if caller is not None:
        signals.send(
            signals.GET_CALL,
            args=(queryset,),
            kwargs=kwargs,
            context={"caller": caller},
            ret=None,
            parser=parse_get_call,
        )


def _get(self: query.QuerySet[Any], *args: Any, **kwargs: Any) -> Any:
    if not signals.active():
        return _original_get(self, *args, **kwargs)
    mode = _in_descriptor_load.get()
    caller = get_caller() if mode is None else None
    try:
        ret = _original_get(self, *args, **kwargs)
    except ObjectDoesNotExist, MultipleObjectsReturned:
        _send_get_call(self, kwargs, caller)
        raise
    # A deferred field load refetches the instance itself; it isn't loaded singly.
    if mode != "deferred":
        signals.send(signals.IGNORE_LOAD, args=(self,), kwargs=kwargs, context={}, ret=ret, parser=parse_get)
    _send_get_call(self, kwargs, caller)
    return ret


query.QuerySet.get = _get  # type: ignore[method-assign]

_original_deferred_get = DeferredAttribute.__get__


def _deferred_get(self: DeferredAttribute, instance: Model | None, cls: type[Model] | None = None) -> Any:
    if instance is None:
        return self
    data = instance.__dict__
    attname = self.field.attname
    if attname in data:
        # Loaded fields only reach __get__ for ForeignKey attnames, or for every field
        # while corpus mode makes DeferredAttribute a data descriptor.
        if corpus.is_enabled() and signals.active():
            signals.emit(signals.FIELD_TOUCH, type(instance), attname, [to_key(instance)])
        return data[attname]
    if not signals.active():
        return _original_deferred_get(self, instance, cls)
    with _setting(_in_descriptor_load, "deferred"):
        return _original_deferred_get(self, instance, cls)


DeferredAttribute.__get__ = _deferred_get  # type: ignore[method-assign]

# deferred=True so LazyListener skips the relation-only ignore set.
if _FETCH_MODES:
    _original_deferred_fetch_one = DeferredAttribute.fetch_one

    def _deferred_fetch_one(self: DeferredAttribute, instance: Model) -> None:
        if signals.active():
            _send_lazy(_relation(instance, self.field.name), deferred=True)
        _original_deferred_fetch_one(self, instance)

    DeferredAttribute.fetch_one = _deferred_fetch_one  # type: ignore[method-assign]
else:
    _original_check_parent_chain = DeferredAttribute._check_parent_chain  # type: ignore[attr-defined]

    def _check_parent_chain(self: DeferredAttribute, instance: Model) -> Any:
        value = _original_check_parent_chain(self, instance)
        if value is None and signals.active():
            _send_lazy(_relation(instance, self.field.name), deferred=True)
        return value

    DeferredAttribute._check_parent_chain = _check_parent_chain  # type: ignore[attr-defined]


class _PrefetchedList(list[Any]):
    """A ``Prefetch(to_attr=...)`` result that reports reads as touches of its relation."""

    __slots__ = ("_nplus1_relation",)

    def __init__(self, values: list[Any], relation: Relation) -> None:
        super().__init__(values)
        self._nplus1_relation = relation

    def __iter__(self) -> Iterator[Any]:
        _send_touch(self._nplus1_relation)
        return super().__iter__()

    def __len__(self) -> int:
        _send_touch(self._nplus1_relation)
        return super().__len__()

    def __getitem__(self, index: Any) -> Any:
        _send_touch(self._nplus1_relation)
        return super().__getitem__(index)

    def __contains__(self, value: object) -> bool:
        _send_touch(self._nplus1_relation)
        return super().__contains__(value)

    def __reversed__(self) -> Iterator[Any]:
        _send_touch(self._nplus1_relation)
        return super().__reversed__()

    def __reduce__(self) -> tuple[type[list[Any]], tuple[list[Any]]]:
        # Copies and pickles come back as plain lists.
        return list, (list.copy(self),)


def _send_prefetch(instances: Sequence[Model], lookup: Prefetch, level: int, site: CallSite | None) -> None:
    to_attr, as_attr = lookup.get_current_to_attr(level)
    if as_attr:
        # Reads of a plain attribute can only be seen through the list stored there. A
        # single related object can't be wrapped, so it isn't tracked.
        wrapped = False
        for instance in instances:
            value = instance.__dict__.get(to_attr)
            if type(value) is list:
                instance.__dict__[to_attr] = _PrefetchedList(value, _relation(instance, to_attr))
                wrapped = True
        if not wrapped:
            return
    signals.emit(
        signals.EAGER_LOAD,
        type(instances[0]),
        to_attr,
        [to_key(instance) for instance in instances],
        next(_group_seq),
        site,
        queryset_prefetch=_in_queryset_prefetch.get(),
        prefetch_call=_prefetch_call_id.get(),
    )


_original_prefetch_one_level = query.prefetch_one_level


def _prefetch_one_level(
    instances: Sequence[Model],
    prefetcher: Any,
    lookup: Prefetch,
    level: int,
) -> tuple[list[Any], list[Prefetch]]:
    if not signals.active():
        return _original_prefetch_one_level(instances, prefetcher, lookup, level)
    site = lookup.__dict__.get("_nplus1_site")
    with _setting(_prefetch_site, site), _setting(_in_prefetch_level, True):
        result = _original_prefetch_one_level(instances, prefetcher, lookup, level)
    # Within a descriptor load this is FETCH_PEERS, not a prefetch_related() that can go unused.
    if _in_descriptor_load.get() is None:
        _send_prefetch(instances, lookup, level, site)
    return result


query.prefetch_one_level = _prefetch_one_level

_original_qs_prefetch_related_objects = query.QuerySet._prefetch_related_objects  # type: ignore[attr-defined]


def _qs_prefetch_related_objects(self: query.QuerySet[Any]) -> None:
    if not signals.active():
        _original_qs_prefetch_related_objects(self)
        return
    with _setting(_in_queryset_prefetch, True):
        _original_qs_prefetch_related_objects(self)


query.QuerySet._prefetch_related_objects = _qs_prefetch_related_objects  # type: ignore[attr-defined]

_original_prefetch_related_objects = query.prefetch_related_objects


def _standalone_prefetch_related_objects(model_instances: Any, *related_lookups: Any) -> None:
    if not signals.active():
        _original_prefetch_related_objects(model_instances, *related_lookups)
        return
    queryset = _iterating.get()
    if queryset is not None and related_lookups == tuple(queryset._prefetch_related_lookups):  # type: ignore[attr-defined]
        # A chunk of .iterator() rows, which are handed out after the prefetch.
        _send_loads(queryset, list(model_instances))
    # Django reads relations while it walks the lookups. Only the caller's reads are touches.
    with (
        _setting(_iterating, None),
        _setting(_prefetch_call_id, next(_prefetch_call_seq)),
        signals.suppress(signals.TOUCH),
    ):
        _original_prefetch_related_objects(model_instances, *related_lookups)


# Patch both the defining module and the public re-export so that
# ``from django.db.models import prefetch_related_objects`` picks up the wrapper.
query.prefetch_related_objects = _standalone_prefetch_related_objects
importlib.import_module("django.db.models").prefetch_related_objects = _standalone_prefetch_related_objects  # type: ignore[attr-defined]


def _replace_stale_prefetch_imports() -> None:
    """Fix stale from-imports captured before AppConfig.ready() ran."""
    for mod in list(sys.modules.values()):
        try:
            if getattr(mod, "prefetch_related_objects", None) is _original_prefetch_related_objects:
                mod.prefetch_related_objects = _standalone_prefetch_related_objects  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001, S110 (third-party __getattr__ can raise anything)
            pass


_replace_stale_prefetch_imports()

_original_populator_init = query.RelatedPopulator.__init__


def _populator_init(self: Any, klass_info: dict[str, Any], *args: Any, **kwargs: Any) -> None:
    if not signals.active():
        _original_populator_init(self, klass_info, *args, **kwargs)
        return
    field = klass_info["field"]
    remote_setter = klass_info["remote_setter"]
    if isinstance(remote_setter, functools.partial):
        # A FilteredRelation row lands in a plain attribute, where reads can't be seen.
        name, lookup = None, remote_setter.args[0]
    elif klass_info["reverse"]:
        name, lookup = field.remote_field.cache_name, field.related_query_name()
    else:
        name = lookup = field.name
    parent = _populator_path.get()
    path = f"{parent}__{lookup}" if parent else lookup
    with _setting(_populator_path, path):
        _original_populator_init(self, klass_info, *args, **kwargs)
    self._nplus1 = (name, path, next(_group_seq), _current_select_sites.get())


query.RelatedPopulator.__init__ = _populator_init  # type: ignore[method-assign]


def _select_site(sites: dict[str, CallSite] | None, path: str) -> CallSite | None:
    if not sites:
        return None
    if path in sites:
        return sites[path]
    # "user" is loaded as part of select_related("user__occupation").
    prefix = f"{path}__"
    return next((site for lookup, site in sites.items() if lookup.startswith(prefix)), None)


_original_populate = query.RelatedPopulator.populate


def _populate(self: Any, row: Any, from_obj: Model) -> None:
    _original_populate(self, row, from_obj)
    state = self.__dict__.get("_nplus1")
    if state is None or state[0] is None:
        return
    name, path, group, sites = state
    site = _select_site(sites, path)
    signals.emit(signals.EAGER_LOAD, type(from_obj), name, [to_key(from_obj)], group, site, select_related=True)


query.RelatedPopulator.populate = _populate  # type: ignore[method-assign]

_original_prefetch_init = Prefetch.__init__


def _prefetch_init(self: Prefetch, *args: Any, **kwargs: Any) -> None:
    _original_prefetch_init(self, *args, **kwargs)
    if corpus.is_enabled():
        self.__dict__["_nplus1_site"] = get_caller()


Prefetch.__init__ = _prefetch_init  # type: ignore[method-assign]

_original_prefetch_related = query.QuerySet.prefetch_related


def _prefetch_related(self: query.QuerySet[Any], *lookups: Any) -> query.QuerySet[Any]:
    if lookups == (None,) or not corpus.is_enabled():
        return _original_prefetch_related(self, *lookups)
    site = get_caller()
    normalized = []
    for lookup in lookups:
        prefetch = lookup if isinstance(lookup, Prefetch) else Prefetch(lookup)
        prefetch.__dict__.setdefault("_nplus1_site", site)
        normalized.append(prefetch)
    return _original_prefetch_related(self, *normalized)


query.QuerySet.prefetch_related = _prefetch_related  # type: ignore[method-assign, assignment]

_original_select_related = query.QuerySet.select_related


def _select_related(self: query.QuerySet[Any], *fields: Any) -> query.QuerySet[Any]:
    queryset = _original_select_related(self, *fields)
    if fields and fields != (None,) and corpus.is_enabled():
        # Copy so the parent queryset's Query keeps its own sites.
        sites = dict(queryset.query.__dict__.get("_nplus1_select_sites") or {})
        sites.update(dict.fromkeys(fields, get_caller()))
        queryset.query.__dict__["_nplus1_select_sites"] = sites
    return queryset


query.QuerySet.select_related = _select_related  # type: ignore[method-assign, assignment]

_original_connect = BaseDatabaseWrapper.connect


@functools.wraps(_original_connect)
def _connect(self: BaseDatabaseWrapper, *args: Any, **kwargs: Any) -> Any:
    with _setting(_in_connection_setup, True):
        return _original_connect(self, *args, **kwargs)


BaseDatabaseWrapper.connect = _connect  # type: ignore[method-assign]


def _dispatch_query(execute: Any, sql: Any, params: Any, many: bool, context: dict[str, Any]) -> Any:
    result = execute(sql, params, many, context)
    if not many and signals.active() and not _in_connection_setup.get():
        signals.emit(signals.QUERY, sql, context)
    return result


def _add_query_hook(connection: BaseDatabaseWrapper) -> None:
    # First in the list is outermost, and connection.execute_wrapper() pops the last.
    if _dispatch_query not in connection.execute_wrappers:
        connection.execute_wrappers.insert(0, _dispatch_query)


_original_wrapper_init = BaseDatabaseWrapper.__init__


@functools.wraps(_original_wrapper_init)
def _wrapper_init(self: BaseDatabaseWrapper, *args: Any, **kwargs: Any) -> None:
    _original_wrapper_init(self, *args, **kwargs)
    _add_query_hook(self)


BaseDatabaseWrapper.__init__ = _wrapper_init  # type: ignore[method-assign]
for _connection in connections.all(initialized_only=True):
    _add_query_hook(_connection)

_original_sync_to_async_call = SyncToAsync.__call__


async def _sync_to_async_call(self: Any, *args: Any, **kwargs: Any) -> Any:
    if not signals.active():
        return await _original_sync_to_async_call(self, *args, **kwargs)
    # Once suspended, a coroutine's frame no longer links to the one awaiting it.
    frames = []
    frame: types.FrameType | None = sys._getframe(1)
    while frame is not None:
        frames.append(frame)
        frame = frame.f_back
    with _setting(util.async_caller_frames, tuple(frames)):
        return await _original_sync_to_async_call(self, *args, **kwargs)


SyncToAsync.__call__ = _sync_to_async_call  # type: ignore[method-assign]
