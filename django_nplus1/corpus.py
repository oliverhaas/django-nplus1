import importlib
import json
import linecache
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

from django_nplus1 import detect, signals
from django_nplus1.detect import Listener
from django_nplus1.middleware import DjangoRule
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
        # Skip entries whose model can't be re-imported in this process.
        # Django's migration framework synthesizes transient classes with
        # ``__module__ == '__fake__'`` during pytest-django's DB setup; a
        # worker that captured one of these has nothing the controller can
        # resolve. The same applies to any prefetched class living in a
        # module the controller's environment doesn't load.
        for entry in payload.get("data", []):
            model = _resolve_model_or_none(entry["model"])
            if model is None:
                continue
            site = tuple(entry["site"])
            self.data[(model, entry["field"], site)].update(entry["instances"])
        for entry in payload.get("touched", []):
            model = _resolve_model_or_none(entry["model"])
            if model is None:
                continue
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
    resolved = cast("type", obj)
    _model_resolver_cache[dotted] = resolved
    return resolved


def _resolve_model_or_none(dotted: str) -> type | None:
    try:
        return _resolve_model(dotted)
    except ImportError, AttributeError:
        return None


class CorpusFieldTracker:
    """Session-lifetime accumulator for unused concrete-field detection.

    Same shape as ``CorpusEagerTracker`` but kept separate so the report
    can label finds distinctly and future tuning (e.g. exclude lists)
    does not entangle the two code paths.
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
            model = _resolve_model_or_none(entry["model"])
            if model is None:
                continue
            site = tuple(entry["site"])
            self.data[(model, entry["field"], site)].update(entry["instances"])
        for entry in payload.get("touched", []):
            model = _resolve_model_or_none(entry["model"])
            if model is None:
                continue
            self.touched[(model, entry["field"])].update(entry["instances"])


_corpus_tracker: CorpusEagerTracker | None = None


def get_tracker() -> CorpusEagerTracker:
    """Return the active session tracker, initializing it lazily."""
    global _corpus_tracker  # noqa: PLW0603
    if _corpus_tracker is None:
        _corpus_tracker = CorpusEagerTracker()
    return _corpus_tracker


_corpus_field_tracker: CorpusFieldTracker | None = None


def get_field_tracker() -> CorpusFieldTracker:
    """Return the active session field tracker, initializing it lazily."""
    global _corpus_field_tracker  # noqa: PLW0603
    if _corpus_field_tracker is None:
        _corpus_field_tracker = CorpusFieldTracker()
    return _corpus_field_tracker


_DUMP_PREFIX = ".nplus1-eager-corpus."


def dump_worker(workerid: str) -> None:
    path = Path.cwd() / f"{_DUMP_PREFIX}{workerid}.json"
    payload = {
        "eager": get_tracker().serialize(),
        "field": get_field_tracker().serialize(),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def merge_worker_dumps() -> None:
    cwd = Path.cwd()
    eager_tracker = get_tracker()
    field_tracker = get_field_tracker()
    for path in sorted(cwd.glob(f"{_DUMP_PREFIX}*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "eager" in payload or "field" in payload:
            eager_tracker.merge(payload.get("eager", {}))
            field_tracker.merge(payload.get("field", {}))
        else:
            # Legacy single-tracker payload from a pre-field-detection worker.
            eager_tracker.merge(payload)
        path.unlink(missing_ok=True)


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


class CorpusFieldListener(Listener):
    def setup(self) -> None:
        signals.connect(signals.FIELD_LOAD, self.handle_load)
        signals.connect(signals.FIELD_TOUCH, self.handle_touch)

    def teardown(self) -> None:
        signals.disconnect(signals.FIELD_LOAD, self.handle_load)
        signals.disconnect(signals.FIELD_TOUCH, self.handle_touch)

    def handle_load(
        self,
        args: Any = None,
        kwargs: Any = None,
        context: Any = None,
        ret: Any = None,
        parser: Any = None,
    ) -> None:
        model, field, instances, site = parser(args, kwargs, context)
        if site is None:
            return
        get_field_tracker().record_load(model, field, instances, site)

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
        get_field_tracker().record_touch(model, field, instances)


_corpus_enabled: bool = False


class CorpusContext(DetectionContext):
    """DetectionContext variant that installs CorpusEagerListener and CorpusFieldListener.

    Use when you want a block of test or script code to contribute
    EAGER_LOAD / TOUCH / FIELD_LOAD / FIELD_TOUCH events to the session
    trackers without enabling lazy/get/duplicate detection.
    """

    def __enter__(self) -> CorpusContext:
        self._token = setup_context()
        eager = CorpusEagerListener(self)
        eager.setup()
        self._listeners["eager_load"] = eager
        field = CorpusFieldListener(self)
        field.setup()
        self._listeners["field_load"] = field
        return self

    def notify(self, message: Any) -> None:
        # Corpus listener never calls notify - reports at session end.
        pass


def activate() -> None:
    """Enable corpus mode: swap LISTENERS["eager_load"], register field listener,
    patch DeferredAttribute, reset both trackers.

    Idempotent: a second call is a no-op so accumulated tracker data is
    preserved (for tests that call activate() per-fixture).
    """
    global _corpus_enabled, _corpus_tracker, _corpus_field_tracker  # noqa: PLW0603
    if _corpus_enabled:
        return
    _corpus_enabled = True
    _corpus_tracker = CorpusEagerTracker()
    _corpus_field_tracker = CorpusFieldTracker()
    detect.LISTENERS["eager_load"] = CorpusEagerListener
    detect.LISTENERS["field_load"] = CorpusFieldListener
    from django_nplus1 import fields

    fields._patch_deferred_attribute()


def is_enabled() -> bool:
    return _corpus_enabled


def format_finds(finds: list[tuple[type, str, CallSite]]) -> str:
    if not finds:
        return ""
    lines = [f"django-nplus1: corpus-wide unused_eager_load ({len(finds)} finds)"]
    for model, field, site in finds:
        filename, lineno, funcname = site
        label = f"{model.__name__}.{field}"
        lines.append(f"  {label:30} at {filename}:{lineno} in {funcname}")
    return "\n".join(lines)


_INLINE_CORPUS_IGNORE_RE = re.compile(r"#\s*nplus1:\s*corpus-ignore")


def _is_inline_corpus_ignored(site: CallSite) -> bool:
    filename, lineno, _ = site
    line = linecache.getline(filename, lineno)
    return bool(line) and bool(_INLINE_CORPUS_IGNORE_RE.search(line))


def _whitelist_rules() -> list[DjangoRule]:
    try:
        from django.conf import settings
    except ImportError, AttributeError:
        return []
    data = getattr(settings, "NPLUS1_WHITELIST", [])
    return [DjangoRule(**item) for item in data]


def report() -> list[tuple[type, str, CallSite]]:
    tracker = get_tracker()
    rules = _whitelist_rules()
    result = []
    for model, field, site in tracker.unused():
        if _is_inline_corpus_ignored(site):
            continue
        if any(rule.compare("unused_eager_load", model, field) for rule in rules):
            continue
        result.append((model, field, site))
    return result


def field_report() -> list[tuple[type, str, CallSite]]:
    tracker = get_field_tracker()
    rules = _whitelist_rules()
    result = []
    for model, field, site in tracker.unused():
        if _is_inline_corpus_ignored(site):
            continue
        if any(rule.compare("unused_field_load", model, field) for rule in rules):
            continue
        result.append((model, field, site))
    return result


def format_field_finds(finds: list[tuple[type, str, CallSite]]) -> str:
    if not finds:
        return ""
    lines = [f"django-nplus1: corpus-wide unused_field_load ({len(finds)} finds)"]
    for model, field, site in finds:
        filename, lineno, funcname = site
        label = f"{model.__name__}.{field}"
        lines.append(f"  {label:30} at {filename}:{lineno} in {funcname}")
    return "\n".join(lines)
