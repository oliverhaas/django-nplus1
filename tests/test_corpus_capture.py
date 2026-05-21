import pytest
from django.db.models import Prefetch
from testapp.models import User

from django_nplus1 import signals as nplus1_signals
from django_nplus1.signals import setup_context, teardown_context


def test_prefetch_stashes_call_site():
    p = Prefetch("hobbies")
    site = p._nplus1_site  # type: ignore[attr-defined]
    assert site is not None
    filename, _lineno, funcname = site
    assert filename.endswith("test_corpus_capture.py")
    assert funcname == "test_prefetch_stashes_call_site"


def test_prefetch_related_string_lookup_normalized_with_site():
    qs = User.objects.prefetch_related("hobbies")
    lookups = qs._prefetch_related_lookups
    assert len(lookups) == 1
    only = lookups[0]
    assert isinstance(only, Prefetch)
    assert only.prefetch_through == "hobbies"
    assert only._nplus1_site[0].endswith("test_corpus_capture.py")  # type: ignore[attr-defined]


def test_prefetch_related_preserves_existing_prefetch_site():
    inner = Prefetch("hobbies")
    inner_site = inner._nplus1_site  # type: ignore[attr-defined]
    qs = User.objects.prefetch_related(inner)
    only = qs._prefetch_related_lookups[0]
    assert only is inner
    assert only._nplus1_site == inner_site  # type: ignore[attr-defined]


def test_prefetch_related_site_survives_filter_clone():
    qs = User.objects.prefetch_related("hobbies").filter(pk=1)
    lookups = qs._prefetch_related_lookups
    only = lookups[0]
    assert isinstance(only, Prefetch)
    assert only._nplus1_site[0].endswith("test_corpus_capture.py")  # type: ignore[attr-defined]


def test_prefetch_related_none_clears_lookups():
    qs = User.objects.prefetch_related("hobbies").prefetch_related(None)
    assert qs._prefetch_related_lookups == ()


def test_select_related_stashes_sites_on_query():
    qs = User.objects.select_related("occupation")
    sites = qs.query._nplus1_select_sites
    assert "occupation" in sites
    filename, _lineno, funcname = sites["occupation"]
    assert filename.endswith("test_corpus_capture.py")
    assert funcname == "test_select_related_stashes_sites_on_query"


def test_select_related_multiple_fields_share_site():
    qs = User.objects.select_related("occupation", "occupation__user")
    sites = qs.query._nplus1_select_sites
    assert set(sites.keys()) == {"occupation", "occupation__user"}
    # Both fields registered on the same source line
    assert sites["occupation"] == sites["occupation__user"]


def test_select_related_site_survives_filter_clone():
    qs = User.objects.select_related("occupation").filter(pk=1)
    assert "occupation" in qs.query._nplus1_select_sites


def test_select_related_successive_calls_accumulate():
    qs = User.objects.select_related("occupation")
    qs = qs.select_related("occupation__user")
    sites = qs.query._nplus1_select_sites
    assert set(sites.keys()) == {"occupation", "occupation__user"}
    # Each call is on its own line, so each site records a different line number
    assert sites["occupation"] != sites["occupation__user"]


def test_select_related_none_clears_select():
    qs = User.objects.select_related("occupation").select_related(None)
    assert qs.query.select_related is False


@pytest.mark.django_db
def test_eager_load_signal_includes_site_for_prefetch(objects):
    """parse_eager_join surfaces the Prefetch declaration site."""
    captured = []

    def subscriber(args=None, kwargs=None, context=None, ret=None, parser=None):
        _model, _field, _instances, _key, site = parser(args, kwargs, context)
        captured.append(site)

    token = setup_context()
    try:
        nplus1_signals.connect(nplus1_signals.EAGER_LOAD, subscriber)
        list(User.objects.prefetch_related("hobbies").all())
    finally:
        nplus1_signals.disconnect(nplus1_signals.EAGER_LOAD, subscriber)
        teardown_context(token)

    assert captured, "EAGER_LOAD never fired"
    site = captured[0]
    assert site[0].endswith("test_corpus_capture.py")
