# django-nplus1

N+1 query detection for Django. The API is in beta and can still change before 1.0.

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

The middleware can also run in development or production settings to log warnings instead of raising. See the [docs](https://oliverhaas.github.io/django-nplus1/) for all options, including the pytest plugin and the `Profiler` context manager.

See [examples/](https://github.com/oliverhaas/django-nplus1/tree/main/examples) for a working project.

## Corpus Mode

Per-request `unused_eager_load` detection can produce false positives on shared prefetch patterns. Corpus mode collects eager loads across the full pytest session and only reports the ones no test read:

```bash
uv run pytest --nplus1-eager-corpus
```

It also reports concrete fields that were loaded but never read across the suite, as `unused_field_load`. Suppress noisy models with `NPLUS1_FIELD_EXCLUDE = ["auth.User", "contenttypes.*"]`.

See [docs](https://oliverhaas.github.io/django-nplus1/user-guide/corpus-mode/) for suppression markers and pytest-xdist support.

## Celery Integration

The equivalent of the middleware for Celery tasks. Each task execution gets its own detection scope.

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
- A detection made when a task ends, such as an unused eager load, or one that the task catches, can't fail the task, because Celery has already recorded its result. It is logged at ERROR level on the `django_nplus1` logger instead.

## Credits

This project builds on the work of:

- [nplusone](https://github.com/jmcarp/nplusone) by Joshua Carp, the original automatic N+1 detection library for Python ORMs. django-nplus1 started as a Django-specific fork of nplusone's architecture.
- [django-zeal](https://github.com/taobojlen/django-zeal) by Tao Bojlen, which inspired several features: deferred field detection, `.get()`-in-a-loop detection, `ContextVar`-based async safety, call-site tracking, and configurable thresholds.

## License

MIT
