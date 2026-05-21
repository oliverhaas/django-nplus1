import pytest
from django.db.models import Prefetch
from testapp.models import User


def test_prefetch_stashes_call_site():
    p = Prefetch("hobbies")
    site = p._nplus1_site  # type: ignore[attr-defined]
    assert site is not None
    filename, _lineno, funcname = site
    assert filename.endswith("test_corpus_capture.py")
    assert funcname == "test_prefetch_stashes_call_site"


@pytest.mark.django_db
def test_prefetch_related_string_lookup_normalized_with_site(db):
    qs = User.objects.prefetch_related("hobbies")
    lookups = qs._prefetch_related_lookups
    assert len(lookups) == 1
    only = lookups[0]
    assert isinstance(only, Prefetch)
    assert only.prefetch_through == "hobbies"
    assert only._nplus1_site[0].endswith("test_corpus_capture.py")  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_prefetch_related_preserves_existing_prefetch_site(db):
    inner = Prefetch("hobbies")
    inner_site = inner._nplus1_site  # type: ignore[attr-defined]
    qs = User.objects.prefetch_related(inner)
    only = qs._prefetch_related_lookups[0]
    assert only is inner
    assert only._nplus1_site == inner_site  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_prefetch_related_site_survives_filter_clone(db):
    qs = User.objects.prefetch_related("hobbies").filter(pk=1)
    lookups = qs._prefetch_related_lookups
    only = lookups[0]
    assert isinstance(only, Prefetch)
    assert hasattr(only, "_nplus1_site")
