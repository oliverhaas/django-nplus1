from __future__ import annotations

import fnmatch
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


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
            and (self.field is None or self.field == field),
        )

    def match_model(self, model: type) -> bool:
        if self.model is model:
            return True
        if isinstance(self.model, str):
            return fnmatch.fnmatch(model.__name__, self.model)
        return False


class Message:
    label: str = ""
    formatter: str = ""

    def __init__(self, model: type, field: str) -> None:
        self.model = model
        self.field = field

    @property
    def message(self) -> str:
        return self.formatter.format(
            label=self.label,
            model=self.model.__name__,
            field=self.field,
        )

    def match(self, rules: Sequence[Rule]) -> bool:
        return any(rule.compare(self.label, self.model, self.field) for rule in rules)


class LazyLoadMessage(Message):
    label = "n_plus_one"
    formatter = "Potential n+1 query detected on `{model}.{field}`"


class EagerLoadMessage(Message):
    label = "unused_eager_load"
    formatter = "Potential unnecessary eager load detected on `{model}.{field}`"


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

    def setup(self) -> None:
        from django_nplus1 import signals

        self.loaded = set()
        self.ignore = set()
        signals.connect(signals.LOAD, self.handle_load, sender=signals.get_worker())
        signals.connect(signals.IGNORE_LOAD, self.handle_ignore, sender=signals.get_worker())
        signals.connect(signals.LAZY_LOAD, self.handle_lazy, sender=signals.get_worker())

    def teardown(self) -> None:
        from django_nplus1 import signals

        signals.disconnect(signals.LOAD, self.handle_load, sender=signals.get_worker())
        signals.disconnect(signals.IGNORE_LOAD, self.handle_ignore, sender=signals.get_worker())
        signals.disconnect(signals.LAZY_LOAD, self.handle_lazy, sender=signals.get_worker())

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
            message = LazyLoadMessage(model, field)
            self.parent.notify(message)


class EagerListener(Listener):
    tracker: EagerTracker
    touched: list[tuple[type, str, list[str]] | None]

    def setup(self) -> None:
        from django_nplus1 import signals

        self.tracker = EagerTracker()
        self.touched = []
        signals.connect(signals.EAGER_LOAD, self.handle_eager, sender=signals.get_worker())
        signals.connect(signals.TOUCH, self.handle_touch, sender=signals.get_worker())

    def teardown(self) -> None:
        from django_nplus1 import signals

        self.log_eager()
        signals.disconnect(signals.EAGER_LOAD, self.handle_eager, sender=signals.get_worker())
        signals.disconnect(signals.TOUCH, self.handle_touch, sender=signals.get_worker())

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


LISTENERS: dict[str, type[Listener]] = {
    "lazy_load": LazyListener,
    "eager_load": EagerListener,
}
