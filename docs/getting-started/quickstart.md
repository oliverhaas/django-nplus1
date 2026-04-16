# Quick Start

## Recommended Setup

After [installation](installation.md), add the middleware to your **test settings**:

```python
# settings/testing.py
MIDDLEWARE = [
    ...,
    "django_nplus1.NPlus1Middleware",
]
NPLUS1_RAISE = True
```

Now any view test that uses the Django test client will fail if an N+1 query is detected:

```python
def test_list_authors(client, authors):
    response = client.get("/authors/")  # raises NPlus1Error if view has N+1
```

### Why test settings?

Testing actual request paths catches real problems in your views. Helper functions or management commands that intentionally defer prefetching to their callers can produce false positives when wrapped in a detection context — testing through the middleware avoids that.

### Adopting in an Existing Project

Introducing django-nplus1 to a project with existing N+1 queries will likely fail many tests at once. Whitelist the known issues and fix them over time:

```python
# settings/testing.py
NPLUS1_WHITELIST = [
    {"model": "myapp.Author", "field": "books"},
    {"model": "myapp.Book", "field": "publisher"},
]
```

See [Whitelisting](../user-guide/whitelisting.md) for the full format including wildcards and `nplus1_allow()`.

## What Gets Detected

### N+1 Queries

```python
# This triggers detection:
users = list(User.objects.all())
for user in users:
    print(user.profile)  # N+1! Each access triggers a separate query

# Fix with select_related:
users = list(User.objects.select_related("profile").all())
for user in users:
    print(user.profile)  # Already loaded
```

### Other Detections

- **Deferred field access**: `.defer()` / `.only()` fields accessed in a loop
- **`.get()` in a loop**: `Model.objects.get()` called repeatedly from the same call-site
- **Unused eager loads**: `select_related` / `prefetch_related` results that are never accessed

## Other Options

The middleware in test settings is the recommended starting point, but django-nplus1 offers other ways to run detection:

### Middleware in All Environments

Add the middleware to your base settings to log warnings during development or production:

```python
# settings.py
MIDDLEWARE = [..., "django_nplus1.NPlus1Middleware"]
```

### pytest Plugin

For per-test control without the middleware:

```python
@pytest.mark.nplus1
def test_my_view(client):
    client.get("/my-view/")  # Fails if N+1 detected
```

See [pytest Plugin](../user-guide/pytest-plugin.md) for details.

### Profiler

For manual use in scripts or tests:

```python
from django_nplus1 import Profiler

with Profiler():
    users = list(User.objects.all())
    users[0].profile  # Raises NPlus1Error
```

## Celery Tasks

The equivalent of the middleware for Celery tasks:

```python
# settings.py (or settings/testing.py)
NPLUS1_CELERY = True
```

Each task gets its own detection context, so N+1 queries inside `task.delay()` or `task.apply()` are reported the same way as in HTTP requests.
