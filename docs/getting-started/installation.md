# Installation

## Requirements

- Python 3.14+
- Django 6+

## Install

```bash
pip install django-nplus1
```

Or with uv:

```bash
uv add django-nplus1
```

## Setup

Add `django_nplus1` to your `INSTALLED_APPS`:

```python
# settings.py
INSTALLED_APPS = [
    ...,
    "django_nplus1",
]
```

Then add the middleware to your **test settings** and enable raising on detection:

```python
# settings/testing.py
MIDDLEWARE = [
    ...,
    "django_nplus1.NPlus1Middleware",  # should be last
]
NPLUS1_RAISE = True
```

This way every view test that uses the Django test client will fail if an N+1 query is detected. Testing actual request paths catches real problems without false positives from helper functions that intentionally defer prefetching to their callers.

For existing projects, introducing django-nplus1 will likely surface many N+1 queries at once. Whitelist the known issues and fix them over time:

```python
# settings/testing.py
NPLUS1_WHITELIST = [
    {"model": "myapp.Author", "field": "books"},
    {"model": "myapp.Book", "field": "publisher"},
]
```

See [Whitelisting](../user-guide/whitelisting.md) for the full whitelist format.

### Other options

The middleware can also be added to your base or development settings to log warnings during normal use. For more granular control, see the [pytest plugin](../user-guide/pytest-plugin.md) (`@pytest.mark.nplus1` marker) and the [Profiler](../reference/api.md#profiler) context manager.

## Celery Integration

The equivalent of the middleware for Celery tasks. Install the `celery` extra and enable the integration:

```bash
pip install django-nplus1[celery]
```

```python
# settings.py (or settings/testing.py)
NPLUS1_CELERY = True
```

Each task execution gets its own detection context, mirroring how the middleware wraps HTTP requests. See [Celery Integration](../reference/api.md#celery-integration) for details.
