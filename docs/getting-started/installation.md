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

Add `django_nplus1` to your `INSTALLED_APPS` and the middleware to `MIDDLEWARE`:

```python
# settings.py
INSTALLED_APPS = [
    ...,
    "django_nplus1",
]

MIDDLEWARE = [
    ...,
    "django_nplus1.NPlus1Middleware",  # should be last
]
```

The middleware will now log warnings when N+1 queries or unused eager loads are detected.

## Celery Integration

To detect N+1 queries inside Celery tasks, install the `celery` extra and enable the integration:

```bash
pip install django-nplus1[celery]
```

```python
# settings.py
NPLUS1_CELERY = True
```

Each task execution gets its own detection context, mirroring how the middleware wraps HTTP requests. See [Celery Integration](../reference/api.md#celery-integration) for details.
