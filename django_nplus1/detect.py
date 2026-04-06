from __future__ import annotations

import contextlib
import fnmatch
from collections import defaultdict
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence


class Rule:
    def __init__(self, label: str | None = None, model: str | type | None = None, field: str | None = None) -> None:
        self.label = label
        self.model = model
        self.field = field

    def compare(self, label: str, model: type, field: str) -> bool:
        return bool(
            (self.label or self.model or self.field)
            and (self.label is None or self.label == label)
            and (self.model is None or self.match_model(model))
            and (self.field is None or self.match_field(field)),
        )

    def match_field(self, field: str) -> bool:
        if self.field is None:
            return True
        return fnmatch.fnmatch(field, self.field)

    def match_model(self, model: type) -> bool:
        if self.model is model:
            return True
        if isinstance(self.model, str):
            return fnmatch.fnmatch(model.__name__, self.model)
        return False


_allow_rules: ContextVar[list[Rule]] = ContextVar("nplus1_allow_rules")


def is_allowed(message: Message) -> bool:
    """Check if a message is suppressed by nplus1_allow rules."""
    try:
        rules = _allow_rules.get()
    except LookupError:
        return False
    return message.match(rules) if rules else False


@contextlib.contextmanager
def nplus1_allow(whitelist: list[dict[str, Any]] | None = None) -> Generator[None]:
    """Context manager to suppress N+1 detection for specific model/field combinations.

    With no arguments, suppresses all detections. With a whitelist, suppresses only
    matching detections. Uses the same format as ``Profiler(whitelist=...)`` and
    ``@pytest.mark.nplus1(whitelist=...)``.

    Usage::

        # Suppress all detections
        with nplus1_allow():
            ...

        # Suppress specific model/field
        with nplus1_allow([{"model": "User", "field": "hobbies"}]):
            ...

        # Suppress all fields on a model (supports fnmatch wildcards)
        with nplus1_allow([{"model": "User"}]):
            ...
    """
    rules = [Rule(**item) for item in whitelist] if whitelist else [Rule(model="*", field="*")]

    try:
        current = _allow_rules.get()
    except LookupError:
        current = []
    token = _allow_rules.set([*current, *rules])
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
        caller: tuple[str, int, str] | None = None,
        callers: list[list[tuple[str, int, str]]] | None = None,
    ) -> None:
        self.model = model
        self.field = field
        self.caller = caller
        self.callers = callers

    @property
    def message(self) -> str:
        base = self.formatter.format(
            label=self.label,
            model=self.model.__name__,
            field=self.field,
        )
        if self.callers:
            parts = [base, " with calls:"]
            for i, stack in enumerate(self.callers, 1):
                parts.append(f"\nCALL {i}:")
                for fn, lineno, funcname in stack:
                    parts.append(f"\n  {fn}:{lineno} in {funcname}")
            return "".join(parts)
        if self.caller:
            filename, lineno, funcname = self.caller
            return f"{base} at {filename}:{lineno} in {funcname}"
        return base

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


class Listener:
    def __init__(self, parent: Any) -> None:
        self.parent = parent

    def setup(self) -> None:
        pass

    def teardown(self) -> None:
        pass


