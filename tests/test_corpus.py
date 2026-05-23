import json

import pytest
from testapp.models import User

from django_nplus1 import corpus
from django_nplus1.corpus import CorpusEagerTracker
from django_nplus1.signals import setup_context, teardown_context


def make_site(line=42):
    return ("/app/views.py", line, "view_fn")


def test_records_load_and_unused_when_no_touch():
    t = CorpusEagerTracker()
    t.record_load(model=int, field="hobbies", instances=["User:1", "User:2"], site=make_site())
    assert t.unused() == [(int, "hobbies", make_site())]


def test_touch_marks_load_used():
    t = CorpusEagerTracker()
    site = make_site()
    t.record_load(model=int, field="hobbies", instances=["User:1", "User:2"], site=site)
    t.record_touch(model=int, field="hobbies", instance_keys=["User:1"])
    assert t.unused() == []


def test_touch_does_not_cross_call_sites():
    t = CorpusEagerTracker()
    a = make_site(line=10)
    b = make_site(line=20)
    t.record_load(model=int, field="hobbies", instances=["User:1"], site=a)
    t.record_load(model=int, field="hobbies", instances=["User:2"], site=b)
    t.record_touch(model=int, field="hobbies", instance_keys=["User:1"])
    assert t.unused() == [(int, "hobbies", b)]


def test_repeated_loads_accumulate_instances():
    t = CorpusEagerTracker()
    site = make_site()
    t.record_load(model=int, field="hobbies", instances=["User:1"], site=site)
    t.record_load(model=int, field="hobbies", instances=["User:2"], site=site)
    t.record_touch(model=int, field="hobbies", instance_keys=["User:2"])
    assert t.unused() == []


def test_serialize_merge_round_trip():
    a = CorpusEagerTracker()
    site = make_site()
    a.record_load(model=int, field="hobbies", instances=["User:1", "User:2"], site=site)
    a.record_touch(model=int, field="hobbies", instance_keys=["User:1"])

    payload = a.serialize()

    b = CorpusEagerTracker()
    b.merge(payload)
    assert b.unused() == []  # touch from a survives merge

    b.record_load(model=int, field="pets", instances=["User:3"], site=site)
    assert b.unused() == [(int, "pets", site)]


def test_merge_skips_unresolvable_model():
    """Worker dumps may reference transient classes (e.g. Django's __fake__
    migration models) that the controller can't reimport. Merge must skip
    them rather than crash.
    """
    a = CorpusEagerTracker()
    site = make_site()
    a.merge(
        {
            "data": [
                {
                    "model": "__fake__.User",
                    "field": "hobbies",
                    "site": list(site),
                    "instances": ["User:1"],
                },
                {
                    "model": "builtins.int",
                    "field": "hobbies",
                    "site": list(site),
                    "instances": ["User:1"],
                },
            ],
            "touched": [
                {"model": "__fake__.User", "field": "hobbies", "instances": ["User:1"]},
                {"model": "builtins.int", "field": "hobbies", "instances": ["User:1"]},
            ],
        },
    )
    # Resolvable entry survived, unresolvable was silently dropped.
    assert list(a.data.keys()) == [(int, "hobbies", site)]
    assert list(a.touched.keys()) == [(int, "hobbies")]


@pytest.fixture
def fresh_tracker():
    from django_nplus1 import detect

    original_listener = detect.LISTENERS["eager_load"]
    original_tracker = corpus._corpus_tracker
    corpus.activate()
    corpus._corpus_tracker = corpus.CorpusEagerTracker()
    yield corpus._corpus_tracker
    detect.LISTENERS["eager_load"] = original_listener
    corpus._corpus_tracker = original_tracker
    corpus._corpus_enabled = False


@pytest.mark.django_db
def test_corpus_listener_records_loads_with_site(fresh_tracker, objects):
    token = setup_context()
    listener = corpus.CorpusEagerListener(parent=None)
    listener.setup()
    try:
        list(User.objects.prefetch_related("hobbies").all())
    finally:
        listener.teardown()
        teardown_context(token)

    keys = list(fresh_tracker.data.keys())
    assert len(keys) == 1
    model, field, site = keys[0]
    assert model is User
    assert field == "hobbies"
    assert site[0].endswith("test_corpus.py")


@pytest.mark.django_db
def test_corpus_listener_records_touches(fresh_tracker, objects):
    token = setup_context()
    listener = corpus.CorpusEagerListener(parent=None)
    listener.setup()
    try:
        users = list(User.objects.prefetch_related("hobbies").all())
        for u in users:
            list(u.hobbies.all())  # triggers TOUCH on prefetched manager
    finally:
        listener.teardown()
        teardown_context(token)

    assert (User, "hobbies") in fresh_tracker.touched
    assert fresh_tracker.touched[(User, "hobbies")]
    assert fresh_tracker.unused() == []


def test_corpus_context_installs_only_corpus_listener():
    with corpus.CorpusContext() as ctx:
        names = set(ctx._listeners.keys())
    assert names == {"eager_load"}


def test_activate_swaps_listener_registry():
    from django_nplus1 import detect

    original = detect.LISTENERS["eager_load"]
    corpus.activate()
    try:
        assert detect.LISTENERS["eager_load"] is corpus.CorpusEagerListener
    finally:
        detect.LISTENERS["eager_load"] = original
        corpus._corpus_enabled = False


def test_dump_worker_and_merge_round_trip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    site = ("/app/views.py", 1, "fn")

    a = corpus.CorpusEagerTracker()
    a.record_load(model=int, field="hobbies", instances=["User:1"], site=site)
    corpus._corpus_tracker = a
    corpus.dump_worker("gw0")
    dump_path = tmp_path / ".nplus1-eager-corpus.gw0.json"
    assert dump_path.exists()
    payload = json.loads(dump_path.read_text())
    assert payload["data"][0]["field"] == "hobbies"

    b = corpus.CorpusEagerTracker()
    corpus._corpus_tracker = b
    corpus.merge_worker_dumps()
    assert b.unused() == [(int, "hobbies", site)]
    assert not dump_path.exists()  # consumed after merge
