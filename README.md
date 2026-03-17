# django-nplus1

> **Exploratory / alpha** — this package is under active development and the API may change.

N+1 query detection for Django.

Based on [nplusone](https://github.com/jmcarp/nplusone) by [Joshua Carp](https://github.com/jmcarp), a well-established library for automatic N+1 detection across Python ORMs. If you need broad ORM support (SQLAlchemy, Peewee, etc.), `nplusone` is still the best choice.

`django-nplus1` is a modernized, Django-only fork that drops legacy compatibility in favour of Python 3.12+ / Django 5.2+, replaces blinker with Django's native signal dispatch, and adds unused eager-load detection.

## Features

- **N+1 detection**: Warns when a related object is lazily loaded on an instance that was part of a bulk query
- **Unused eager load detection**: Warns when `select_related` or `prefetch_related` results are never accessed
- **Middleware**: Automatically monitors all requests
- **pytest plugin**: `nplus1` fixture and `@pytest.mark.nplus1` marker for test-time detection
- **Profiler**: Context manager for manual use in scripts or tests
- **Whitelisting**: Ignore specific model/field combinations with wildcard support
- **Zero dependencies**: Only requires Django (no blinker, no six)

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
    "django_nplus1.NPlusOneMiddleware",
]

# Optional
NPLUS1_RAISE = True  # Raise exceptions instead of logging (recommended for tests)
```

## Documentation

Full documentation at [oliverhaas.github.io/django-nplus1](https://oliverhaas.github.io/django-nplus1/).

## License

MIT
