from __future__ import annotations

import copy
import functools
import importlib
from typing import Any

from django.db.models import Model, query
from django.db.models.fields.related_descriptors import (
    ForwardManyToOneDescriptor,
    ReverseOneToOneDescriptor,
    create_forward_many_to_many_manager,
    create_reverse_many_to_one_manager,
)
from django.db.models.query_utils import DeferredAttribute

from django_nplus1 import signals


def to_key(instance: Model) -> str:
    return f"{type(instance).__name__}:{instance.pk}"


def _patch(original: Any, patched: Any) -> None:
    module = importlib.import_module(original.__module__)
    setattr(module, original.__name__, patched)


def signalify_queryset(
    func: Any,
    parser: Any = None,
    **context: Any,
) -> Any:
    @functools.wraps(func)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        queryset = func(*args, **kwargs)
        ctx = copy.copy(context)
        ctx["args"] = context.get("args", args)
        ctx["kwargs"] = context.get("kwargs", kwargs)
        queryset._clone = signalify_queryset(queryset._clone, parser=parser, **ctx)
        queryset._fetch_all = signalify_fetch_all(queryset, parser=parser, **ctx)
        queryset._context = ctx
        return queryset

    return wrapped


def signalify_fetch_all(queryset: Any, parser: Any = None, **context: Any) -> Any:
    func = queryset._fetch_all

    @functools.wraps(func)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if queryset._result_cache is None:
            signals.send(
                signals.LAZY_LOAD,
                args=args,
                kwargs=kwargs,
                ret=None,
                context=context,
                parser=parser,
            )
        return func(*args, **kwargs)

    return wrapped


def get_related_name(model: type[Model]) -> str:
    return f"{model._meta.model_name}_set"


def parse_field(field: Any) -> tuple[type[Model], str]:
    related_model = field.related_model
    name = field.remote_field.name or get_related_name(field.related_model)
    return related_model, name


def parse_reverse_field(field: Any) -> tuple[type[Model], str]:
    return field.model, field.name


def parse_related(context: dict[str, Any]) -> tuple[type[Model], str]:
    field = context["rel_field"]
    model = field.related_model
    related_name = field.remote_field.related_name
    related_model = context["rel_model"]
    return parse_related_parts(model, related_name, related_model)


def parse_related_parts(
    model: type[Model],
    related_name: str | None,
    related_model: type[Model],
) -> tuple[type[Model], str]:
    return (
        model,
        related_name or get_related_name(related_model),
    )


def parse_reverse_one_to_one_queryset(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
) -> tuple[type[Model], str, str]:
    descriptor = context["args"][0]
    field = descriptor.related.field
    model, name = parse_field(field)
    instance = context["kwargs"]["instance"]
    return model, to_key(instance), name


def parse_forward_many_to_one_queryset(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
) -> tuple[type[Model], str, str]:
    descriptor = context["args"][0]
    instance = context["kwargs"]["instance"]
    return descriptor.field.model, to_key(instance), descriptor.field.name


def parse_many_related_queryset(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
) -> tuple[type[Model], str, str]:
    rel = context["rel"]
    manager = context["args"][0]
    model = manager.instance.__class__
    related_model = manager.target_field.related_model
    field = manager.prefetch_cache_name if rel.related_name else None
    return (
        model,
        to_key(manager.instance),
        field or get_related_name(related_model),
    )


def parse_foreign_related_queryset(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
) -> tuple[type[Model], str, str]:
    model, name = parse_related(context)
    descriptor = context["args"][0]
    return model, to_key(descriptor.instance), name


# Suppress lazy_load signals during prefetch_one_level
query.prefetch_one_level = signals.designalify(  # type: ignore[attr-defined]
    signals.LAZY_LOAD,
    query.prefetch_one_level,  # type: ignore[attr-defined]
)


def parse_get(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
    ret: Any,
) -> list[str]:
    return [to_key(ret)] if isinstance(ret, Model) else []


def parse_get_call(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
    ret: Any,
) -> tuple[type[Model], tuple[str, int, str]]:
    qs = args[0]
    caller = context["caller"]
    return qs.model, caller


# Emit IGNORE_LOAD (so LazyListener ignores the instance) and GET_CALL (for loop detection)
_original_get = query.QuerySet.get


