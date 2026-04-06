# Django N+1

!!! warning "Exploratory / Alpha"
    This package is under active development and the API may change.

N+1 query detection for Django.

Based on [nplusone](https://github.com/jmcarp/nplusone) by [Joshua Carp](https://github.com/jmcarp), a well-established library for automatic N+1 detection across Python ORMs. If you need broad ORM support (SQLAlchemy, Peewee, etc.), `nplusone` is still the best choice.

Several features (deferred field detection, call-site tracking, `.get()`-in-a-loop detection, `ContextVar`-based async safety, and configurable thresholds) were inspired by [django-zeal](https://github.com/taobojlen/django-zeal) by [Tao Bojlen](https://github.com/taobojlen).

`django-nplus1` is a modernized, Django-only fork that drops legacy compatibility in favour of Python 3.12+ / Django 5.2+, uses a lightweight `ContextVar`-based signal system, and adds unused eager-load detection.

## Features

- **N+1 detection**: Warns when a related object is lazily loaded on an instance that was part of a bulk query
- **Deferred field detection**: Detects N+1 from `.defer()` / `.only()` field access
- **`.get()` in a loop detection**: Detects `Model.objects.get()` called repeatedly from the same call-site
- **Unused eager load detection**: Warns when `select_related` or `prefetch_related` results are never accessed
- **Call-site tracking**: Error messages include the exact file, line number, and function name
- **Async support**: Works with both sync and async Django views
- **Middleware**: Automatically monitors all requests (sync and async)
- **pytest plugin**: `nplus1` fixture and `@pytest.mark.nplus1` marker for test-time detection
- **Profiler**: Context manager for manual use in scripts or tests
- **Whitelisting**: Ignore specific model/field combinations with wildcard support and typo detection
- **`nplus1_allow()`**: Context manager to locally suppress detection for specific code blocks
- **Multiple notification methods**: Logging, exceptions, `warnings.warn_explicit()`, and a Django signal
- **Duplicate query detection**: Optional SQL-level fallback catches N+1 from raw SQL and `.raw()`
- **Configurable threshold**: `NPLUS1_THRESHOLD` controls detection sensitivity
- **Zero dependencies**: Only requires Django

## Quick Start

```bash
pip install django-nplus1
```

```python
INSTALLED_APPS = [
    ...,
    "django_nplus1",
]

MIDDLEWARE = [
    ...,
    "django_nplus1.NPlus1Middleware",
]

# Recommended for test settings
NPLUS1_RAISE = True
```

## Requirements

- Python 3.12+
- Django 5.2+
