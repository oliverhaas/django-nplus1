# Whitelisting

Whitelist specific model/field combinations to suppress warnings for known acceptable patterns.

## Global Whitelist (Settings)

```python
NPLUS1_WHITELIST = [
    {"model": "myapp.User", "field": "profile"},
    {"model": "auth.*"},                          # Wildcard model
    {"label": "n_plus_one", "model": "myapp.Post"},  # Only N+1, not unused eager
]
```

### Pattern Options

Each whitelist entry is a dictionary with optional keys:

| Key | Description | Example |
|-----|-------------|---------|
| `model` | Model class or `"app_label.ModelName"` pattern | `"myapp.User"`, `"auth.*"` |
| `field` | Field name pattern | `"profile"`, `"*"` |
| `label` | Message type: `"n_plus_one"`, `"unused_eager_load"`, or `"get_in_loop"` | `"n_plus_one"` |

### Wildcard Support

Both `model` and `field` support `fnmatch` wildcards:

- `"myapp.*"` - matches all models in `myapp`
- `"*.User"` - matches `User` in any app
- `"*"` - matches everything (not recommended for global whitelist)

Whitelist entries are validated against the Django model registry at startup. Typos in model or field names raise `NPlus1Error` with suggestions. Entries using wildcards skip validation.

## Local Suppression (`nplus1_allow`)

For suppressing detection in specific code blocks, use the `nplus1_allow()` context manager:

```python
from django_nplus1 import nplus1_allow

# Suppress all detections in a block
with nplus1_allow():
    ...

# Suppress a specific model
with nplus1_allow([{"model": "User"}]):
    ...

# Suppress a specific model/field combination
with nplus1_allow([{"model": "User", "field": "profile"}]):
    ...

# Suppress multiple patterns
with nplus1_allow([{"model": "User", "field": "profile"}, {"model": "Post"}]):
    ...
```

Uses the same whitelist format as `Profiler(whitelist=...)` and `@pytest.mark.nplus1(whitelist=...)`. Supports nesting: inner calls add to the outer rules; exiting an inner block restores the previous state. Works in both middleware and profiler contexts.

This is the recommended approach for incrementally adopting detection in existing projects: enable `NPLUS1_RAISE = True` in tests, then wrap known N+1 patterns with `nplus1_allow()` and fix them over time.

## Profiler Whitelisting

When using the `Profiler` directly, pass whitelist to the constructor:

```python
from django_nplus1 import Profiler

with Profiler(whitelist=[{"model": "User", "field": "profile"}]):
    ...
```

Note: In the profiler context, model matching uses `model.__name__` (no app label prefix), unlike the middleware which uses `app_label.ModelName`.