def _is_descriptor_call() -> bool:
    """Check if .get() was called from Django's related descriptor machinery.

    Walk from the caller of _get upward. If we reach a Django descriptor
    frame before hitting user code, this is an internal .get() call.
    """
    import sys

    from django_nplus1.util import _is_internal_frame

    # frame(0)=here, frame(1)=_get, frame(2)=caller of _get
    frame = sys._getframe(1).f_back  # caller of _get
    try:
        while frame is not None:
            fn = frame.f_code.co_filename
            if not _is_internal_frame(fn):
                return False
            if "related_descriptors" in fn or "related.py" in fn:
                return True
            frame = frame.f_back
    finally:
        del frame
    return False


def _get(self: Any, *args: Any, **kwargs: Any) -> Any:
    # Short-circuit when no detection context is active (zero overhead in production)
    try:
        signals._listeners.get()
    except LookupError:
        return _original_get(self, *args, **kwargs)

    from django_nplus1.util import get_caller

    direct_call = not _is_descriptor_call()
    caller = get_caller() if direct_call else None
    ret = _original_get(self, *args, **kwargs)
    signals.send(
        signals.IGNORE_LOAD,
        args=(self,),
        kwargs=kwargs,
        ret=ret,
        context={},
        parser=parse_get,
    )
    if direct_call and caller is not None:
        signals.send(
            signals.GET_CALL,
            args=(self,),
            kwargs=kwargs,
            ret=ret,
            context={"caller": caller},
            parser=parse_get_call,
        )
    return ret


query.QuerySet.get = _get  # type: ignore[method-assign]

# Patch descriptor get_queryset methods
ReverseOneToOneDescriptor.get_queryset = signalify_queryset(  # type: ignore[method-assign]
    ReverseOneToOneDescriptor.get_queryset,
    parser=parse_reverse_one_to_one_queryset,
)
ForwardManyToOneDescriptor.get_queryset = signalify_queryset(  # type: ignore[method-assign]
    ForwardManyToOneDescriptor.get_queryset,
    parser=parse_forward_many_to_one_queryset,
)


def _create_forward_many_to_many_manager(superclass: Any, rel: Any, **kwargs: Any) -> Any:
    manager = create_forward_many_to_many_manager(superclass, rel, **kwargs)
    manager.get_queryset = signalify_queryset(  # type: ignore[method-assign]
        manager.get_queryset,
        parser=parse_many_related_queryset,
        rel=rel,
        rel_field=rel.field,
        rel_model=rel.related_model,
    )
    return manager


_patch(create_forward_many_to_many_manager, _create_forward_many_to_many_manager)


def _create_reverse_many_to_one_manager(superclass: Any, rel: Any) -> Any:
    manager = create_reverse_many_to_one_manager(superclass, rel)
    manager.get_queryset = signalify_queryset(  # type: ignore[method-assign]
        manager.get_queryset,
        parser=parse_foreign_related_queryset,
        rel_field=rel.field,
        rel_model=rel.related_model,
    )
    return manager


_patch(create_reverse_many_to_one_manager, _create_reverse_many_to_one_manager)


def parse_forward_many_to_one_get(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
) -> tuple[type[Model], str, list[str]] | None:
    descriptor, instance, *_ = args
    if instance is None:
        return None
    field, model = parse_reverse_field(descriptor.field)
    return field, model, [to_key(instance)]


ForwardManyToOneDescriptor.__get__ = signals.signalify(  # type: ignore[method-assign]
    signals.TOUCH,
    ForwardManyToOneDescriptor.__get__,
    parser=parse_forward_many_to_one_get,
)


def parse_reverse_one_to_one_get(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
) -> tuple[type[Model], str, list[str]] | None:
    descriptor, instance = args[:2]
    if instance is None:
        return None
    model, field = parse_field(descriptor.related.field)
    return model, field, [to_key(instance)]


ReverseOneToOneDescriptor.__get__ = signals.signalify(  # type: ignore[method-assign]
    signals.TOUCH,
    ReverseOneToOneDescriptor.__get__,
    parser=parse_reverse_one_to_one_get,
)


def parse_fetch_all(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
) -> tuple[type[Model], str, list[str]] | None:
    self = args[0]
    if hasattr(self, "_context"):
        manager = self._context["args"][0]
        instance = manager.instance
        if manager.__class__.__name__ == "ManyRelatedManager":
            return (
                instance.__class__,
                parse_manager_field(manager, self._context["rel"]),
                [to_key(instance)],
            )
        model, field = parse_related(self._context)
        return model, field, [to_key(instance)]
    return None


