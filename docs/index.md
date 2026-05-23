# Django N+1

!!! note "Beta"
    This package is under active development and the API may change before 1.0.

N+1 query detection for Django.

Based on [nplusone](https://github.com/jmcarp/nplusone) by [Joshua Carp](https://github.com/jmcarp), a well-established library for automatic N+1 detection across Python ORMs. If you need broad ORM support (SQLAlchemy, Peewee, etc.), `nplusone` is still the best choice.

Several features (deferred field detection, call-site tracking, `.get()`-in-a-loop detection, `ContextVar`-based async safety, and configurable thresholds) were inspired by [django-zeal](https://github.com/taobojlen/django-zeal) by [Tao Bojlen](https://github.com/taobojlen).

`django-nplus1` is a Django-only fork that drops legacy compatibility in favour of Python 3.14+ / Django 6+, uses a `ContextVar`-based signal system, and adds unused eager-load detection.

## Features

Detects:

- Lazy loads on bulk-fetched rows (N+1)
- Deferred-field access from `.defer()` / `.only()`
- `Model.objects.get()` repeated in a loop
- Unused `select_related` / `prefetch_related`
- Duplicate raw SQL (opt-in via `NPLUS1_DETECT_DUPLICATE_QUERIES`)

Activates via:

- Middleware (sync and async)
- pytest plugin (`nplus1` fixture and `@pytest.mark.nplus1` marker)
- Celery `task_prerun`/`task_postrun` signals
- `Profiler` context manager

Suppression:

- Wildcard whitelist with typo detection
- `# nplus1: ignore` inline comments
- `nplus1_allow()` context manager

Reports via logging, exceptions, `warnings.warn_explicit()`, and a Django signal. Messages include file, line, and function. Threshold tunable via `NPLUS1_THRESHOLD`. Only depends on Django.

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
```

```python
# settings/testing.py
MIDDLEWARE = [
    ...,
    "django_nplus1.NPlus1Middleware",
]
NPLUS1_RAISE = True
```

Adding the middleware to your test settings means every view test that goes through the Django test client will fail on N+1 queries. This catches real problems in actual request paths without false positives from helper functions or scripts that intentionally defer prefetching.

For existing projects, this will likely surface many issues at once. Whitelist them and fix over time; see [Whitelisting](user-guide/whitelisting.md).

The middleware can also run in development or production settings to log warnings. Other options include the [pytest plugin](user-guide/pytest-plugin.md) for per-test control and the [Profiler](reference/api.md#profiler) context manager for scripts and manual use.

## Requirements

- Python 3.14+
- Django 6+
