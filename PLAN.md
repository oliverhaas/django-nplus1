# django-nplus1 Implementation Plan

## Overview

Modernized, Django-only N+1 query detection. Fork of [nplusone](https://github.com/jmcarp/nplusone) (last updated 2018), stripped of SQLAlchemy/Peewee/WSGI support and rewritten for Python 3.12+ / Django 5.2+.

Tooling and project structure copied from [django-cachex](https://github.com/oliverhaas/django-cachex).

---

## What nplusone Does (Architecture Summary)

nplusone uses a **signal-based monkeypatch architecture**:

1. **`patch.py`** — At import time, monkeypatches Django ORM internals to emit signals when related objects are accessed:
   - `QuerySet._fetch_all` → emits `load` (tracks which instances were loaded in bulk)
   - `QuerySet.get` → emits `ignore_load` (single-object fetches are not N+1)
   - Descriptor `get_queryset` (FK, O2O, M2M) → emits `lazy_load` when fetching related objects
   - `RelatedPopulator.populate` / `prefetch_one_level` → emits `eager_load` for select/prefetch_related
   - Descriptor `__get__` / `QuerySet.__getitem__` → emits `touch` (tracks which eager-loaded relations are actually used)

2. **`signals.py`** — Uses `blinker` library for signal dispatch, with thread-local sender routing.

3. **`listeners.py`** — Two listeners subscribe to signals:
   - **`LazyListener`** — Tracks loaded instances. When a `lazy_load` fires for an instance that was part of a bulk load, it's an N+1. Emits `LazyLoadMessage`.
   - **`EagerListener`** — Tracks eager-loaded relations. At request end, checks which were never `touch`ed. Emits `EagerLoadMessage`.

4. **`middleware.py`** — Django middleware that starts listeners on `process_request` and tears them down on `process_response`. Delegates to notifiers (log or raise).

5. **`notifiers.py`** — `LogNotifier` (logs warnings) and `ErrorNotifier` (raises `NPlusOneError`).

6. **`profiler.py`** — Context manager for use outside middleware (e.g., in tests). Raises on detection.

---

## What Needs Modernizing

### Drop
- `six` dependency (Python 2 compat) — use native Python 3
- `blinker` dependency — replace with simple callbacks or Django signals
- SQLAlchemy, Peewee, Flask, WSGI support — Django only
- Django < 5.2 compat branches (1.8/1.9/1.10 conditionals)
- `django.conf.urls.url` → `django.urls.path`
- `MiddlewareMixin` fallback — modern middleware only
- `inspect.getcallargs` usage — deprecated

### Update
- Django descriptor imports: `related_descriptors` module (stable since Django 1.9, just clean up the import)
- `RelatedPopulator` API — verify still works on Django 5.2/6.0
- `prefetch_one_level` — verify signature hasn't changed
- `create_forward_many_to_many_manager` / `create_reverse_many_to_one_manager` — verify still exist
- Thread safety: `threading.current_thread().ident` approach is fine, just remove blinker indirection

### Add
- **pytest plugin** — nplusone had none. Add a proper pytest plugin with `@pytest.mark.nplus1` and auto-detection fixture
- **Async support** — Django 5.0+ has async views; ensure detection works in async context
- Type hints throughout
- Modern packaging (hatchling, ruff, mypy)

---

## Project Structure

```
django-nplus1/
├── django_nplus1/
│   ├── __init__.py              # Version, public API exports
│   ├── detect.py                # Core detection logic (replaces listeners.py)
│   ├── patch.py                 # Django ORM monkeypatches (modernized from nplusone)
│   ├── middleware.py            # Django middleware
│   ├── signals.py               # Internal signal/callback system (no blinker)
│   ├── notifiers.py             # Log / raise notification backends
│   ├── profiler.py              # Context manager for manual use / tests
│   ├── pytest_plugin.py         # pytest plugin (auto-discovered via entry point)
│   ├── exceptions.py            # NPlusOneError
│   ├── apps.py                  # Django AppConfig
│   └── py.typed                 # PEP 561 marker
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_detect.py           # Core detection unit tests
│   ├── test_middleware.py       # Middleware integration tests
│   ├── test_eager.py            # Unused eager load detection tests
│   ├── test_plugin.py           # pytest plugin tests
│   ├── test_async.py            # Async view detection tests
│   ├── testapp/
│   │   ├── __init__.py
│   │   ├── models.py            # Test models (User, Pet, Allergy, Occupation, etc.)
│   │   ├── views.py             # Test views exercising various query patterns
│   │   └── urls.py
│   └── settings/
│       ├── __init__.py
│       ├── base.py
│       └── urls.py
│
├── docs/
│   ├── index.md
│   ├── getting-started/
│   │   ├── installation.md
│   │   └── quickstart.md
│   ├── user-guide/
│   │   ├── configuration.md
│   │   ├── pytest-plugin.md
│   │   └── whitelisting.md
│   └── reference/
│       ├── api.md
│       └── changelog.md
│
├── .github/workflows/
│   ├── ci.yml
│   ├── publish.yml
│   └── tag.yml
│
├── pyproject.toml
├── .pre-commit-config.yaml
├── mkdocs.yml
├── .gitignore
├── .python-version
├── LICENSE
└── README.md
```

---

## Architecture (Modernized)

### Signal System (replacing blinker)

Replace blinker with a minimal callback registry. No external dependency needed — the signals are purely internal, scoped to the current thread/request.

```python
# signals.py
import threading
from collections import defaultdict
from contextlib import contextmanager

_listeners: dict[str, list[callable]] = defaultdict(list)
_local = threading.local()

def get_worker_id() -> str:
    return str(threading.current_thread().ident)

def connect(signal_name: str, callback: callable) -> None:
    _listeners[signal_name].append(callback)

def disconnect(signal_name: str, callback: callable) -> None:
    _listeners[signal_name].remove(callback)

def send(signal_name: str, **kwargs) -> None:
    for callback in _listeners[signal_name]:
        callback(**kwargs)

@contextmanager
def suppress(signal_name: str):
    """Temporarily disconnect all listeners for a signal."""
    saved = _listeners[signal_name][:]
    _listeners[signal_name].clear()
    try:
        yield
    finally:
        _listeners[signal_name] = saved
```

### Patch Module

Modernized version of nplusone's `patch.py`. Key changes:

- Remove all Django < 1.9 branches — use `related_descriptors` directly
- Remove `six` usage
- Remove `inspect.getcallargs` — use explicit argument capture
- Use our callback system instead of blinker signals
- Keep the same monkeypatching strategy (it's proven and works)

Patches applied at import time (when `django_nplus1` app is ready):

| Django Internal | Signal Emitted | Purpose |
|---|---|---|
| `QuerySet._fetch_all` | `load` | Track instances loaded in bulk |
| `QuerySet.get` | `ignore_load` | Exclude single-object fetches |
| `ForwardManyToOneDescriptor.get_queryset` | `lazy_load` | Detect FK lazy loading |
| `ReverseOneToOneDescriptor.get_queryset` | `lazy_load` | Detect reverse O2O lazy loading |
| `create_reverse_many_to_one_manager` | `lazy_load` | Detect reverse FK lazy loading |
| `create_forward_many_to_many_manager` | `lazy_load` | Detect M2M lazy loading |
| `RelatedPopulator.populate` | `eager_load` | Track select_related usage |
| `prefetch_one_level` | `eager_load` | Track prefetch_related usage |
| Descriptor `__get__` methods | `touch` | Track which eager loads are accessed |
| `QuerySet.__getitem__` | `touch` | Track prefetch indexing |

### Detection Logic

```python
# detect.py

class LazyLoadDetector:
    """Detects N+1: lazy load on an instance that was part of a bulk fetch."""

    def __init__(self):
        self.loaded: set[str] = set()      # instance keys from bulk loads
        self.ignored: set[str] = set()     # instance keys from .get() calls

    def on_load(self, instances: list[str]) -> None:
        self.loaded.update(instances)

    def on_ignore(self, instances: list[str]) -> None:
        self.ignored.update(instances)

    def on_lazy_load(self, model, instance_key: str, field: str) -> Message | None:
        if instance_key in self.loaded and instance_key not in self.ignored:
            return LazyLoadMessage(model, field)
        return None


class EagerLoadDetector:
    """Detects unused eager loads: select/prefetch_related that were never accessed."""

    def __init__(self):
        self.tracked: dict[tuple, dict] = defaultdict(lambda: defaultdict(set))
        self.touched: list[tuple] = []

    def on_eager_load(self, model, field, instances, key) -> None:
        self.tracked[(model, field)][key].update(instances)

    def on_touch(self, model, field, instances) -> None:
        self.touched.append((model, field, instances))

    def get_unused(self) -> list[Message]:
        # Prune touched from tracked, return remaining as EagerLoadMessages
        ...
```

### Middleware

```python
# middleware.py
from django.conf import settings

class NPlusOneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        config = self._load_config()
        detectors = setup_detectors()
        connect_signals(detectors)
        try:
            response = self.get_response(request)
        finally:
            messages = teardown_detectors(detectors)
            disconnect_signals(detectors)
        for message in messages:
            if not message.matches_whitelist(config.whitelist):
                for notifier in config.notifiers:
                    notifier.notify(message)
        return response
```

### pytest Plugin

New feature not in nplusone. Auto-discovered via entry point.

```python
# pytest_plugin.py
import pytest
from django_nplus1.profiler import Profiler

def pytest_configure(config):
    config.addinivalue_line("markers", "nplus1: mark test to detect N+1 queries")

@pytest.fixture
def nplus1():
    """Context manager / fixture that fails on N+1 detection."""
    with Profiler() as p:
        yield p

@pytest.fixture(autouse=False)
def auto_nplus1(request):
    """Auto-detect N+1 in marked tests."""
    marker = request.node.get_closest_marker("nplus1")
    if marker:
        with Profiler(whitelist=marker.kwargs.get("whitelist")):
            yield
    else:
        yield
```

Usage:
```python
@pytest.mark.nplus1
def test_my_view(client):
    client.get("/my-view/")  # fails if N+1 detected

def test_manual(nplus1):
    # use nplus1 fixture directly
    users = list(User.objects.all())
    users[0].profile  # raises NPlusOneError
```

### Profiler (Context Manager)

```python
# profiler.py
class Profiler:
    def __init__(self, whitelist=None):
        self.whitelist = whitelist or []

    def __enter__(self):
        self.detectors = setup_detectors()
        connect_signals(self.detectors)
        return self

    def __exit__(self, *exc):
        messages = teardown_detectors(self.detectors)
        disconnect_signals(self.detectors)
        for message in messages:
            if not message.matches_whitelist(self.whitelist):
                raise NPlusOneError(message.text)
```

---

## Configuration

```python
# settings.py

INSTALLED_APPS = [
    ...,
    "django_nplus1",
]

MIDDLEWARE = [
    ...,
    "django_nplus1.NPlusOneMiddleware",  # should be last
]

# Optional settings
NPLUS1_LOG = True                    # Log warnings (default: True)
NPLUS1_LOG_LEVEL = "WARNING"         # Log level (default: WARNING)
NPLUS1_RAISE = False                 # Raise exceptions (default: False, enable in tests)
NPLUS1_WHITELIST = [                 # Ignore specific patterns
    {"model": "myapp.User", "field": "profile"},
    {"model": "auth.*"},             # Wildcard support
]
```

---

## Build & Tooling (matching django-cachex)

| Tool | Purpose |
|---|---|
| hatchling | Build backend |
| uv | Package manager, lockfile |
| ruff | Linter + formatter (line length 120) |
| mypy + ty | Type checking (django-stubs) |
| pytest | Testing (pytest-django, pytest-cov) |
| pre-commit | Hooks (ruff, mypy, taplo, trailing comma) |
| mkdocs-material | Documentation |
| GitHub Actions | CI matrix, publish |

### Dependencies

- **Required**: Django >=5.2
- **No other runtime dependencies** (blinker and six removed)

### Python / Django Support

- Python: 3.12+
- Django: 5.2, 6.0

---

## Implementation Phases

### Phase 1: Core Detection + Middleware

1. Project skeleton (pyproject.toml, pre-commit, CI, .gitignore, LICENSE, README) — copy from django-cachex
2. `signals.py` — minimal callback system replacing blinker
3. `patch.py` — modernized monkeypatches from nplusone (drop six, old Django branches)
4. `detect.py` — `LazyLoadDetector` + `EagerLoadDetector` (refactored from nplusone's `listeners.py`)
5. `middleware.py` — modern Django middleware (no MiddlewareMixin)
6. `notifiers.py` — log + raise (simplified from nplusone)
7. `exceptions.py` — `NPlusOneError`
8. Test models + views from nplusone's testapp (modernized)
9. Full test suite for N+1 detection (one-to-one, many-to-one, many-to-many, nested, whitelisting)

### Phase 2: pytest Plugin + Profiler

1. `profiler.py` — context manager for non-middleware use
2. `pytest_plugin.py` — `nplus1` fixture + `@pytest.mark.nplus1` marker
3. Entry point registration in pyproject.toml
4. Tests for the plugin itself

### Phase 3: Eager Load Detection

1. Eager load tracking in `detect.py`
2. `select_related` unused detection
3. `prefetch_related` unused detection
4. Nested eager load detection
5. Tests (prefetch used/unused, select used/unused, nested)

### Phase 4: Polish

1. Async view support (verify patches work in async context, add async middleware path if needed)
2. Documentation (mkdocs-material)
3. CI matrix (Python 3.12/3.13/3.14 × Django 5.2/6.0)
4. PyPI publishing workflow

---

## Migration from nplusone

For users switching from nplusone:

```python
# Before (nplusone)
INSTALLED_APPS = [..., "nplusone.ext.django"]
MIDDLEWARE = [..., "nplusone.ext.django.NPlusOneMiddleware"]
NPLUSONE_RAISE = True
NPLUSONE_WHITELIST = [{"model": "myapp.MyModel", "field": "related"}]

# After (django-nplus1)
INSTALLED_APPS = [..., "django_nplus1"]
MIDDLEWARE = [..., "django_nplus1.NPlusOneMiddleware"]
NPLUS1_RAISE = True
NPLUS1_WHITELIST = [{"model": "myapp.MyModel", "field": "related"}]
```

Whitelist format is intentionally kept compatible.
