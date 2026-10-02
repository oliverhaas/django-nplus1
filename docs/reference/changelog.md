# Changelog

## 0.6.1 (2026-10-02)

### Detection

- `NPLUS1_THRESHOLD` counts rows, not reads. One row read through two instances, such as one from `.get()` and one from a queryset, is no longer reported as an N+1.
- `.get()` calls are counted per call site and the calls that lead from it to `.get()`. A library call that looks a row up a second way is no longer reported as `get_in_loop`, as when waffle creates a missing switch with `get_or_create()`, wagtail's redirect middleware retries a path without its query string, or `ContentType.objects.get_for_model()` creates a missing content type. Calling such a library function in a loop is still reported.

## 0.6.0 (2026-10-02)

### Breaking changes

- The pytest marker and the `nplus1` fixture treat `NPLUS1_WHITELIST` as the middleware does. Its model patterns match `"app_label.ModelName"` only, so entries such as `{"model": "Occupation"}` or `{"model": "Occ*"}` no longer match there. An entry naming an unknown model raises `NPlus1Error`, which fails a test with the marker and errors a test with the fixture at setup. The marker's own `whitelist` still matches class names.
- The middleware, `setup_celery_detection()` and every detection scope raise `ImproperlyConfigured` when `django_nplus1` is missing from `INSTALLED_APPS`. Without the app, detection found nothing and said nothing.

### Detection

- A foreign key column deferred with `.only()` or `.defer()` and read by `prefetch_related()`, which loads it one row at a time, is reported as an N+1. This covers the rows of the queryset, the rows of a `Prefetch()` queryset, and `.iterator()` chunks.
- A relation read in a loop is reported even when its rows were each fetched on their own earlier in the scope, for example by `.get()` or an earlier lazy load, and then loaded again in one query.
- `.get()` calls that raise `DoesNotExist` or `MultipleObjectsReturned` count toward `get_in_loop`.
- Loops over `.aiterator()` are detected.
- Async ORM calls such as `aget()` take the call site of the line in your coroutine that awaited them. `aget()` loops are reported as `get_in_loop` again, and separate `aget()` calls in an async view requested from sync code, such as the test client, are no longer reported as one loop.
- Rows loaded in an enclosing scope count in nested scopes. Reading a relation row by row in an inner scope is reported, and reads split between the scopes add up.
- `select_related()` on an `.iterator()` queryset is no longer reported as an unused eager load when the loop reads the relation on early rows only.
- With Django 6.1's `FETCH_PEERS`, a deferred field or `GenericForeignKey` read in a loop loads every row in one query and is no longer reported as an N+1. With `FETCH_RAISE`, a blocked read of a deferred field no longer counts as a load.

### Settings

