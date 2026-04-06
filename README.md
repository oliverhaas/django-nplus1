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
    def test_no_nplus1(self):
        books = list(Book.objects.select_related("author"))
        [book.author.name for book in books]  # OK

    def test_nplus1_detected(self):
        with pytest.raises(NPlus1Error):
            books = list(Book.objects.all())
            [book.author.name for book in books]  # N+1!
```

Use `nplus1_allow()` to suppress known N+1s while you fix them. Use `NPlus1Middleware` for runtime detection. See [examples/](examples/) for a working project and the [docs](https://oliverhaas.github.io/django-nplus1/) for full configuration.

## License

MIT
