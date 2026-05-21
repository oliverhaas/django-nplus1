from django.db.models import Prefetch


def test_prefetch_stashes_call_site():
    p = Prefetch("hobbies")
    site = p._nplus1_site  # type: ignore[attr-defined]
    assert site is not None
    filename, _lineno, funcname = site
    assert filename.endswith("test_corpus_capture.py")
    assert funcname == "test_prefetch_stashes_call_site"
