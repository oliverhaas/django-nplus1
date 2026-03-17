# Whitelisting

Whitelist specific model/field combinations to suppress warnings for known acceptable patterns.

## Configuration

```python
NPLUS1_WHITELIST = [
    {"model": "myapp.User", "field": "profile"},
    {"model": "auth.*"},                          # Wildcard model
    {"label": "n_plus_one", "model": "myapp.Post"},  # Only N+1, not unused eager
]
```

## Pattern Options

Each whitelist entry is a dictionary with optional keys:

| Key | Description | Example |
|-----|-------------|---------|
| `model` | Model class or `"app_label.ModelName"` pattern | `"myapp.User"`, `"auth.*"` |
| `field` | Field name | `"profile"`, `"user"` |
| `label` | Message type: `"n_plus_one"` or `"unused_eager_load"` | `"n_plus_one"` |

## Wildcard Support

The `model` field supports `fnmatch` wildcards:

- `"myapp.*"`:matches all models in `myapp`
- `"*.User"`:matches `User` in any app
- `"*"`:matches everything (not recommended)

## Profiler Whitelisting

When using the `Profiler` directly, pass whitelist to the constructor:

```python
from django_nplus1 import Profiler

with Profiler(whitelist=[{"model": "User", "field": "profile"}]):
    ...
```

Note: In the profiler context, model matching uses `model.__name__` (no app label prefix), unlike the middleware which uses `app_label.ModelName`.
