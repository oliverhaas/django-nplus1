# django-nplus1

> **Exploratory / alpha**: this package is under active development and the API may change.

N+1 query detection for Django.

Based on [nplusone](https://github.com/jmcarp/nplusone) by [Joshua Carp](https://github.com/jmcarp), a well-established library for automatic N+1 detection across Python ORMs. If you need broad ORM support (SQLAlchemy, Peewee, etc.), `nplusone` is still the best choice. I would actually prefer if `nplusone` will in the near future accept some of my PRs which I've tested basically in this package, but I also do not want to wait for it.

Several features (deferred field detection, call-site tracking in error messages, `.get()`-in-a-loop detection, `ContextVar`-based async safety, and configurable thresholds) were inspired by [django-zeal](https://github.com/taobojlen/django-zeal) by [Tao Bojlen](https://github.com/taobojlen).

`django-nplus1` is a modernized, Django-only fork that drops legacy compatibility in favour of Python 3.12+ / Django 5.2+, uses a lightweight `ContextVar`-based signal system, and adds unused eager-load detection.

## Features

- **N+1 detection**: Warns when a related object is lazily loaded on an instance that was part of a bulk query
- **Deferred field detection**: Detects N+1 from `.defer()` / `.only()` field access
- **`.get()` in a loop detection**: Detects `Model.objects.get()` called repeatedly from the same call-site
- **Unused eager load detection**: Warns when `select_related` or `prefetch_related` results are never accessed
- **Call-site tracking**: Error messages include the exact file, line number, and function name
- **Async support**: Works with both sync and async Django views via `ContextVar`-based scoping
- **Middleware**: Automatically monitors all requests (sync and async)
- **pytest plugin**: `nplus1` fixture and `@pytest.mark.nplus1` marker for test-time detection
- **Profiler**: Context manager for manual use in scripts or tests
- **Whitelisting**: Ignore specific model/field combinations with wildcard support and typo detection
- **`nplus1_allow()` context manager**: Locally suppress detection for specific code blocks
- **Multiple notification methods**: Logging, exceptions, `warnings.warn_explicit()`, and a Django signal (`nplus1_detected`)
- **Configurable threshold**: `NPLUS1_THRESHOLD` controls how many repeated accesses trigger detection
- **Zero dependencies**: Only requires Django

## Quick Start

```bash
pip install django-nplus1
```

```python
# settings.py
INSTALLED_APPS = [
    ...,
    "django_nplus1",
]

MIDDLEWARE = [
    ...,
    "django_nplus1.NPlus1Middleware",
]
```

## Recommended Approach

The recommended way to use `django-nplus1` is to have good test coverage and raise on detection in tests:

```python
# settings/test.py
NPLUS1_RAISE = True
```

For existing projects, this will likely surface many N+1 queries at first. Use `nplus1_allow()` to temporarily suppress known issues and fix them incrementally:

```python
from django_nplus1 import nplus1_allow

def my_view(request):
    users = list(User.objects.all())
    with nplus1_allow([{"model": "User", "field": "profile"}]):
        # Known N+1 - TODO: add select_related
        profiles = [u.profile for u in users]
    ...
```

`nplus1_allow()` uses the same whitelist format as `Profiler(whitelist=...)` and `@pytest.mark.nplus1(whitelist=...)`:

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

## Settings

All settings are optional:

```python
NPLUS1_RAISE = True               # Raise NPlus1Error on detection (default: False)
NPLUS1_LOG = True                 # Log warnings on detection (default: True)
NPLUS1_WARN = True                # Emit warnings via warnings.warn_explicit() (default: False)
NPLUS1_THRESHOLD = 2              # Repeated lazy accesses before detection fires (default: 2)
NPLUS1_GET_THRESHOLD = 2          # Repeated .get() calls from same call-site before detection fires (default: 2)
NPLUS1_SHOW_ALL_CALLERS = True    # Include full stack traces in messages (default: False)
NPLUS1_WHITELIST = [              # Global whitelist (supports fnmatch wildcards)
    {"model": "myapp.User", "field": "profile"},
    {"model": "myapp.*"},
]
```

## Documentation

Full documentation at [oliverhaas.github.io/django-nplus1](https://oliverhaas.github.io/django-nplus1/).

## License

MIT
