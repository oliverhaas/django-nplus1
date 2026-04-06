# django-nplus1

N+1 query detection for Django.

Based on [nplusone](https://github.com/jmcarp/nplusone) by [Joshua Carp](https://github.com/jmcarp). Several features inspired by [django-zeal](https://github.com/taobojlen/django-zeal) by [Tao Bojlen](https://github.com/taobojlen).

## Quick Start

```bash
pip install django-nplus1
```

```python
# settings.py
INSTALLED_APPS = [..., "django_nplus1"]
```

```python
# tests.py
@pytest.mark.nplus1
class TestMyView:
    def test_list_books(self, books):
        response = client.get("/books/")  # raises NPlus1Error if view has N+1
```

Tests marked with `@pytest.mark.nplus1` will fail if the code under test triggers an N+1 query. Fix the N+1, or use `nplus1_allow()` in helper functions that intentionally defer prefetching to their callers.

See [examples/](examples/) for a working project and the [docs](https://oliverhaas.github.io/django-nplus1/) for full configuration.

## License

MIT
