# django-nplus1

N+1 query detection for Django.

Detects N+1 queries (lazy loading related objects in a loop) and unused eager loads (`select_related`/`prefetch_related` that are never accessed) in your Django application.

Modernized fork of [nplusone](https://github.com/jmcarp/nplusone), stripped down to Django-only support with Python 3.12+ / Django 5.2+.

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
