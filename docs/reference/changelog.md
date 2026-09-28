# Changelog

## Unreleased

- Corpus mode now also flags concrete fields loaded by the SELECT but never read across the suite. Reports as `unused_field_load`; suggested fix is `.only()` / `.defer()`. Suppress noisy models with `NPLUS1_FIELD_EXCLUDE`.
- `@pytest.mark.nplus1` checks only the test body. Previously its profiler also covered fixtures, including pytest-django's test database setup, so `post_migrate` handlers and data fixtures could fail the test at setup, and the failure stayed cached for later database tests on the same worker. The autouse `auto_nplus1` fixture is replaced by a `pytest_runtest_call` hook.
- The pytest marker and `nplus1` fixture apply `NPLUS1_WHITELIST`.
- `Profiler`, `nplus1_allow()`, and the marker's `whitelist` match `model` patterns against `"app_label.ModelName"` as well as the class name, so `{"model": "auth.User"}` works there too.
- Duplicate query detection skips queries Django runs while opening a connection, such as `django.contrib.postgres`' hstore and citext type lookups, and queries with no frame of your code on the stack. Call sites no longer fall back to the standard library or a launcher line such as `.venv/bin/pytest:10`, which merged unrelated library queries into one call site. Async ORM calls run in a worker thread without your frames, so `aget()` loops are no longer reported as `get_in_loop`.
- A detection raised when a `Profiler` or `DetectionContext` exits no longer replaces an exception from its body, and no longer skips tearing down the remaining listeners. Previously an unused eager load at exit left duplicate query detection attached to the connection.

## 0.3.5

- Detect deferred-field N+1 even when the row was also fetched as a singleton in the same scope. Previously, an incidental `.get()` or `refresh_from_db()` would silently suppress later `.only()`/`.defer()` detection on the same instances.
- Suppress false positives from converging FK chains in `prefetch_related_objects(...)` (e.g. two lookups sharing a tail like `store__region` / `warehouse__region`).
- Replace stale `from django.db.models import prefetch_related_objects` imports captured before `AppConfig.ready()` ran, so suppression still applies.
- Widen the `sys.modules` walk's `except` clause to tolerate any `__getattr__` error from third-party modules.

## 0.3.1

- Fix forward M2M without an explicit `related_name`: detection now uses the correct field name instead of the auto-generated one.

## 0.3.0

- Inline `# nplus1: ignore` suppression. Add a trailing comment to the call site to suppress a detection, optionally scoped to labels (`# nplus1: ignore[n_plus_one, get_in_loop]`).
- Fix false positive on `qs.prefetch_related(...).filter(pk=X)` where a queryset-level prefetch returning a single instance was flagged as N+1.

## 0.2.0

- Celery integration: per-task N+1 detection via `task_prerun`/`task_postrun` signals. Enable with `NPLUS1_CELERY = True` or `pip install django-nplus1[celery]`.
- Extract `DetectionContext` as a reusable public class for scoped detection.
- Require Python 3.14+ and Django 6+.

## 0.1.0

Initial release.

- N+1 lazy load detection for related fields (ForeignKey, OneToOneField, ManyToManyField)
- N+1 detection for deferred field access (`.defer()` / `.only()`)
- `.get()` in a loop detection
- Unused eager load detection (`select_related` / `prefetch_related`)
- SQL-level duplicate query detection as opt-in fallback (`NPLUS1_DETECT_DUPLICATE_QUERIES`)
- Call-site tracking in detection messages
- `NPLUS1_SHOW_ALL_CALLERS` mode for full stack traces
- Configurable thresholds (`NPLUS1_THRESHOLD`, `NPLUS1_GET_THRESHOLD`, `NPLUS1_DUPLICATE_QUERY_THRESHOLD`)
- Django middleware with sync and async support
- pytest plugin with `nplus1` fixture and `@pytest.mark.nplus1` marker
- `Profiler` context manager
- `nplus1_allow()` context manager for local suppression
- `nplus1_detected` Django signal for custom reporting
- Whitelisting with wildcard support and validation against Django model registry
- Multiple notification methods: logging, `warnings.warn_explicit()`, raise exception
- Python 3.12+ / Django 5.2+ support
