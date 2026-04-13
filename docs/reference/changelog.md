# Changelog

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
