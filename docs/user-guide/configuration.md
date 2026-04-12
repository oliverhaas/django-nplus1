# Configuration

All settings are optional and configured in your Django settings module.

## Settings Reference

### `NPLUS1_LOG`

Enable/disable logging of detected issues. Default: `True`.

```python
NPLUS1_LOG = True
```

### `NPLUS1_LOG_LEVEL`

Python logging level for detected issues. Default: `logging.WARNING`.

```python
import logging
NPLUS1_LOG_LEVEL = logging.WARNING
```

### `NPLUS1_LOGGER`

Custom logger instance. Default: `logging.getLogger("django_nplus1")`.

```python
import logging
NPLUS1_LOGGER = logging.getLogger("my_app.nplus1")
```

### `NPLUS1_RAISE`

Raise `NPlus1Error` on detection instead of (or in addition to) logging. Default: `False`.

```python
NPLUS1_RAISE = True  # Recommended for test settings
```

### `NPLUS1_WARN`

Emit `UserWarning` via `warnings.warn_explicit()` on detection. Default: `False`.

When caller info is available, the warning points to the exact file and line. Integrates with `pytest -W error::UserWarning` and `warnings.filterwarnings()`.

```python
NPLUS1_WARN = True
```

### `NPLUS1_ERROR`

Custom exception class to raise. Default: `NPlus1Error`.

```python
NPLUS1_ERROR = MyCustomError
```

### `NPLUS1_THRESHOLD`

Number of repeated lazy accesses of the same model/field pair before detection fires. Default: `2`.

```python
NPLUS1_THRESHOLD = 2
```

### `NPLUS1_GET_THRESHOLD`

Number of repeated `.get()` calls from the same call-site before detection fires. Default: `2`.

```python
NPLUS1_GET_THRESHOLD = 2
```

### `NPLUS1_SHOW_ALL_CALLERS`

Include full stack traces from each repeated access in detection messages. Default: `False`.

When enabled, messages include labeled `CALL 1:`, `CALL 2:` sections with full stack traces.

```python
NPLUS1_SHOW_ALL_CALLERS = True
```

### `NPLUS1_DETECT_DUPLICATE_QUERIES`

Enable SQL-level duplicate query detection. Default: `False`.

The primary detection works at the ORM descriptor level, which provides exact model/field identification but only catches queries going through the ORM. This setting enables a secondary detector that fingerprints raw SQL queries and flags repeated identical queries from the same call-site.

This catches N+1 patterns from `cursor.execute()`, `QuerySet.raw()`, and any other path that bypasses the ORM descriptors.

```python
NPLUS1_DETECT_DUPLICATE_QUERIES = True
```

Note: duplicate query detection only monitors the default database connection. Multi-database setups won't detect duplicates on secondary connections.

### `NPLUS1_DUPLICATE_QUERY_THRESHOLD`

Number of repeated identical SQL queries from the same call-site before detection fires. Default: `2`. Only relevant when `NPLUS1_DETECT_DUPLICATE_QUERIES` is enabled.

```python
NPLUS1_DUPLICATE_QUERY_THRESHOLD = 3
```

### `NPLUS1_WHITELIST`

List of patterns to ignore. See [Whitelisting](whitelisting.md) for details.

```python
NPLUS1_WHITELIST = [
    {"model": "myapp.User", "field": "profile"},
    {"model": "auth.*"},
]
```

## Recommended Test Configuration

```python
# settings/test.py
NPLUS1_RAISE = True
```

With good test coverage, this catches N+1 queries during testing. For existing projects that surface many issues at first, use `nplus1_allow()` to suppress known problems and fix them incrementally. See [nplus1_allow](../reference/api.md#nplus1_allow) for details.
