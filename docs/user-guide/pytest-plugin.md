# pytest Plugin

django-nplus1 includes a pytest plugin that is automatically discovered via entry points.

## Fixtures

### `nplus1`

A fixture that provides a `Profiler` context. Any N+1 queries detected within the test will raise `NPlus1Error`.

```python
def test_my_view(nplus1, client):
    client.get("/my-view/")  # Raises if N+1 detected
```

## Markers

### `@pytest.mark.nplus1`

Mark a test for automatic N+1 detection. The entire test is wrapped in a `Profiler`.

```python
@pytest.mark.nplus1
def test_my_view(client):
    client.get("/my-view/")
```

With whitelisting:

```python
@pytest.mark.nplus1(whitelist=[{"model": "auth.User"}])
def test_with_whitelist(client):
    client.get("/my-view/")
```

## Disabling the Plugin

If you need to disable the plugin for specific tests, you can use the `-p` flag:

```bash
pytest -p no:nplus1
```