- New `NPLUS1_PROJECT_PACKAGES` names packages that count as your code even when they are installed in `site-packages`, as in some Docker images. Without it, such projects got no `.get()` loop or duplicate query detection, and N+1 messages had no file and line. See [Configuration](../user-guide/configuration.md#nplus1_project_packages).

### Reporting

- `nplus1_detected` is sent with `send_robust()`. A receiver that raises is logged on the `django.dispatch` logger instead of breaking the code that made the detection, and async receivers work in async views.
- A scope whose block raises no longer reports unused eager loads, because the error can stop the block before it reads them. They used to be logged, warned about and sent with `nplus1_detected`, and only the raise was skipped.
- A `duplicate_query` message keeps the whole query in `.field`, so whitelist patterns match all of it. The message text still shows the first 120 characters.

### Celery

- Two runs of the same task id in different threads at once no longer end each other's detection scope.
- The `ImportError` raised without Celery quotes the install command, `pip install "django-nplus1[celery]"`, which zsh needs.

## 0.5.0 (2026-10-02)

- **Breaking:** A detection that code inside a scope catches, as Django's `{% if %}` tag does when a comparison raises, now fails the scope when it ends. This applies to `NPlus1Middleware` with `NPLUS1_RAISE`, `Profiler`, `DetectionContext`, `@pytest.mark.nplus1` and the `nplus1` fixture. The caught detection replaces an exception that the block raises later, but never a `BaseException` such as `KeyboardInterrupt`.
- **Breaking:** With the marker or the fixture, a test fails on a detection even inside `pytest.raises(NPlus1Error)`. To check that code makes an N+1 query, use a `Profiler` in a test without them, as in [Asserting a Detection](../user-guide/pytest-plugin.md#asserting-a-detection).
- **Breaking:** A detection raised when a Celery task ends, such as an unused eager load, now fails the enclosing scope if the task runs inside one, such as a request under `NPlus1Middleware`, a test with the marker or the fixture, or another task. The task used to log it at ERROR level. A task runs inside the scope that calls `.apply()`, or `.delay()` under `task_always_eager`, so tests that run tasks eagerly can now fail.
- A fixture of your own that yields inside `with Profiler():` can't see the test's exception, so a detection that fails the test fails its teardown too. Have it request the `nplus1` fixture instead.
- A detection that a Celery task catches is logged at ERROR level when the task ends. If the task runs inside another scope, that scope raises it instead. The log message reads `detection not raised by task <id>` instead of `detection at the end of task <id> raised`.
- When a test that uses the `nplus1` fixture fails or errors at setup, it no longer also errors at teardown on an unused eager load. The failure can stop the test before it reads the eager load.
- With `NPLUS1_RAISE`, a Celery task that fails no longer logs an unused eager load found when it ends, for the same reason.

## 0.4.0 (2026-09-29)

### Breaking changes

- Invalid settings raise `ImproperlyConfigured` when the middleware is created or Celery detection is set up. This covers a threshold that is not an integer of at least 1, an `NPLUS1_LOG_LEVEL` that is neither a number nor a level name, an `NPLUS1_LOGGER` that is neither a logger nor a logger name, and an `NPLUS1_ERROR` that is not an exception class or a path to one. A threshold such as `0` or `"2"` used to turn detection off without a word. `Profiler` and `DetectionContext` check the thresholds they use when they are entered.
- Detection scopes nest. A detection in an inner scope reaches the notifiers of every enclosing scope, where notifiers built from the same settings report it once, and a whitelist entry of any of them suppresses it. With `NPlus1Middleware` installed, `@pytest.mark.nplus1`, the `nplus1` fixture and `Profiler` now see N+1 queries in views that a test requests through the test client. Tests that passed because the middleware hid those queries from them can now fail.
- `nplus1_allow([])` suppresses nothing. Only `nplus1_allow()` without an argument suppresses every detection.
- Listeners of the `EAGER_LOAD` signal receive `(model, field, keys, group, call_site)`, and instance keys have the form `app_label.ModelName:pk`.

### Corpus mode

- `pytest --nplus1-eager-corpus`, or `NPLUS1_EAGER_CORPUS = True`, collects eager loads and loaded fields across the whole session. At the end it reports the ones that no test read and fails the session. Unused `select_related()` and `prefetch_related()` calls are reported as `unused_eager_load`, and columns that `.only()` or `.defer()` could skip as `unused_field_load`. See [Corpus Mode](../user-guide/corpus-mode.md).
- A finding names the line that declared the eager load or started the queryset. A `# nplus1: corpus-ignore` comment on that line suppresses it. `NPLUS1_FIELD_EXCLUDE` skips whole models, and `NPLUS1_WHITELIST` applies.
- Works with pytest-xdist. Workers hand their findings to the controller, so no files are written.
- New `FIELD_LOAD` and `FIELD_TOUCH` signals feed the field tracking.

### Detection

- N+1 queries and unused prefetches on `GenericRelation` managers are detected.
- A `GenericForeignKey` read in a loop is reported as an N+1 on the relation, such as `Tag.content_object`. It was reported as `get()` in a loop on the target model.
- Loops over `.iterator()` are detected.
- A deferred field read in a loop is reported once, as an N+1 on the field. It was also reported as `get()` in a loop, which fired at the second read whatever `NPLUS1_THRESHOLD` said, and a whitelist entry for the field didn't stop it.
- Eager loads that are read are no longer reported as unused. This affected `Prefetch(to_attr=...)` lists that are iterated, indexed, measured or searched, `GenericForeignKey` prefetches, `.count()` and `.exists()` on a prefetched relation, and `select_related()` through proxy models, multi-table inheritance parents, self-referential reverse one-to-one relations and `FilteredRelation`.
- Reading a relation loaded with `select_related()` is no longer reported as an N+1 when the same rows were loaded earlier in the scope.
- Rows of models with the same class name in different apps are told apart.
- Call sites no longer point into django-nplus1's own code when the package is imported through a symlinked path.
- Duplicate query detection runs under the async middleware and on every database connection, not only `default`. SQL given as bytes or as a psycopg `sql.Composed` object no longer raises `TypeError` after the query has run. The query text in the message is cut to 120 characters.
- Duplicate query detection skips queries Django runs while opening a connection, such as `django.contrib.postgres`' hstore and citext type lookups, and queries with no frame of your code on the stack. Call sites no longer fall back to the standard library or a launcher line such as `.venv/bin/pytest:10`, which merged unrelated library queries into one call site. Async ORM calls run in a worker thread without your frames, so `aget()` loops are no longer reported as `get_in_loop`.

### Suppression and scopes

- A suppressed read no longer uses up the one report per model and field, so a later N+1 in the same scope is still reported. With `NPLUS1_SHOW_ALL_CALLERS`, an ignore comment suppresses a detection only when every listed call carries it.
- `nplus1_allow()` also suppresses unused eager loads.
- A whitelist entry for a model also covers its proxy models and multi-table inheritance children.
- `Profiler`, `nplus1_allow()`, and the marker's `whitelist` match `model` patterns against `"app_label.ModelName"` as well as the class name, so `{"model": "auth.User"}` works there too.
- In `duplicate_query` whitelist entries, `[` in the `field` pattern matches a literal bracket.
- `DetectionContext` accepts whitelist entries as dicts, like `Profiler`. It crashed at the first detection.
- Rows loaded in a scope can be read in a nested scope without being reported as an unused eager load.
- Entering a scope that is already active raises `RuntimeError`. It used to leak the scope's listeners.
- Prefetches running in several threads of one scope at once no longer hide lazy loads in the other threads, and no longer switch N+1 detection off for the rest of the scope.
- A detection raised when a `Profiler` or `DetectionContext` exits no longer replaces an exception from its body, and no longer skips tearing down the remaining listeners. Previously an unused eager load at exit left duplicate query detection attached to the connection.

### Reporting and settings

- `Profiler` accepts `notifiers`, which run before it raises, for example to also log the detection.
- `NPLUS1_LOGGER` accepts a logger name, `NPLUS1_LOG_LEVEL` a level name such as `"ERROR"`, and `NPLUS1_ERROR` a dotted path to an exception class. Strings used to crash the request at the first detection.
- With `NPLUS1_SHOW_ALL_CALLERS`, the calls listed in a message no longer change after it was sent, and `NPLUS1_WARN` warnings point at the line that triggered the detection instead of `django_nplus1:0`.

### Middleware

- `NPlus1Middleware` is a class. The `MIDDLEWARE` entry stays `"django_nplus1.NPlus1Middleware"`.
- `NPLUS1_WHITELIST` is checked when the middleware is created, at startup instead of on the first request. An unknown model still raises `NPlus1Error`. An unknown field only warns, because a `Prefetch(to_attr=...)` name is no model field. Column names such as `user_id` and model classes are accepted.
- With `NPLUS1_RAISE`, an exception raised by the view is no longer replaced by a detection made at the end of the request.

### Celery

- Invalid settings raise when detection is set up, which happens at startup with `NPLUS1_CELERY = True`. They used to turn detection off for every task, with a DEBUG log line. When detection can't start for a single task, the task still runs and the error is logged at ERROR level.
- A detection made when a task ends, such as an unused eager load, is logged at ERROR level on the `django_nplus1` logger instead of raised. Celery can't fail a task that has already finished.
- An eager `self.replace()` no longer leaves its detection scope active.

### pytest plugin

- `@pytest.mark.nplus1` checks only the test body. Previously its profiler also covered fixtures, including pytest-django's test database setup, so `post_migrate` handlers and data fixtures could fail the test at setup, and the failure stayed cached for later database tests on the same worker. The autouse `auto_nplus1` fixture is replaced by a `pytest_runtest_call` hook.
- The pytest marker and `nplus1` fixture apply `NPLUS1_WHITELIST`.

### ORM patches

These apply as soon as `django_nplus1` is installed, also outside detection scopes.

- Related querysets, and instances with prefetched relations, can be pickled and deep-copied.
- A related manager called with `manager=`, as in `user.hobbies(manager="objects")`, no longer raises `TypeError`.
- Calling `.all()` many times on a prefetched relation no longer ends in `RecursionError`.
- Related querysets are freed without waiting for the garbage collector.

### Compatibility

- Supports Django 6.1.

## 0.3.5 (2026-05-20)

- A deferred field read in a loop is reported even when the same rows were also fetched one at a time in the scope, for example with `.get()` or `refresh_from_db()`. Such a fetch used to hide the N+1.

## 0.3.4 (2026-04-20)

- Django no longer fails to start when an imported module's `__getattr__` raises an error such as `KeyError`, as ddtrace's does. The failure started in 0.3.3.

## 0.3.3 (2026-04-18)

- The 0.3.2 fix also applies in modules that import `prefetch_related_objects` from `django.db.models` before django-nplus1's `AppConfig.ready()` runs, such as `models.py` files.

## 0.3.2 (2026-04-18)

- `prefetch_related_objects()` with lookups that end on the same relation, such as `store__region` and `warehouse__region`, is no longer reported as an N+1. Calling it on one row at a time in a loop is still reported.

## 0.3.1 (2026-04-16)

- Fix forward M2M without an explicit `related_name`: detection now uses the correct field name instead of the auto-generated one.

## 0.3.0 (2026-04-14)

- Inline `# nplus1: ignore` suppression. Add a trailing comment to the call site to suppress a detection, optionally scoped to labels (`# nplus1: ignore[n_plus_one, get_in_loop]`).
- Fix false positive on `qs.prefetch_related(...).filter(pk=X)` where a queryset-level prefetch returning a single instance was flagged as N+1.

## 0.2.1 (2026-04-14)

- **Breaking:** Requires Python 3.14+ and Django 6+. Python 3.12, Python 3.13 and Django 5.2 are no longer supported.

## 0.2.0 (2026-04-13)

- Celery integration: per-task N+1 detection via `task_prerun`/`task_postrun` signals. Enable with `NPLUS1_CELERY = True` or by calling `django_nplus1.celery.setup_celery_detection()`. The `celery` extra (`pip install "django-nplus1[celery]"`) installs Celery.
- Extract `DetectionContext` as a reusable public class for scoped detection.

## 0.1.0 (2026-04-12)

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
