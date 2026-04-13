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
# tests.py
@pytest.mark.nplus1
class TestMyView:
    def test_list_books(self, books):
        response = client.get("/books/")  # raises NPlus1Error if view has N+1
```

Tests marked with `@pytest.mark.nplus1` will fail if the code under test triggers an N+1 query. Fix the N+1, or use `nplus1_allow()` in helper functions that intentionally defer prefetching to their callers.

See [examples/](examples/) for a working project and the [docs](https://oliverhaas.github.io/django-nplus1/) for full configuration.

## Celery Integration

Detect N+1 queries inside Celery tasks, using the same per-execution scoping as the HTTP middleware.

```bash
pip install django-nplus1[celery]
```

```python
# settings.py
NPLUS1_CELERY = True
```

Each task execution gets its own detection scope. Lazy loads, `.get()`-in-a-loop, unused eager loads, and duplicate queries are all detected per-task, just as they are per-request. `nplus1_allow()` works inside tasks the same way it does in views.

**Limitations:**

- `nplus1_allow()` context does not propagate across task boundaries. If a view calls `task.delay()` inside an `nplus1_allow()` block, the allow rules do not carry into the worker (ContextVars don't survive serialization).
- Scope nesting for synchronous subtasks (`.apply()` inside a task) creates a separate scope for the inner task.

## Credits

This project builds on the work of:

- [nplusone](https://github.com/jmcarp/nplusone) by Joshua Carp - the original automatic N+1 detection library for Python ORMs. django-nplus1 started as a Django-specific fork of nplusone's architecture.
- [django-zeal](https://github.com/taobojlen/django-zeal) by Tao Bojlen - inspired several features including deferred field detection, `.get()`-in-a-loop detection, `ContextVar`-based async safety, call-site tracking, and configurable thresholds.

## License

MIT
