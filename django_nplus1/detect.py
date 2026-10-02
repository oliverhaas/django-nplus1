import contextlib
import fnmatch
import linecache
import re
from collections import defaultdict
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from django.conf import settings

from django_nplus1 import conf, signals
from django_nplus1.util import get_caller, get_stack

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Sequence

    from django_nplus1.scope import DetectionContext
    from django_nplus1.util import CallSite


def _model_classes(model: type) -> list[type]:
    """Return the model and the models it inherits from: proxy targets, MTI parents, abstract bases."""
    return [cls for cls in model.__mro__ if "_meta" in cls.__dict__] or [model]


class Rule:
    """One whitelist entry. Keys left out match anything, but at least one must be given."""

    def __init__(self, label: str | None = None, model: str | type | None = None, field: str | None = None) -> None:
        self.label = label
        self.model = model
        self.field = field

    def compare(self, label: str, model: type, field: str) -> bool:
        return bool(
            (self.label or self.model or self.field)
            and (self.label is None or self.label == label)
            and (self.model is None or self.match_model(model))
            and (self.field is None or self.match_field(field, label)),
        )

    def match_field(self, field: str, label: str) -> bool:
        pattern = self.field or "*"
        if label == DuplicateQueryMessage.label:
            # Brackets in SQL (quoted identifiers, arrays) are literal, not character classes.
            pattern = pattern.replace("[", "[[]")
        return fnmatch.fnmatch(field, pattern)

    def match_model(self, model: type) -> bool:
        return any(self.match_class(cls) for cls in _model_classes(model))

    def match_class(self, cls: type) -> bool:
        if self.model is cls:
            return True
        if not isinstance(self.model, str):
            return False
        meta = cls.__dict__.get("_meta")
        return fnmatch.fnmatch(cls.__name__, self.model) or (
            meta is not None and fnmatch.fnmatch(meta.label, self.model)
        )


_allow_rules: ContextVar[tuple[Rule, ...]] = ContextVar("nplus1_allow_rules", default=())

_ALLOW_ALL = Rule(model="*")


def is_allowed(message: Message) -> bool:
    """Check if a message is suppressed by an enclosing ``nplus1_allow()``."""
    return message.match(_allow_rules.get())


_INLINE_IGNORE_RE = re.compile(r"#\s*nplus1:\s*ignore(?:\[([^\]]*)\])?")


def _caller_ignores(caller: CallSite, label: str) -> bool:
    filename, lineno, _ = caller
    match = _INLINE_IGNORE_RE.search(linecache.getline(filename, lineno))
    if not match:
        return False
    labels = match.group(1)
    return not labels or label in {part.strip() for part in labels.split(",")}


def is_inline_ignored(message: Message) -> bool:
    """Check for ``# nplus1: ignore`` or ``# nplus1: ignore[label, ...]`` at the detection's call site.

    With ``NPLUS1_SHOW_ALL_CALLERS`` a detection is ignored only when every call site ignores it.
    """
    if message.caller:
        return _caller_ignores(message.caller, message.label)
    sites = [stack[0] for stack in message.callers or () if stack]
    return bool(sites) and all(_caller_ignores(site, message.label) for site in sites)


@contextlib.contextmanager
def nplus1_allow(whitelist: Sequence[dict[str, Any]] | None = None) -> Generator[None]:
    """Suppress detections inside the block.

    Without an argument every detection is suppressed, otherwise only those matching a
    whitelist entry. Entries use the same format as ``Profiler(whitelist=...)``.
    """
    rules = [_ALLOW_ALL] if whitelist is None else [Rule(**item) for item in whitelist]
    token = _allow_rules.set((*_allow_rules.get(), *rules))
    try:
        yield
    finally:
        _allow_rules.reset(token)


class Message:
    label: str = ""
    formatter: str = ""

    def __init__(
        self,
        model: type,
        field: str,
        caller: CallSite | None = None,
        callers: list[list[CallSite]] | None = None,
    ) -> None:
        self.model = model
        self.field = field
        self.caller = caller
        self.callers = callers

    @property
    def message(self) -> str:
        base = self.formatter.format(label=self.label, model=self.model.__name__, field=self.field_text())
        if self.callers:
            parts = [base, " with calls:"]
            for i, stack in enumerate(self.callers, 1):
                parts.append(f"\nCALL {i}:")
                parts.extend(f"\n  {filename}:{lineno} in {funcname}" for filename, lineno, funcname in stack)
            return "".join(parts)
        if self.caller:
            filename, lineno, funcname = self.caller
            return f"{base} at {filename}:{lineno} in {funcname}"
        return base

    def field_text(self) -> str:
        return self.field

    def match(self, rules: Sequence[Rule]) -> bool:
        return any(rule.compare(self.label, self.model, self.field) for rule in rules)


class LazyLoadMessage(Message):
    label = "n_plus_one"
    formatter = "Potential n+1 query detected on `{model}.{field}`"


