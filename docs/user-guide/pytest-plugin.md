# pytest Plugin

django-nplus1 includes a pytest plugin that is automatically discovered via entry points.

## Fixtures

### `nplus1`

A fixture that provides a `Profiler` context. Any N+1 queries detected while it is active raise `NPlus1Error`.

```python
def test_my_view(client, nplus1):
    client.get("/my-view/")  # Raises if N+1 detected
```

The profiler is active from the fixture's setup to its teardown, so fixtures requested after `nplus1` run inside it. Request it last, or use the marker, to check only the test body.

## Markers

### `@pytest.mark.nplus1`

Mark a test for automatic N+1 detection. The test body runs inside a `Profiler`. Fixtures, including pytest-django's test database setup, run outside it.

```python
@pytest.mark.nplus1
def test_my_view(client):
    client.get("/my-view/")
```

For `unittest`-style tests such as `django.test.TestCase`, pytest runs `setUp()` and `tearDown()` as part of the test, so they are checked too.

With whitelisting:

```python
@pytest.mark.nplus1(whitelist=[{"model": "auth.User"}])
def test_with_whitelist(client):
    client.get("/my-view/")
```

## Asserting a Detection

The marker and the fixture report a detection even when something catches it: the code under test, as Django's `{% if %}` tag does when a comparison raises, or a `pytest.raises(NPlus1Error)` in the test. With the marker the test fails. With the fixture it errors at teardown, as it does on an unused eager load. To check that code makes an N+1 query, use a `Profiler` in a test without the marker or the fixture:

```python
import pytest

from django_nplus1 import NPlus1Error, Profiler


def test_my_view_makes_an_n_plus_1(client):
    with pytest.raises(NPlus1Error), Profiler():
        client.get("/my-view/")
```

## Whitelisting

The marker and the `nplus1` fixture apply `NPLUS1_WHITELIST` from your settings, plus the marker's own `whitelist`. `NPLUS1_WHITELIST` entries match models by `"app_label.ModelName"` only, as they do in the middleware, while the marker's entries also match the class name. An `NPLUS1_WHITELIST` entry that names an unknown model raises `NPlus1Error`, which fails a test with the marker and errors one with the fixture at setup. See [Whitelisting](whitelisting.md) for the pattern format.

## Corpus Mode

`pytest --nplus1-eager-corpus`, or `NPLUS1_EAGER_CORPUS = True` in your test settings, reports the eager loads and loaded fields that no test in the session read, and fails the run. See [Corpus Mode](corpus-mode.md).

## Disabling the Plugin

To run without the plugin, for example when another plugin clashes with it, pass `-p no:nplus1`. This turns it off for the whole run, so the marker, the fixture and corpus mode are unavailable:

```bash
pytest -p no:nplus1
```
