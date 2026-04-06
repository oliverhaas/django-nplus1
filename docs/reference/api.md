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

## Profiler

### `Profiler`

Context manager for manual N+1 detection.

```python
from django_nplus1 import Profiler

with Profiler(whitelist=None) as p:
    ...  # Any N+1 queries here raise NPlus1Error
```

**Parameters:**

- `whitelist` (optional): List of dicts with `model`, `field`, and/or `label` keys.

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

With no arguments, all detections are suppressed within the block. Supports nesting: inner `nplus1_allow` calls add to the outer rules; exiting restores the previous state.

Works in both middleware and profiler contexts.

## Signals

### `nplus1_detected`

Django signal emitted on every detection (after whitelist and `nplus1_allow` filtering). Useful for custom reporting (e.g., sending to Sentry).

```python
from django_nplus1 import nplus1_detected

def report_nplus1(sender, message, **kwargs):
    sentry_sdk.capture_message(message.message, level="warning")

nplus1_detected.connect(report_nplus1)
```

**Arguments sent:**

- `sender`: `NPlus1Middleware` (function) or `Profiler` (class)
- `message`: A `Message` instance with `.model`, `.field`, `.label`, and `.message` attributes

## Exceptions

### `NPlus1Error`

Raised when an N+1 query or unused eager load is detected (when `NPLUS1_RAISE=True` or using `Profiler`).

```python
from django_nplus1.exceptions import NPlus1Error
```

## pytest Plugin

### Fixtures

- `nplus1`: Yields a `Profiler` instance. Test fails on N+1 detection.

### Markers

- `@pytest.mark.nplus1`: Auto-detect N+1 in the marked test.
- `@pytest.mark.nplus1(whitelist=[...])`: With whitelisting.
