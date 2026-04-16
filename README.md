# django-nplus1

N+1 query detection for Django. Beta - API may still change before 1.0.

## Quick Start

```bash
pip install django-nplus1
```

```python
# settings.py
INSTALLED_APPS = [..., "django_nplus1"]
```

```python
# settings/testing.py
MIDDLEWARE = [..., "django_nplus1.NPlus1Middleware"]
NPLUS1_RAISE = True
```

Adding the middleware to your test settings means every view test that goes through the Django test client will fail on N+1 queries. This catches real problems in actual request paths without false positives from helper functions or scripts that intentionally defer prefetching.

For existing projects, introducing django-nplus1 will likely surface many N+1 queries at once. Whitelist the known issues and fix them over time:

```python
# settings/testing.py
NPLUS1_WHITELIST = [
    {"model": "myapp.Author", "field": "books"},
    {"model": "myapp.Book", "field": "publisher"},
]
```

The middleware can also run in development or production settings to log warnings instead of raising — see the [docs](https://oliverhaas.github.io/django-nplus1/) for all options, including the pytest plugin and the `Profiler` context manager.

See [examples/](examples/) for a working project.

## Celery Integration

The equivalent of the middleware for Celery tasks — each task execution gets its own detection scope.

```bash
pip install django-nplus1[celery]
```

```python
# settings.py (or settings/testing.py)
NPLUS1_CELERY = True
```

Lazy loads, `.get()`-in-a-loop, unused eager loads, and duplicate queries are all detected per-task, just as they are per-request. `nplus1_allow()` works inside tasks the same way it does in views.

**Limitations:**

- `nplus1_allow()` context does not propagate across task boundaries. If a view calls `task.delay()` inside an `nplus1_allow()` block, the allow rules do not carry into the worker (ContextVars don't survive serialization).
- Scope nesting for synchronous subtasks (`.apply()` inside a task) creates a separate scope for the inner task.

## Credits

This project builds on the work of:

- [nplusone](https://github.com/jmcarp/nplusone) by Joshua Carp - the original automatic N+1 detection library for Python ORMs. django-nplus1 started as a Django-specific fork of nplusone's architecture.
- [django-zeal](https://github.com/taobojlen/django-zeal) by Tao Bojlen - inspired several features including deferred field detection, `.get()`-in-a-loop detection, `ContextVar`-based async safety, call-site tracking, and configurable thresholds.

## License

MIT
