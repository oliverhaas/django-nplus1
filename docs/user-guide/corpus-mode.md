# Corpus mode

Corpus mode collects eager loads and field loads across the whole pytest session and reports two kinds of finding once at the end: eager loads whose relation no test read (`unused_eager_load`) and concrete fields that no test read (`unused_field_load`).

The per-request `unused_eager_load` detector flags eager loads that the request didn't read. In real codebases that fires on patterns that are correct at suite scope: shared prefetch tuples consumed by many paths, `{% if %}` branches where the empty path flags the prefetch, `select_related` to sparse FKs. Corpus mode aggregates across the whole session, so an eager load passes once any test reads what it loaded.

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

Off by default.

## What changes

- Per-request `unused_eager_load` detection is off for the whole session.
- Every detection scope opened during the run (by `NPlus1Middleware`, the Celery integration, `Profiler`, the pytest marker and fixture, or a manual `with DetectionContext():`) records its eager loads, field loads and reads in a session-wide tracker.
- Django's `DeferredAttribute` becomes a data descriptor, so every read of a loaded field goes through it and counts as a read. Field values stay in the instance `__dict__`, so models behave as they do without corpus mode. Reads get slower: about 0.2 µs per read outside a scope and 1.5 µs inside one, against 0.02 µs without corpus mode.
- ORM calls outside a scope (test setup, factories, direct queryset assertions) are ignored.
- At the end of the session the findings are printed in a "django-nplus1 corpus" section of the terminal summary, and the run fails.

## What counts as instrumented

Only code executed inside an active detection scope contributes to the tracker. In practice that means:

- View bodies reached through `NPlus1Middleware` (typical: tests using the Django test client).
- Celery task bodies when `NPLUS1_CELERY = True` is set and the task signals are connected.
- Code wrapped in `Profiler()`, `@pytest.mark.nplus1`, or a manual `with DetectionContext():` block.

If a prefetch is declared and consumed entirely in test code (no middleware, no task, no explicit wrap), corpus mode will not flag it. Wrap the code you actually want audited.

## Which reads count

A read counts only for rows loaded in the same scope. Each test starts with an empty database and reuses primary keys, so a read in one test says nothing about the rows another test loaded. Nested scopes, such as a test client request inside `Profiler`, share the rows of the outermost scope.

A finding names the line that declared the eager load or, for a field, the line that started the queryset. The finding goes away once any test reads the field on a row loaded there.

Reading a forward relation, such as `pet.user`, also counts as a read of its foreign key column `user_id`, because loading the relation needs that column.

## Report

```text
============================= django-nplus1 corpus =============================
django-nplus1: corpus-wide unused_eager_load (1 finding)
  User.hobbies                   at /project/users/views.py:12 in user_list
django-nplus1: corpus-wide unused_field_load (1 finding)
  User.name                      at /project/users/views.py:12 in user_list
```

When findings remain, a run that would have passed exits with code 1. Any other exit code, such as the one for failed tests or an interrupted run, stays as it is.

## Suppression

Only `NPLUS1_WHITELIST` and `# nplus1: corpus-ignore` apply to corpus findings. Whitelists given to a scope, `nplus1_allow()` and `# nplus1: ignore` don't.

```python
NPLUS1_WHITELIST = [
    {"label": "unused_eager_load", "model": "app.Model", "field": "rel"},
]
```

A `# nplus1: corpus-ignore` comment on the line a finding names suppresses every finding for that line, eager loads and fields alike:

```python
def view(request):
    users = User.objects.prefetch_related("hobbies")  # nplus1: corpus-ignore
    ...
```

The corpus marker is distinct from the existing `# nplus1: ignore` marker. Use `corpus-ignore` for prefetches exercised only outside the test suite (management commands, error handlers).

## Unused field loads

A field loaded by the SELECT but never read across the session is reported as `unused_field_load`. The suggested fix is `.only()` or `.defer()` at the line the finding names, so the column is not fetched at all. Primary keys are never reported.

Note on `model.save()`: every field on a re-saved instance is counted as read, because `save()` reads each field it writes. Use `save(update_fields=[...])` or `.update()` to avoid reading unrelated fields.

Exclude noisy models with `NPLUS1_FIELD_EXCLUDE`:

```python
NPLUS1_FIELD_EXCLUDE = [
    "auth.User",  # exact match
    "contenttypes.*",  # wildcard: all models in the app
]
```

Patterns are fnmatch'd against `app_label.ModelName`. `["*"]` turns field tracking off.

Add `unused_field_load` to `NPLUS1_WHITELIST` to suppress individual fields. A foreign key's column goes by its attribute name, such as `user_id`:

```python
NPLUS1_WHITELIST = [
    {"label": "unused_field_load", "model": "myapp.Article", "field": "body"},
    {"label": "unused_field_load", "model": "myapp.Article", "field": "author_id"},
]
```

## pytest-xdist

Corpus mode works with pytest-xdist. Each worker hands its tracker to the controller when it finishes, and the controller reports once for the whole session. No files are written.

## For plugin authors

Connect a listener with `django_nplus1.signals.connect()` inside a detection scope. It receives signals until that scope ends. Outside a scope, `connect()` does nothing. Listeners receive each payload as the `args` tuple. Rows are identified by keys of the form `"app_label.ModelName:pk"`, and call sites are `(filename, lineno, funcname)` tuples.

- `EAGER_LOAD` carries `(model, field, keys, group, call_site)`. `group` numbers the query that loaded the rows. `call_site` is the line that declared the eager load. It is resolved in corpus mode only and is `None` otherwise.
- `FIELD_LOAD` carries `(model, attname, keys, call_site)`, once for each loaded concrete field other than the primary key. `call_site` is the line that started the queryset.
- `FIELD_TOUCH` carries `(model, attname, keys)` for each read of a loaded field.

`FIELD_LOAD` and `FIELD_TOUCH` are only sent in corpus mode.
