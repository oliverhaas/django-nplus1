# API Reference

## Middleware

### `NPlusOneMiddleware`

Django middleware that detects N+1 queries and unused eager loads during request processing.

```python
MIDDLEWARE = [
    ...,
    "django_nplus1.NPlusOneMiddleware",
]
```

## Profiler

### `Profiler`

Context manager for manual N+1 detection.

```python
from django_nplus1 import Profiler

with Profiler(whitelist=None) as p:
    ...  # Any N+1 queries here raise NPlusOneError
```

**Parameters:**

- `whitelist` (optional): List of dicts with `model`, `field`, and/or `label` keys.

## Exceptions

### `NPlusOneError`

Raised when an N+1 query or unused eager load is detected (when `NPLUS1_RAISE=True` or using `Profiler`).

```python
from django_nplus1.exceptions import NPlusOneError
```

## pytest Plugin

### Fixtures

- `nplus1`:Yields a `Profiler` instance. Test fails on N+1 detection.

### Markers

- `@pytest.mark.nplus1`:Auto-detect N+1 in the marked test.
- `@pytest.mark.nplus1(whitelist=[...])`:With whitelisting.