class LazyListener(Listener):
    loaded: set[str]
    ignore: set[str]
    counts: defaultdict[tuple[type, str], int]
    show_all_callers: bool
    call_stacks: defaultdict[tuple[type, str], list[list[tuple[str, int, str]]]]

    def setup(self) -> None:
        from django.conf import settings

        from django_nplus1 import signals

        self.loaded = set()
        self.ignore = set()
        self.counts = defaultdict(int)
        self.threshold = getattr(settings, "NPLUS1_THRESHOLD", 2)
        self.show_all_callers = getattr(settings, "NPLUS1_SHOW_ALL_CALLERS", False)
        self.call_stacks = defaultdict(list)
        signals.connect(signals.LOAD, self.handle_load)
        signals.connect(signals.IGNORE_LOAD, self.handle_ignore)
        signals.connect(signals.LAZY_LOAD, self.handle_lazy)
        signals.connect(signals.EAGER_LOAD, self.handle_eager)

    def teardown(self) -> None:
        from django_nplus1 import signals

        signals.disconnect(signals.LOAD, self.handle_load)
        signals.disconnect(signals.IGNORE_LOAD, self.handle_ignore)
        signals.disconnect(signals.LAZY_LOAD, self.handle_lazy)
        signals.disconnect(signals.EAGER_LOAD, self.handle_eager)

    def handle_load(
        self,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        ret: Any = None,
        parser: Any = None,
    ) -> None:
        instances = parser(args, kwargs, context, ret)
        self.loaded.update(instances)

    def handle_ignore(
        self,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        ret: Any = None,
        parser: Any = None,
    ) -> None:
        instances = parser(args, kwargs, context, ret)
        self.ignore.update(instances)

    def handle_lazy(
        self,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        ret: Any = None,
        parser: Any = None,
    ) -> None:
        model, instance, field = parser(args, kwargs, context)
        if instance in self.loaded and instance not in self.ignore:
            key = (model, field)
            self.counts[key] += 1
            if self.show_all_callers:
                from django_nplus1.util import get_stack

                self.call_stacks[key].append(get_stack())
            if self.counts[key] == self.threshold:
                if self.show_all_callers:
                    message = LazyLoadMessage(model, field, callers=self.call_stacks[key])
                else:
                    from django_nplus1.util import get_caller

                    caller = get_caller()
                    message = LazyLoadMessage(model, field, caller=caller)
                self.parent.notify(message)

    def handle_eager(
        self,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        ret: Any = None,
        parser: Any = None,
    ) -> None:
        model, field, keys, _key = parser(args, kwargs, context)
        if len(keys) == 1 and keys[0] in self.loaded and keys[0] not in self.ignore:
            key = (model, field)
            self.counts[key] += 1
            if self.show_all_callers:
                from django_nplus1.util import get_stack

                self.call_stacks[key].append(get_stack())
            if self.counts[key] == self.threshold:
                if self.show_all_callers:
                    message = LazyLoadMessage(model, field, callers=self.call_stacks[key])
                else:
                    from django_nplus1.util import get_caller

                    caller = get_caller()
                    message = LazyLoadMessage(model, field, caller=caller)
                self.parent.notify(message)


class EagerListener(Listener):
    tracker: EagerTracker
    touched: list[tuple[type, str, list[str]] | None]

    def setup(self) -> None:
        from django_nplus1 import signals

        self.tracker = EagerTracker()
        self.touched = []
        signals.connect(signals.EAGER_LOAD, self.handle_eager)
        signals.connect(signals.TOUCH, self.handle_touch)

    def teardown(self) -> None:
        from django_nplus1 import signals

        self.log_eager()
        signals.disconnect(signals.EAGER_LOAD, self.handle_eager)
        signals.disconnect(signals.TOUCH, self.handle_touch)

    def handle_eager(
        self,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        ret: Any = None,
        parser: Any = None,
    ) -> None:
        self.tracker.track(*parser(args, kwargs, context))

    def handle_touch(
        self,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        ret: Any = None,
        parser: Any = None,
    ) -> None:
        self.touched.append(parser(args, kwargs, context))

    def log_eager(self) -> None:
        self.tracker.prune([each for each in self.touched if each])
        for model, field in self.tracker.unused:
            message = EagerLoadMessage(model, field)
            self.parent.notify(message)


class EagerTracker:
    def __init__(self) -> None:
        self.data: defaultdict[tuple[type, str], defaultdict[int, set[str]]] = defaultdict(
            lambda: defaultdict(set),
        )

    def track(self, model: type, field: str, instances: list[str], key: int) -> None:
        self.data[(model, field)][key].update(instances)

    def prune(self, touched: list[tuple[type, str, list[str]]]) -> None:
        for model, field, touch_instances in touched:
            group = self.data[(model, field)]
            for key, fetch_instances in list(group.items()):
                if touch_instances and fetch_instances.intersection(touch_instances):
                    group.pop(key, None)

    @property
    def unused(self) -> list[tuple[type, str]]:
        return [(model, field) for (model, field), group in self.data.items() if group]


class GetLoopListener(Listener):
    """Detects Model.objects.get() called repeatedly from the same call-site."""

    counts: defaultdict[tuple[Any, ...], int]

    def setup(self) -> None:
        from django.conf import settings

        from django_nplus1 import signals

        self.counts = defaultdict(int)
        self.threshold = getattr(settings, "NPLUS1_GET_THRESHOLD", 2)
        signals.connect(signals.GET_CALL, self.handle_get)

    def teardown(self) -> None:
        from django_nplus1 import signals

        signals.disconnect(signals.GET_CALL, self.handle_get)

    def handle_get(
        self,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        ret: Any = None,
        parser: Any = None,
    ) -> None:
        model, caller = parser(args, kwargs, context, ret)
        key = (model, *caller)
        self.counts[key] += 1
        if self.counts[key] == self.threshold:
            message = GetLoopMessage(model, "get()", caller=caller)
            self.parent.notify(message)


LISTENERS: dict[str, type[Listener]] = {
    "lazy_load": LazyListener,
    "eager_load": EagerListener,
    "get_loop": GetLoopListener,
}
