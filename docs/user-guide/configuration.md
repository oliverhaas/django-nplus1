# Configuration

All settings are optional and configured in your Django settings module. The middleware checks them when Django creates it, and the Celery integration when it is set up, so an invalid value raises `ImproperlyConfigured` at startup. Only the settings in use are checked: `NPLUS1_LOGGER` and `NPLUS1_LOG_LEVEL` while `NPLUS1_LOG` is on, and `NPLUS1_ERROR` while `NPLUS1_RAISE` is on. A whitelist entry that names an unknown model raises `NPlus1Error` instead, see [Whitelisting](whitelisting.md). Every `Profiler` or `DetectionContext` also checks `NPLUS1_PROJECT_PACKAGES` and the thresholds it uses when it starts, including the ones the pytest marker and fixture create.

## Settings Reference

### `NPLUS1_LOG`

Enable/disable logging of detected issues. Default: `True`.

```python
NPLUS1_LOG = True
```

### `NPLUS1_LOG_LEVEL`

Logging level for detected issues, as a number or a level name. Default: `logging.WARNING`.

```python
NPLUS1_LOG_LEVEL = "ERROR"
```

### `NPLUS1_LOGGER`

Logger for detected issues, as a logger or a logger name. Default: the `django_nplus1` logger.

```python
NPLUS1_LOGGER = "my_app.nplus1"
```

### `NPLUS1_RAISE`

Raise `NPLUS1_ERROR` on detection. Default: `False`. Logging and warnings, where enabled, happen before the raise.

```python
NPLUS1_RAISE = True  # Recommended for test settings
```

### `NPLUS1_WARN`

Emit `UserWarning` via `warnings.warn_explicit()` on detection. Default: `False`.

The warning points at the line that triggered the detection, so `pytest -W error::UserWarning` and `warnings.filterwarnings()` work with it. Unused eager loads are detected when the scope ends and point at `django_nplus1` instead.

```python
NPLUS1_WARN = True
```

### `NPLUS1_ERROR`

Exception class to raise, or a dotted path to one. Default: `NPlus1Error`.

```python
NPLUS1_ERROR = "myapp.exceptions.QueryError"
```

### `NPLUS1_THRESHOLD`

Number of rows that load the same relation or deferred field one at a time before detection fires. A row counts once, however many of its instances read it. Default: `2`.

```python
NPLUS1_THRESHOLD = 2
```

### `NPLUS1_GET_THRESHOLD`

Number of `.get()` calls from the same call site, through the same chain of calls, before detection fires. Default: `2`.

```python
NPLUS1_GET_THRESHOLD = 2
```

### `NPLUS1_SHOW_ALL_CALLERS`

Include full stack traces from each repeated access in detection messages. Default: `False`.

When enabled, messages include labeled `CALL 1:`, `CALL 2:` sections with full stack traces.

```python
NPLUS1_SHOW_ALL_CALLERS = True
```

### `NPLUS1_PROJECT_PACKAGES`

Packages that count as your code even when they are installed in `site-packages`. Default: `[]`.

A detection points at the innermost frame of your code on the call stack, and `.get()` loops and duplicate queries are counted per such call site. Frames from the standard library, installed packages and django-nplus1 itself are skipped. If your project is installed as a package, as in some Docker images, none of its frames count either: `.get()` loops and duplicate queries go undetected, N+1 messages lose their file and line, and `# nplus1: ignore` comments have no effect. List your project's top-level packages here. Their submodules count too.

```python
NPLUS1_PROJECT_PACKAGES = ["myproject"]
```

The value must be a list or tuple of module names.

### `NPLUS1_DETECT_DUPLICATE_QUERIES`

Enable SQL-level duplicate query detection. Default: `False`.

The other detectors work at the ORM descriptor level, which names the exact model and field but only sees queries that go through the descriptors. This setting adds a detector that fingerprints every SQL query, with literals replaced by `?`, and flags the same fingerprint run repeatedly from the same call site.

This catches N+1 patterns from `cursor.execute()`, `QuerySet.raw()`, and any other path that bypasses the ORM descriptors. ORM queries are fingerprinted too, so a lazy-load or `.get()` loop is also reported as `duplicate_query`.

```python
NPLUS1_DETECT_DUPLICATE_QUERIES = True
```

It watches every database connection. Queries Django runs while opening a connection, and queries with no frame of your code on the call stack, are not counted.

### `NPLUS1_DUPLICATE_QUERY_THRESHOLD`

Number of repeated identical SQL queries from the same call-site before detection fires. Default: `2`. Only relevant when `NPLUS1_DETECT_DUPLICATE_QUERIES` is enabled.

```python
NPLUS1_DUPLICATE_QUERY_THRESHOLD = 3
```

### `NPLUS1_WHITELIST`

List of patterns to ignore. Applied by the middleware, the Celery integration, corpus mode, and the pytest marker and `nplus1` fixture. A `model` pattern matches `"app_label.ModelName"`, not the bare class name. See [Whitelisting](whitelisting.md) for details.

```python
NPLUS1_WHITELIST = [
    {"model": "myapp.User", "field": "profile"},
    {"model": "auth.*"},
]
```

### `NPLUS1_CELERY`

Enable per-task N+1 detection inside Celery workers. Default: `False`. Requires the `celery` extra (`pip install "django-nplus1[celery]"`). See [Celery integration](../reference/api.md#celery-integration) for details.

```python
NPLUS1_CELERY = True
```

### `NPLUS1_FIELD_EXCLUDE`

Models whose fields corpus mode never reports as `unused_field_load`, as `app_label.ModelName` patterns with fnmatch wildcards. Default: `[]`.

```python
NPLUS1_FIELD_EXCLUDE = [
    "auth.User",
    "contenttypes.*",
]
```

### `NPLUS1_EAGER_CORPUS`

Turn on corpus mode for pytest runs, which reports the eager loads and loaded fields that no test in the session read. Default: `False`. Same as passing `--nplus1-eager-corpus`. See [Corpus Mode](corpus-mode.md).

```python
NPLUS1_EAGER_CORPUS = True
```

## Recommended Test Configuration

```python
# settings/testing.py
MIDDLEWARE = [
    ...,
    "django_nplus1.NPlus1Middleware",
]
NPLUS1_RAISE = True
```

Adding the middleware only in test settings catches N+1 queries in your actual view code paths. For existing projects that surface many issues at first, whitelist the known problems and fix them incrementally:

```python
NPLUS1_WHITELIST = [
    {"model": "myapp.Author", "field": "books"},
]
```

See [Whitelisting](whitelisting.md) for the full format.
