# Corpus-wide unused_eager_load

`unused_eager_load` is request-scoped by default: a prefetch with no in-request touches gets flagged. In real codebases that fires on patterns that are correct at suite scope: shared prefetch tuples consumed by many paths, `{% if %}` branches where the empty path flags the prefetch, `select_related` to sparse FKs.

Corpus mode accumulates EAGER_LOAD/TOUCH events across the entire pytest session and only reports prefetches that were never touched by any test in the suite.

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
- An autouse fixture wraps every test in a slim detection context that records loads and touches.
- At session end, surviving `(model, field, declaration_call_site)` tuples are printed and pytest exits with code 1.

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

## pytest-xdist

Workers dump their tracker state to `.nplus1-eager-corpus.<workerid>.json` in the pytest working directory. The controller merges all dumps in `pytest_sessionfinish` and reports once. Run pytest from the project root for consistent results across xdist invocations.

## Exit code

Corpus mode reports at session end: pytest exits with code 1 if any untouched prefetches remain after whitelist filtering. The standard pytest exit code for test failures (also 1) is preserved.

## For plugin authors

Custom listeners subscribed to the `EAGER_LOAD` signal must unpack a 5-element tuple as of 0.4.0: `(model, field, instances, key, call_site)`. The fifth element is the declaration call-site as a `(filename, lineno, funcname)` tuple, or `None` if it could not be resolved.
