import importlib
from collections import defaultdict
from typing import Any

from django_nplus1 import detect, signals
from django_nplus1.detect import Listener
from django_nplus1.scope import DetectionContext
from django_nplus1.signals import setup_context

CallSite = tuple[str, int, str]


class CorpusEagerTracker:
    """Session-lifetime accumulator for unused eager-load detection.

    `data` maps (model, field, call_site) to the set of instance keys ever
    loaded at that declaration site. `touched` maps (model, field) to the
    set of instance keys ever accessed. An entry in `data` is "unused"
    iff none of its instance keys appear in `touched[(model, field)]`.
    """

    def __init__(self) -> None:
        self.data: dict[tuple[type, str, CallSite], set[str]] = defaultdict(set)
        self.touched: dict[tuple[type, str], set[str]] = defaultdict(set)

    def record_load(self, model: type, field: str, instances: list[str], site: CallSite) -> None:
        self.data[(model, field, site)].update(instances)

    def record_touch(self, model: type, field: str, instance_keys: list[str]) -> None:
        self.touched[(model, field)].update(instance_keys)

    def unused(self) -> list[tuple[type, str, CallSite]]:
        result = []
        for (model, field, site), insts in self.data.items():
            if not insts & self.touched.get((model, field), set()):
                result.append((model, field, site))
        return result

    def serialize(self) -> dict[str, Any]:
        return {
            "data": [
                {
                    "model": f"{m.__module__}.{m.__qualname__}",
                    "field": f,
                    "site": list(s),
                    "instances": sorted(insts),
                }
                for (m, f, s), insts in self.data.items()
            ],
            "touched": [
                {
                    "model": f"{m.__module__}.{m.__qualname__}",
                    "field": f,
                    "instances": sorted(insts),
                }
                for (m, f), insts in self.touched.items()
            ],
        }

    def merge(self, payload: dict[str, Any]) -> None:
        for entry in payload.get("data", []):
            model = _resolve_model(entry["model"])
            site = tuple(entry["site"])
            self.data[(model, entry["field"], site)].update(entry["instances"])
        for entry in payload.get("touched", []):
            model = _resolve_model(entry["model"])
            self.touched[(model, entry["field"])].update(entry["instances"])


_model_resolver_cache: dict[str, type] = {}


def _resolve_model(dotted: str) -> type:
    cached = _model_resolver_cache.get(dotted)
    if cached is not None:
        return cached
    module_name, _, qual = dotted.rpartition(".")
    obj: Any = importlib.import_module(module_name)
    for part in qual.split("."):
        obj = getattr(obj, part)
    _model_resolver_cache[dotted] = obj
    return obj


_corpus_tracker: CorpusEagerTracker | None = None


def get_tracker() -> CorpusEagerTracker:
    """Return the active session tracker, initializing it lazily."""
    global _corpus_tracker  # noqa: PLW0603
    if _corpus_tracker is None:
        _corpus_tracker = CorpusEagerTracker()
    return _corpus_tracker


class CorpusEagerListener(Listener):
    def setup(self) -> None:
        signals.connect(signals.EAGER_LOAD, self.handle_eager)
        signals.connect(signals.TOUCH, self.handle_touch)

    def teardown(self) -> None:
        signals.disconnect(signals.EAGER_LOAD, self.handle_eager)
        signals.disconnect(signals.TOUCH, self.handle_touch)

    def handle_eager(
        self,
        args: Any = None,
        kwargs: Any = None,
        context: Any = None,
        ret: Any = None,
        parser: Any = None,
    ) -> None:
        model, field, instances, _key, site = parser(args, kwargs, context)
        if site is None:
            return
        get_tracker().record_load(model, field, instances, site)

    def handle_touch(
        self,
        args: Any = None,
        kwargs: Any = None,
        context: Any = None,
        ret: Any = None,
        parser: Any = None,
    ) -> None:
        parsed = parser(args, kwargs, context)
        if parsed is None:
            return
        model, field, instances = parsed
        get_tracker().record_touch(model, field, instances)


_corpus_enabled: bool = False


class CorpusContext(DetectionContext):
    """DetectionContext variant that installs only CorpusEagerListener.

    Used by the autouse pytest fixture so every test contributes
    EAGER_LOAD/TOUCH events to the session tracker without enabling
    lazy/get/duplicate detection for tests that haven't opted in.
    """

    def __enter__(self) -> CorpusContext:
        self._token = setup_context()
        listener = CorpusEagerListener(self)
        listener.setup()
        self._listeners["eager_load"] = listener
        return self

    def notify(self, message: Any) -> None:
        # Corpus listener never calls notify - reports at session end.
        pass


def activate() -> None:
    """Enable corpus mode: swap LISTENERS["eager_load"] and reset tracker."""
    global _corpus_enabled, _corpus_tracker  # noqa: PLW0603
    _corpus_enabled = True
    _corpus_tracker = CorpusEagerTracker()
    detect.LISTENERS["eager_load"] = CorpusEagerListener


def is_enabled() -> bool:
    return _corpus_enabled
