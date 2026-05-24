from django_nplus1.corpus import CorpusFieldTracker


def make_site(line=42):
    return ("/app/views.py", line, "view_fn")


def test_records_load_and_unused_when_no_touch():
    t = CorpusFieldTracker()
    t.record_load(model=int, field="bio", instances=["User:1", "User:2"], site=make_site())
    assert t.unused() == [(int, "bio", make_site())]


def test_touch_marks_load_used():
    t = CorpusFieldTracker()
    site = make_site()
    t.record_load(model=int, field="bio", instances=["User:1", "User:2"], site=site)
    t.record_touch(model=int, field="bio", instance_keys=["User:1"])
    assert t.unused() == []


def test_touch_does_not_cross_call_sites():
    t = CorpusFieldTracker()
    a = make_site(line=10)
    b = make_site(line=20)
    t.record_load(model=int, field="bio", instances=["User:1"], site=a)
    t.record_load(model=int, field="bio", instances=["User:2"], site=b)
    t.record_touch(model=int, field="bio", instance_keys=["User:1"])
    assert t.unused() == [(int, "bio", b)]


def test_serialize_merge_round_trip():
    a = CorpusFieldTracker()
    site = make_site()
    a.record_load(model=int, field="bio", instances=["User:1"], site=site)
    a.record_touch(model=int, field="bio", instance_keys=["User:1"])
    payload = a.serialize()
    b = CorpusFieldTracker()
    b.merge(payload)
    assert b.unused() == []


def test_merge_skips_unresolvable_model():
    a = CorpusFieldTracker()
    site = make_site()
    a.merge(
        {
            "data": [
                {
                    "model": "__fake__.User",
                    "field": "bio",
                    "site": list(site),
                    "instances": ["User:1"],
                },
                {
                    "model": "builtins.int",
                    "field": "bio",
                    "site": list(site),
                    "instances": ["User:1"],
                },
            ],
            "touched": [
                {"model": "__fake__.User", "field": "bio", "instances": ["User:1"]},
                {"model": "builtins.int", "field": "bio", "instances": ["User:1"]},
            ],
        },
    )
    assert list(a.data.keys()) == [(int, "bio", site)]
    assert list(a.touched.keys()) == [(int, "bio")]
