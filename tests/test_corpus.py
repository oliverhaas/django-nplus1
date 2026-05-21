from django_nplus1.corpus import CorpusEagerTracker


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