def parse_manager_field(manager: Any, rel: Any) -> str:
    if manager.reverse:
        return rel.related_name or get_related_name(rel.related_model)
    return rel.field.name or get_related_name(rel.model)


def parse_load(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
    ret: Any,
) -> list[str]:
    return [to_key(row) for row in ret if isinstance(row, Model)]


def is_single(low: int, high: int | None) -> bool:
    return high is not None and high - low == 1


# Patch _fetch_all to emit load/ignore_load and touch signals
_original_fetch_all = query.QuerySet._fetch_all


def _fetch_all(self: Any) -> None:
    if self._prefetch_done:
        signals.send(
            signals.TOUCH,
            args=(self,),
            parser=parse_fetch_all,
        )
    _original_fetch_all(self)
    signal = signals.IGNORE_LOAD if is_single(self.query.low_mark, self.query.high_mark) else signals.LOAD
    signals.send(
        signal,
        args=(self,),
        ret=self._result_cache,
        parser=parse_load,
    )


query.QuerySet._fetch_all = _fetch_all  # type: ignore[method-assign]


# Patch RelatedPopulator.__init__ to capture args for eager load parsing
_original_related_populator_init = query.RelatedPopulator.__init__  # type: ignore[attr-defined]


def _related_populator_init(self: Any, *args: Any, **kwargs: Any) -> None:
    _original_related_populator_init(self, *args, **kwargs)
    self.__nplus1__ = {"args": args, "kwargs": kwargs}


query.RelatedPopulator.__init__ = _related_populator_init  # type: ignore[attr-defined]


def parse_eager_select(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
) -> tuple[type[Model], str, list[str], int]:
    populator = args[0]
    instance = args[2]
    meta = populator.__nplus1__
    klass_info, select, *_ = meta["args"]
    field = klass_info["field"]
    model, name = parse_field(field) if instance._meta.model != field.model else parse_reverse_field(field)
    return model, name, [to_key(instance)], id(select)


# Emit eager_load on populating from select_related
query.RelatedPopulator.populate = signals.signalify(  # type: ignore[attr-defined]
    signals.EAGER_LOAD,
    query.RelatedPopulator.populate,  # type: ignore[attr-defined]
    parser=parse_eager_select,
)


def parse_eager_join(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
) -> tuple[type[Model], str, list[str], int]:
    instances, _descriptor, fetcher, level = args
    model = instances[0].__class__
    field, _ = fetcher.get_current_to_attr(level)
    keys = [to_key(instance) for instance in instances]
    return model, field, keys, id(instances)


# Emit eager_load on populating from prefetch_related
query.prefetch_one_level = signals.signalify(  # type: ignore[attr-defined]
    signals.EAGER_LOAD,
    query.prefetch_one_level,  # type: ignore[attr-defined]
    parser=parse_eager_join,
)

# Emit touch on indexing into prefetched QuerySet instances
_original_getitem = query.QuerySet.__getitem__


def _getitem_queryset(self: Any, index: Any) -> Any:
    if self._prefetch_done:
        signals.send(
            signals.TOUCH,
            args=(self,),
            parser=parse_fetch_all,
        )
    return _original_getitem(self, index)


query.QuerySet.__getitem__ = _getitem_queryset  # type: ignore[method-assign]


def parse_deferred_attribute(
    args: Any,
    kwargs: Any,
    context: dict[str, Any],
) -> tuple[type[Model], str, str]:
    self_attr = args[0]  # the DeferredAttribute instance
    instance = args[1]  # the model instance
    return instance.__class__, to_key(instance), self_attr.field.name


# Patch DeferredAttribute._check_parent_chain to emit LAZY_LOAD
_original_check_parent_chain = DeferredAttribute._check_parent_chain  # type: ignore[attr-defined]


def _check_parent_chain(self: Any, instance: Any) -> Any:
    ret = _original_check_parent_chain(self, instance)
    if ret is None:
        # Field is not loaded - Django will fetch it from DB
        signals.send(
            signals.LAZY_LOAD,
            args=(self, instance),
            kwargs={},
            ret=ret,
            context={},
            parser=parse_deferred_attribute,
        )
    return ret


DeferredAttribute._check_parent_chain = _check_parent_chain  # type: ignore[attr-defined]
