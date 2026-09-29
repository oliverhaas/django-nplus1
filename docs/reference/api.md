# API Reference

## Middleware

### `NPlus1Middleware`

Django middleware that detects N+1 queries and unused eager loads during request processing. Supports both sync and async views.

```python
MIDDLEWARE = [
    ...,
    "django_nplus1.NPlus1Middleware",
]
```

It reads the `NPLUS1_*` settings when Django creates it, so invalid settings and whitelist entries naming unknown models fail at startup. With `NPLUS1_RAISE`, an exception raised by the view wins over a detection made at the end of the request.

## Profiler

### `Profiler`

Context manager for manual N+1 detection. It raises `NPlus1Error` on the first detection.

```python
from django_nplus1 import Profiler

with Profiler(whitelist=None, notifiers=None):
    ...  # Any N+1 queries here raise NPlus1Error
```

**Parameters:**

- `whitelist` (optional): List of dicts, each with any of `model`, `field`, and `label`. A `model` pattern matches the class name (`"User"`) or `"app_label.ModelName"` (`"auth.User"`).
- `notifiers` (optional): Notifiers that run before the raise. `Profiler(notifiers=init(settings))`, with `init` from `django_nplus1.notifiers`, also logs, warns or raises as the `NPLUS1_*` settings say.

## `DetectionContext`

The detection scope that `NPlus1Middleware`, `Profiler` and the Celery integration are built on. Use it to detect N+1 queries in other entry points, such as management commands or message consumers.

```python
from django.conf import settings

from django_nplus1 import DetectionContext
from django_nplus1.notifiers import init

with DetectionContext(notifiers=init(settings), whitelist=[{"model": "auth.User"}]):
    ...
```

**Parameters** (keyword-only, all optional):

- `notifiers`: Objects with a `notify(message)` method, called for each detection.
- `whitelist`: Entries in the same format as `Profiler(whitelist=...)`.
- `sender`: The `sender` of the `nplus1_detected` signal. Default: the scope's class.

Scopes nest. A detection inside an inner scope goes to the notifiers of every enclosing scope, and notifiers built from the same settings report it once. A whitelist entry of any enclosing scope suppresses it. Entering a scope that is already active raises `RuntimeError`.

## `nplus1_allow`

Context manager to locally suppress N+1 detection for specific code blocks. Useful for incrementally adopting detection in existing projects.

```python
from django_nplus1 import nplus1_allow
```

**Usage:**

```python
# Suppress all detections in a block
with nplus1_allow():
    ...

# Suppress a specific model (supports fnmatch wildcards)
with nplus1_allow([{"model": "User"}]):
    ...

# Suppress a specific model/field combination
with nplus1_allow([{"model": "User", "field": "profile"}]):
    ...

# Suppress multiple patterns
with nplus1_allow([{"model": "User", "field": "profile"}, {"model": "Post"}]):
    ...
```

**Parameters:**

- `whitelist` (optional): List of dicts with `model`, `field`, and/or `label` keys. Same format as `Profiler(whitelist=...)` and `@pytest.mark.nplus1(whitelist=...)`. Supports fnmatch wildcards.

Without an argument, every detection in the block is suppressed. An empty list suppresses nothing. Supports nesting: inner `nplus1_allow` calls add to the outer rules; exiting restores the previous state.

An unused eager load is reported when the scope ends, but it is suppressed when the query that loaded it ran inside the block.

Works in every detection scope.

**Note:** `nplus1_allow()` and `Profiler` match a `model` pattern against both the class name (`"User"`) and `"app_label.ModelName"` (`"auth.User"`), so patterns copied from `NPLUS1_WHITELIST` work unchanged.

## Signals

### `nplus1_detected`

Django signal sent once per detection, after whitelist and `nplus1_allow` filtering. Useful for custom reporting (e.g., sending to Sentry).

```python
from django_nplus1 import nplus1_detected


def report_nplus1(sender, message, **kwargs):
    sentry_sdk.capture_message(message.message, level="warning")


nplus1_detected.connect(report_nplus1)
```

**Arguments sent:**

- `sender`: The class of the innermost scope that made the detection: `NPlus1Middleware` for requests, `Profiler` for `Profiler`, the pytest marker and the `nplus1` fixture, and `DetectionContext` for Celery tasks. A `DetectionContext` created with `sender=` sends that value.
- `message`: A `Message` instance with `.model`, `.field`, `.label`, and `.message` attributes. `.caller` is the `(filename, lineno, funcname)` of the line that triggered the detection, or `None` when there is none, as for an unused eager load. With `NPLUS1_SHOW_ALL_CALLERS`, `.callers` holds a stack for each repeated access instead.

## Duplicate Query Detection

The primary detection works at the ORM descriptor level. For raw SQL, `.raw()`, and other paths that bypass the ORM, enable SQL-level duplicate query detection:

```python
NPLUS1_DETECT_DUPLICATE_QUERIES = True
NPLUS1_DUPLICATE_QUERY_THRESHOLD = 2  # default
```

When enabled, every query on every database connection is fingerprinted (literals replaced with `?`), and repeated identical queries from the same call-site are flagged. This works in every detection scope.

The call site is the innermost frame of your code. Frames from the standard library, installed packages, and console-script launchers such as `bin/pytest` don't count. Queries with no frame of your code on the stack aren't counted, nor are queries Django runs while opening a connection (backend setup and `connection_created` receivers such as `django.contrib.postgres`' type lookups).

## Exceptions

### `NPlus1Error`

Raised on a detection by `Profiler`, and by the middleware and Celery tasks when `NPLUS1_RAISE = True` and `NPLUS1_ERROR` names no other class. Also raised at startup when `NPLUS1_WHITELIST` names a model that doesn't exist.

```python
from django_nplus1 import NPlus1Error
```

## Celery Integration

Per-task N+1 detection for Celery workers. Each task run gets its own detection scope, like a request under the middleware.

```bash
pip install django-nplus1[celery]
```

```python
# settings.py
NPLUS1_CELERY = True
```

### `setup_celery_detection()`

Connects the Celery task signals. Called at startup when `NPLUS1_CELERY = True`. Invalid `NPLUS1_*` settings raise here.

```python
from django_nplus1.celery import setup_celery_detection

setup_celery_detection()
```

`teardown_celery_detection()` disconnects them. Call it only while no task runs.

**Limitations:**

- A detection made when a task ends, such as an unused eager load, can't fail the task, because Celery has already recorded its result. It is logged at ERROR level on the `django_nplus1` logger instead.
- When detection can't start for a task, the task runs without it and the error is logged at ERROR level.
- `nplus1_allow()` doesn't reach tasks sent to a worker, because context variables don't travel with the task message. A task run with `.apply()` inside another task or a request nests in that scope, so an enclosing `nplus1_allow()` covers it.

## pytest Plugin

### Fixtures

- `nplus1`: Yields a `Profiler` instance, active from the fixture's setup to its teardown. Test fails on N+1 detection. Applies `NPLUS1_WHITELIST`.

### Markers

- `@pytest.mark.nplus1`: Auto-detect N+1 in the marked test's body. Fixtures run outside the profiler. Applies `NPLUS1_WHITELIST`.
- `@pytest.mark.nplus1(whitelist=[...])`: With extra whitelist entries.

### Options

- `--nplus1-eager-corpus`: Turns on [corpus mode](../user-guide/corpus-mode.md).