class EagerLoadMessage(Message):
    label = "unused_eager_load"
    formatter = "Potential unnecessary eager load detected on `{model}.{field}`"


class GetLoopMessage(Message):
    label = "get_in_loop"
    formatter = "Potential n+1 query detected on `{model}.{field}`"


class DuplicateQueryMessage(Message):
    label = "duplicate_query"
    formatter = "Potential n+1 query detected: duplicate query `{field}`"

    def field_text(self) -> str:
        # field keeps the whole query, so a whitelist pattern can match any part of it.
        return _shorten(self.field)


class Listener:
    def __init__(self, parent: DetectionContext) -> None:
        self.parent = parent

    def handlers(self) -> dict[str, Callable[..., None]]:
        return {}

    def setup(self) -> None:
        for signal_name, handler in self.handlers().items():
            signals.connect(signal_name, handler)

    def teardown(self) -> None:
        for signal_name, handler in self.handlers().items():
            signals.disconnect(signal_name, handler)


class LazyListener(Listener):
    """Reports a relation or deferred field loaded one row at a time from a multi-row result."""

    def setup(self) -> None:
        self.threshold = conf.threshold(settings, "NPLUS1_THRESHOLD")
        self.show_all_callers = bool(getattr(settings, "NPLUS1_SHOW_ALL_CALLERS", False))
        self.loaded: set[str] = set()
        self.ignore: set[str] = set()
        self.rows: defaultdict[tuple[type, str], set[str]] = defaultdict(set)
        self.stacks: defaultdict[tuple[type, str], list[list[CallSite]]] = defaultdict(list)
        self.reported: set[tuple[type, str]] = set()
        self.prefetch_calls: dict[tuple[type, str], int | None] = {}
        super().setup()

    def handlers(self) -> dict[str, Callable[..., None]]:
        return {
            signals.LOAD: self.handle_load,
            signals.IGNORE_LOAD: self.handle_ignore,
            signals.LAZY_LOAD: self.handle_lazy,
            signals.EAGER_LOAD: self.handle_eager,
        }

    def handle_load(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        keys = parser(args, kwargs, context, ret)
        self.loaded.update(keys)
        # Rows fetched on their own before are now part of a larger result.
        self.ignore.difference_update(keys)

    def handle_ignore(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        self.ignore.update(parser(args, kwargs, context, ret))

    def handle_lazy(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        model, key, field = parser(args, kwargs, context)
        owner = self.owner(key, deferred=bool(context.get("deferred")))
        if owner is not None:
            self.hit(model, field, key, owner)

    def handle_eager(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        # Prefetching for one row of a larger result, once per loop pass, is an N+1 too.
        if context.get("select_related") or context.get("queryset_prefetch"):
            return
        model, field, keys, _group, _site = parser(args, kwargs, context)
        owner = self.owner(keys[0]) if len(keys) == 1 else None
        if owner is None:
            return
        call = context.get("prefetch_call")
        if call is not None and owner.prefetch_calls.get((model, field)) == call:
            return
        owner.prefetch_calls[(model, field)] = call
        self.hit(model, field, keys[0], owner)

    def owner(self, key: str, *, deferred: bool = False) -> LazyListener | None:
        """Return the listener of the innermost scope that loaded the row as part of a larger result.

        None if no scope did, or if a relation is read on a row that was fetched on its
        own since. Deferred fields still load in a query per row on such a row.
        """
        listener: LazyListener | None = self
        while listener is not None:
            if not deferred and key in listener.ignore:
                return None
            if key in listener.loaded:
                return listener
            listener = listener.parent.outer_listener(LazyListener)
        return None

    def hit(self, model: type, field: str, row: str, owner: LazyListener) -> None:
        """Count a read of a row that ``owner``'s scope loaded, and report it through this scope.

        Each row counts once, so reading one row again through another instance is no N+1.
        """
        key = (model, field)
        if key in owner.reported or row in owner.rows[key]:
            return
        # Rules need no call site, so check them before walking the stack.
        message = LazyLoadMessage(model, field)
        if self.parent.suppresses(message):
            return
        message.caller = get_caller()
        if is_inline_ignored(message):
            return
        owner.rows[key].add(row)
        if owner.show_all_callers:
            owner.stacks[key].append(get_stack())
        if len(owner.rows[key]) < owner.threshold:
            return
        owner.reported.add(key)
        if owner.show_all_callers:
            message = LazyLoadMessage(model, field, callers=owner.stacks.pop(key))
        self.parent.notify(message)


class EagerListener(Listener):
    """Reports eager loads whose rows never had the relation read before the scope ended."""

    def setup(self) -> None:
        # (model, field) -> group -> (row keys, declaration site). A read of any row
        # of a group uses the group.
        self.groups: defaultdict[tuple[type, str], dict[int, tuple[set[str], CallSite | None]]] = defaultdict(dict)
        # Groups that were read or are allowed. .iterator() adds rows to a group after
        # the loop has read earlier ones.
        self.settled: set[int] = set()
        super().setup()

    def handlers(self) -> dict[str, Callable[..., None]]:
        return {signals.EAGER_LOAD: self.handle_eager, signals.TOUCH: self.handle_touch}

    def teardown(self) -> None:
        super().teardown()
        # A failed block can end before it reads its eager loads.
        if self.parent.failed:
            return
        for (model, field), groups in self.groups.items():
            if groups:
                _keys, site = next(iter(groups.values()))
                self.parent.notify(EagerLoadMessage(model, field, caller=site))

    def handle_eager(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        model, field, keys, group, site = parser(args, kwargs, context)
        if group in self.settled:
            return
        groups = self.groups[(model, field)]
        entry = groups.get(group)
        if entry is not None:
            entry[0].update(keys)
        elif is_allowed(EagerLoadMessage(model, field)):
            self.settled.add(group)
        else:
            groups[group] = (set(keys), site)

    def handle_touch(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        model, field, keys = parser(args, kwargs, context)
        groups = self.groups.get((model, field))
        if not groups:
            return
        for group, (loaded, _site) in list(groups.items()):
            if not loaded.isdisjoint(keys):
                del groups[group]
                self.settled.add(group)


class GetLoopListener(Listener):
    """Reports ``Model.objects.get()`` reached repeatedly from the same line through the same calls."""

    def setup(self) -> None:
        self.threshold = conf.threshold(settings, "NPLUS1_GET_THRESHOLD")
        self.counts: defaultdict[tuple[Any, ...], int] = defaultdict(int)
        self.reported: set[tuple[Any, ...]] = set()
        super().setup()

    def handlers(self) -> dict[str, Callable[..., None]]:
        return {signals.GET_CALL: self.handle_get}

    def handle_get(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        model, caller, path = parser(args, kwargs, context, ret)
        site = (model, *caller)
        if site in self.reported:
            return
        message = GetLoopMessage(model, "get()", caller=caller)
        if self.parent.suppresses(message):
            return
        key = (model, path)
        self.counts[key] += 1
        if self.counts[key] >= self.threshold:
            self.reported.add(site)
            self.parent.notify(message)


class _SQL:
    """Stands in for the model of a duplicate query."""


_SQL_LITERAL_RE = re.compile(r"'(?:[^']|'')*'|\b\d+\b")

_SHORT_SQL_LENGTH = 120


def _sql_text(sql: Any, context: dict[str, Any]) -> str:
    if isinstance(sql, str):
        return sql
    if isinstance(sql, bytes):
        return sql.decode(errors="replace")
    try:
        # psycopg's sql.Composed renders against the cursor's connection.
        return sql.as_string(context["cursor"].cursor)
    except Exception:  # noqa: BLE001
        return str(sql)


def _fingerprint_sql(sql: str) -> str:
    """Normalize a SQL query by replacing literals with ?, collapsing whitespace."""
    return " ".join(_SQL_LITERAL_RE.sub("?", sql).split())


def _shorten(sql: str) -> str:
    if len(sql) <= _SHORT_SQL_LENGTH:
        return sql
    return sql[: _SHORT_SQL_LENGTH - 3] + "..."


class DuplicateQueryListener(Listener):
    """Reports the same SQL run repeatedly from the same line, which also covers ``.raw()`` and cursor SQL."""

    def setup(self) -> None:
        self.enabled = bool(getattr(settings, "NPLUS1_DETECT_DUPLICATE_QUERIES", False))
        if not self.enabled:
            return
        self.threshold = conf.threshold(settings, "NPLUS1_DUPLICATE_QUERY_THRESHOLD")
        self.counts: defaultdict[tuple[str, str, int, str], int] = defaultdict(int)
        self.reported: set[tuple[str, str, int, str]] = set()
        super().setup()

    def teardown(self) -> None:
        if self.enabled:
            super().teardown()

    def handlers(self) -> dict[str, Callable[..., None]]:
        return {signals.QUERY: self.handle_query}

    def handle_query(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        sql, query_context = parser(args, kwargs, context)
        # Without a project frame there is no call site to count per.
        caller = get_caller()
        if caller is None:
            return
        fingerprint = _fingerprint_sql(_sql_text(sql, query_context))
        key = (fingerprint, *caller)
        if key in self.reported:
            return
        message = DuplicateQueryMessage(_SQL, fingerprint, caller=caller)
        if self.parent.suppresses(message):
            return
        self.counts[key] += 1
        if self.counts[key] >= self.threshold:
            self.reported.add(key)
            self.parent.notify(message)


LISTENERS: dict[str, type[Listener]] = {
    "lazy_load": LazyListener,
    "eager_load": EagerListener,
    "get_loop": GetLoopListener,
    "duplicate_query": DuplicateQueryListener,
}
