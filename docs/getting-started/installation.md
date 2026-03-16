# Installation

## Requirements

- Python 3.12+
- Django 5.2+

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
    "django_nplus1.NPlusOneMiddleware",  # should be last
]
```

The middleware will now log warnings when N+1 queries or unused eager loads are detected.
