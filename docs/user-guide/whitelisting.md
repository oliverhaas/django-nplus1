# Whitelisting

Whitelist specific model/field combinations to suppress warnings for known acceptable patterns.

## Global Whitelist (Settings)

```python
NPLUS1_WHITELIST = [
    {"model": "myapp.User", "field": "profile"},
    {"model": "auth.*"},  # Wildcard model
    {"label": "n_plus_one", "model": "myapp.Post"},  # Only N+1, not unused eager
]
```

### Pattern Options

Each whitelist entry is a dictionary with optional keys:

| Key | Description | Example |
|-----|-------------|---------|
| `model` | Model class or `"app_label.ModelName"` pattern | `"myapp.User"`, `"auth.*"` |
| `field` | Field name pattern; for `duplicate_query`, a pattern for the query's SQL | `"profile"`, `"*"` |
| `label` | Message type: `"n_plus_one"`, `"unused_eager_load"`, `"get_in_loop"`, `"duplicate_query"`, or `"unused_field_load"` | `"n_plus_one"` |

A `duplicate_query` detection's field is the whole query with literals replaced by `?`. The message shows only its first 120 characters, but patterns match against the whole query. Match it to suppress one query shape instead of every duplicate. In these patterns `[` matches a literal bracket:

```python
NPLUS1_WHITELIST = [
    {"label": "duplicate_query", "field": '*FROM "myapp_setting"*'},
]
```

### Wildcard Support

Both `model` and `field` support `fnmatch` wildcards:

- `"myapp.*"` matches all models in `myapp`
- `"*.User"` matches `User` in any app
- `"*"` matches everything (not recommended for global whitelist)

An entry for a model also covers its proxy models and multi-table inheritance children.

`NPLUS1_WHITELIST` is checked against your models when the middleware is created, when Celery detection is set up, and when a test with the pytest marker or the `nplus1` fixture starts. An unknown model raises `NPlus1Error` with suggestions. An unknown field only warns, because a `Prefetch(to_attr=...)` name is no model field. Column names such as `user_id` count as fields. Entries using wildcards aren't checked.

### Rows Created on First Use

Some libraries create a row the first time they need it. Wagtail runs `get_or_create()` for an image rendition the first time a page needs that rendition, so a page that needs several new renditions is reported as `get_in_loop`. Later requests find the renditions without `.get()`. Tests start without renditions, so each test that renders such a page reports the loop. Whitelist the model for that label:

```python
NPLUS1_WHITELIST = [
    {"label": "get_in_loop", "model": "wagtailimages.Rendition"},
]
```

With a custom rendition model, list that model instead. Django's content type lookups, such as `ContentType.objects.get_for_model()`, fill a cache and need no entry.

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

Uses the same whitelist format as `Profiler(whitelist=...)` and `@pytest.mark.nplus1(whitelist=...)`. An empty list suppresses nothing. Supports nesting: inner calls add to the outer rules; exiting an inner block restores the previous state. Works in every detection scope.

An unused eager load is reported when the scope ends, but it is suppressed when the query that loaded it ran inside the block.

Use it for code that is fine as it is, such as a loop over a few rows that a page never shows more of. To adopt detection in an existing project, list the known N+1 queries in `NPLUS1_WHITELIST` instead and remove the entries as you fix them.

## Inline Suppression (`# nplus1: ignore`)

For per-line suppression co-located with the offending code, add a trailing comment to the call site:

```python
# Suppress any detection on this line
occupations[0].user  # nplus1: ignore

# Scope to one label
for user in User.objects.all():
    User.objects.get(pk=user.pk)  # nplus1: ignore[get_in_loop]

# Scope to multiple labels
for user in users:
    User.objects.get(pk=user.pk)  # nplus1: ignore[n_plus_one, get_in_loop]
```

Supported labels: `n_plus_one`, `get_in_loop`, `duplicate_query`.

Inline comments apply to the exact line captured as the detection's call site. With `NPLUS1_SHOW_ALL_CALLERS`, a detection is suppressed only when every listed call carries the comment. They do **not** apply to `unused_eager_load` detections, which happen at teardown without a specific call site; use the global whitelist or `nplus1_allow()` for those. For corpus mode findings, use [`# nplus1: corpus-ignore`](corpus-mode.md#suppression).

## Profiler Whitelisting

When using the `Profiler` or a `DetectionContext` directly, pass whitelist to the constructor:

```python
from django_nplus1 import Profiler

with Profiler(whitelist=[{"model": "User", "field": "profile"}]):
    ...
```

`Profiler`, `DetectionContext`, `nplus1_allow()`, and the pytest marker's `whitelist` match a `model` pattern against both the class name (`"User"`) and `"app_label.ModelName"` (`"auth.User"`), so patterns copied from `NPLUS1_WHITELIST` work unchanged. `NPLUS1_WHITELIST` itself matches `"app_label.ModelName"` only, also where the pytest marker and the `nplus1` fixture apply it.

A whitelist also covers the scopes nested inside its own. The marker's whitelist applies to views that the test requests through the test client, even though the middleware opens a scope of its own.
