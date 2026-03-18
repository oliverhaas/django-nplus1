# TODO

Thorough review of django-nplus1 codebase. Organized by severity.

---

## Bugs (all fixed)

### ~~1. `EagerListener.handle_eager` connects `TOUCH` signal repeatedly~~

FIXED: Moved TOUCH connection to `setup()` so it's connected exactly once.

### ~~2. `signals.send` iterates listeners list directly~~

FIXED: `send()` now iterates over a snapshot copy of the list.

### 3. `to_key()` does not handle unsaved instances (patch.py:25)

`to_key(instance)` returns `"ModelName:None"` for unsaved instances (pk=None).
Multiple unsaved instances of the same model share the same key, causing false positives.
NOT A BUG in practice: unsaved instances never enter `loaded` set (they can't come from DB queries).

### ~~4. `_load_config` uses `settings._wrapped` private API~~

FIXED: `notifiers.init()` now takes the settings object and uses `getattr()` with defaults.

---

## Inconsistencies

### 5. `get_worker()` defined in both `signals.py` and `patch.py`

Identical implementation in two places. `patch.py` should import from `signals.py`.

### 6. Classifier says "4 - Beta" but version is alpha (pyproject.toml:11)

`"Development Status :: 4 - Beta"` vs version `"0.1.0a1"`.
Should be `"Development Status :: 3 - Alpha"`.

### 7. Docs say "Django's native signal dispatch" but implementation is custom (README.md:9, docs/index.md:10)

The signal system is a custom callback registry (`signals.py`), not `django.dispatch.Signal`.
The text should say something like "a lightweight internal callback system" instead.

### 8. Ruff `target-version = "py313"` vs minimum Python 3.12 (pyproject.toml:69)

The ruff target version should match the minimum supported Python version (`"py312"`),
otherwise ruff may not flag syntax that doesn't work on 3.12.

### 9. `EagerListener.touched` allows `None` entries (detect.py:132)

`touched: list[tuple[type, str, list[str]] | None]` because `parse_fetch_all` can return None.
Then `log_eager` filters with `[each for each in self.touched if each]`.

**Fix:** Filter in `handle_touch` instead: `result = parser(...); if result: self.touched.append(result)`.

---

## Missing Features / Coverage Gaps

### 10. No async middleware support

PLAN.md Phase 4 lists async support. The middleware is sync-only. Django wraps sync middleware
with `sync_to_async` for async views, but `threading.current_thread().ident` may differ between
the middleware thread and the ORM thread, breaking signal routing.

### 11. `test_async.py` listed in PLAN.md but not implemented

### 12. Low test coverage in some modules

- `notifiers.py`: 24% (LogNotifier and ErrorNotifier barely tested directly)
- `pytest_plugin.py`: 47%
- `middleware.py`: 61%
- `__init__.py`: 0% (import coverage not counted due to test runner importing it early)

### 13. No test for `NPLUS1_ERROR` custom exception class

The `ErrorNotifier` accepts a custom error class via `NPLUS1_ERROR` but no test exercises this.

### 14. No test for `NPLUS1_LOG = False`

No test verifies that setting `NPLUS1_LOG = False` actually suppresses log output.

### 15. No test for concurrent requests / thread safety

The signal system uses thread-keyed dispatch but no test verifies correct behavior under
concurrent requests (e.g., two threads running middleware simultaneously).

---

## Code Quality / Simplification

### 16. `patch.py:parse_fetch_all` uses string-based type check (patch.py:262)

`manager.__class__.__name__ == "ManyRelatedManager"` is fragile.
Should use `isinstance` or duck-typing.

### 17. `Listener.__init__` parent type is `Any` (detect.py:64)

Both `NPlusOneMiddleware` and `Profiler` implement `notify(message)`.
Should define a `Protocol` for this.

### 18. Config is re-read on every request (middleware.py:43)

`_load_config` creates new notifier instances and whitelist rules on every request.
Could cache and only re-read when settings change (or just accept the overhead for simplicity).

### 19. `apps.py` sets `default_auto_field` unnecessarily (apps.py:7)

The package has no models, so this setting has no effect. Remove it.

### 20. `create_forward_many_to_many_manager` wrapper accepts `**kwargs` but original takes 2 args (patch.py:186)

The `**kwargs` could silently swallow errors. Match the original signature.

### 21. `patch.py` module-level side effects are irreversible

Monkeypatching happens at import time (triggered by `apps.ready()`).
No mechanism to unpatch. This is fine for production but makes isolated testing harder.

---

## Documentation

### 22. Whitelisting docs have formatting issues (whitelisting.md:29-31)

Missing space after colon in list items: `"myapp.*"`:matches` should be `"myapp.*"`: matches`.

### 23. API reference docs have similar formatting issues (api.md:47-52)

Same `:` immediately followed by text without space.

### 24. No migration guide section in docs

The PLAN.md has a migration guide from nplusone but it's not in the published docs.

### 25. Changelog says "0.1.0" but current version is "0.1.0a1" (changelog.md:3)

Should reflect the actual version, or note it as "0.1.0a1 (unreleased)".

---

## Packaging / CI

### 26. `.gitignore`: `*.json` is too broad

Would exclude any JSON fixture files, VS Code configs, etc.

### 27. Codecov upload only for one matrix cell (ci.yml:78)

Only uploads coverage for Python 3.13 + Django 5.2. If there are version-specific code paths,
they won't be reflected in coverage.

### 28. `ci.yml` doesn't test on Python 3.12 + Django main

The `include` only adds `3.14 + main`. Django main might have issues on 3.12 too
(though unlikely since Django main targets the latest Python).

### 29. `tag.yml` version parsing is fragile (tag.yml:28)

`grep -m1 'version = ' pyproject.toml | cut -d'"' -f2` could break if there are
other `version = ` lines before the project version (e.g., in dependency specs).
