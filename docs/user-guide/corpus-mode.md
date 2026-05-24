# Corpus mode

Corpus mode accumulates load and touch events across the entire pytest session and reports two classes of finding once at session end: prefetches that were never read (`unused_eager_load`) and concrete fields that were never read (`unused_field_load`).

The per-request `unused_eager_load` detector flags prefetches with no in-request touches. In real codebases that fires on patterns that are correct at suite scope: shared prefetch tuples consumed by many paths, `{% if %}` branches where the empty path flags the prefetch, `select_related` to sparse FKs. Corpus mode aggregates across the whole session, so a prefetch survives if any test touched it.

Field detection has no per-request equivalent. It is only available in corpus mode.

## Enable

CLI flag:

```bash
uv run pytest --nplus1-eager-corpus
```

Or in Django test settings:

```python
NPLUS1_EAGER_CORPUS = True
```

Off by default; opt-in only.

## What changes

- Per-request `unused_eager_load` detection is suppressed for the whole session.
- Any `DetectionContext` opened during the run (by `NPlus1Middleware`, the Celery integration, an explicit `Profiler`, or a manual `with DetectionContext()`) contributes EAGER_LOAD / TOUCH / FIELD_LOAD / FIELD_TOUCH events to a shared session tracker.
- `DeferredAttribute` is patched into a data descriptor so every concrete-field read passes through the touch hook, regardless of whether the value was loaded by the SELECT.
- ORM calls outside an instrumented scope (test setup, factories, direct queryset assertions) are ignored.
- At session end, surviving `(model, field, call_site)` tuples are printed for both detectors and pytest exits with code 1 if any remain.

## What counts as instrumented

Only code executed inside an active `DetectionContext` contributes to the tracker. In practice that means:

- View bodies reached through `NPlus1Middleware` (typical: tests using the Django test client).
- Celery task bodies when `NPLUS1_CELERY = True` is set and the task signals are connected.
- Code wrapped in `Profiler()`, `@pytest.mark.nplus1`, or a manual `with DetectionContext():` block.

If a prefetch is declared and consumed entirely in test code (no middleware, no task, no explicit wrap), corpus mode will not flag it. Wrap the code you actually want audited.

## Suppression

Use the existing `NPLUS1_WHITELIST` setting:

```python
NPLUS1_WHITELIST = [
    {"label": "unused_eager_load", "model": "app.Model", "field": "rel"},
]
```

Or use a per-line marker at the declaration:

```python
def view(request):
    users = User.objects.prefetch_related("hobbies")  # nplus1: corpus-ignore
    ...
```

The corpus marker is distinct from the existing `# nplus1: ignore` marker. Use `corpus-ignore` for prefetches exercised only outside the test suite (management commands, error handlers).

## Unused field loads

A field is counted as "touched" when accessing it would have triggered a database fetch had the field been deferred. Concretely, the read must be routed through `DeferredAttribute.__get__`. Fields that are loaded by the SELECT but never accessed in this way across the full pytest session are reported as `unused_field_load`. The suggested fix is to add `.only()` or `.defer()` at the call site so the column is not fetched at all.

Note on `model.save()`: every field on a re-saved instance is counted as touched, because deferring any field would force a refetch inside `save()`. Use `save(update_fields=[...])` or `.update()` to avoid touching unrelated fields.

Exclude noisy models with `NPLUS1_FIELD_EXCLUDE`:

```python
NPLUS1_FIELD_EXCLUDE = [
    "auth.User",        # exact match
    "contenttypes.*",   # wildcard: all models in the app
]
```

Patterns are fnmatch'd against `app_label.ModelName`. Setting `["*"]` short-circuits field tracking entirely.

Add `unused_field_load` to `NPLUS1_WHITELIST` to suppress individual fields:

```python
NPLUS1_WHITELIST = [
    {"label": "unused_field_load", "model": "myapp.Article", "field": "body"},
]
```

A `# nplus1: corpus-ignore` comment at the queryset call site suppresses both `unused_eager_load` and `unused_field_load` for that queryset.

## pytest-xdist

Workers dump their tracker state to `.nplus1-eager-corpus.<workerid>.json` in the pytest working directory. The controller merges all dumps in `pytest_sessionfinish` and reports once. Run pytest from the project root for consistent results across xdist invocations.

## Exit code

Corpus mode reports at session end: pytest exits with code 1 if any untouched prefetches or untouched field loads remain after whitelist filtering. The standard pytest exit code for test failures (also 1) is preserved.

## For plugin authors

Custom listeners subscribed to the `EAGER_LOAD` signal must unpack a 5-element tuple as of 0.4.0: `(model, field, instances, key, call_site)`. The fifth element is the declaration call-site as a `(filename, lineno, funcname)` tuple, or `None` if it could not be resolved.

Two new signals back the field detector:

- `FIELD_LOAD` carries `(model, field, instance_keys, call_site)`. Fired once per non-deferred concrete field on each fetched row when corpus mode is active. `call_site` may be `None` if the queryset call site could not be resolved.
- `FIELD_TOUCH` carries `(model, field, instance_keys)`. Fired on every read routed through the patched `DeferredAttribute.__get__`, which (during corpus mode) is every concrete-field read on a loaded instance.
