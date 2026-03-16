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

Raise `NPlusOneError` on detection instead of (or in addition to) logging. Default: `False`.

```python
NPLUS1_RAISE = True  # Recommended for test settings
```

### `NPLUS1_ERROR`

Custom exception class to raise. Default: `NPlusOneError`.

```python
NPLUS1_ERROR = MyCustomError
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
NPLUS1_WHITELIST = [
    # Known acceptable patterns
]
```
