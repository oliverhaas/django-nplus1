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


import pytest

from django_nplus1 import signals
from django_nplus1.signals import setup_context, teardown_context


@pytest.fixture
def deferred_patch():
    from django_nplus1 import fields

    fields._patch_deferred_attribute()
    yield fields
    fields._unpatch_deferred_attribute()


@pytest.fixture
def field_events():
    token = setup_context()
    events = []

    def receiver(args=None, kwargs=None, context=None, ret=None, parser=None):
        events.append(("touch", args, kwargs))

    signals.connect(signals.FIELD_TOUCH, receiver)
    yield events
    signals.disconnect(signals.FIELD_TOUCH, receiver)
    teardown_context(token)


@pytest.mark.django_db
def test_set_routes_field_into_side_cache(deferred_patch, db):
    from testapp.models import User

    u = User(name="Alice")
    cache = u.__dict__.get("_nplus1_field_cache", {})
    assert cache.get("name") == "Alice"
    assert "name" not in {k for k in u.__dict__ if k != "_nplus1_field_cache"}


@pytest.mark.django_db
def test_get_returns_cached_value(deferred_patch, db):
    from testapp.models import User

    u = User(name="Alice")
    assert u.name == "Alice"


@pytest.mark.django_db
def test_get_fires_field_touch_signal(deferred_patch, field_events, db):
    from testapp.models import User

    u = User(name="Alice")
    _ = u.name
    touch_events = [e for e in field_events if e[0] == "touch"]
    assert touch_events, "expected at least one FIELD_TOUCH"
    # parsers run with args=(model, field, instance_keys) shape
    _, args, _ = touch_events[-1]
    assert args[0] is User
    assert args[1] == "name"


def test_patch_is_idempotent(deferred_patch):
    from django.db.models.query_utils import DeferredAttribute

    from django_nplus1 import fields

    has_set_before = hasattr(DeferredAttribute, "__set__")
    fields._patch_deferred_attribute()  # second call
    assert hasattr(DeferredAttribute, "__set__") == has_set_before


@pytest.mark.django_db
def test_field_listener_records_load_and_touch(deferred_patch, db):
    from testapp.models import User

    from django_nplus1 import corpus

    token = setup_context()
    listener = corpus.CorpusFieldListener(parent=None)
    listener.setup()
    tracker = corpus.CorpusFieldTracker()
    corpus._corpus_field_tracker = tracker
    try:
        site = ("/app/views.py", 42, "view")
        signals.send(
            signals.FIELD_LOAD,
            args=(User, "name", ["User:1"], site),
            kwargs={},
            ret=None,
            context={},
            parser=lambda a, k, c: (a[0], a[1], a[2], a[3]),
        )
        signals.send(
            signals.FIELD_TOUCH,
            args=(User, "name", ["User:1"]),
            kwargs={},
            ret=None,
            context={},
            parser=lambda a, k, c: (a[0], a[1], a[2]),
        )
    finally:
        listener.teardown()
        teardown_context(token)
        corpus._corpus_field_tracker = None

    assert tracker.unused() == []


@pytest.mark.django_db
def test_field_listener_records_unused_when_never_touched(db):
    from testapp.models import User

    from django_nplus1 import corpus

    token = setup_context()
    listener = corpus.CorpusFieldListener(parent=None)
    listener.setup()
    tracker = corpus.CorpusFieldTracker()
    corpus._corpus_field_tracker = tracker
    try:
        site = ("/app/views.py", 42, "view")
        signals.send(
            signals.FIELD_LOAD,
            args=(User, "bio", ["User:1"], site),
            kwargs={},
            ret=None,
            context={},
            parser=lambda a, k, c: (a[0], a[1], a[2], a[3]),
        )
    finally:
        listener.teardown()
        teardown_context(token)
        corpus._corpus_field_tracker = None

    assert tracker.unused() == [(User, "bio", site)]


@pytest.fixture
def field_load_events():
    token = setup_context()
    events = []

    def receiver(args=None, kwargs=None, context=None, ret=None, parser=None):
        events.append(parser(args, kwargs, context))

    signals.connect(signals.FIELD_LOAD, receiver)
    yield events
    signals.disconnect(signals.FIELD_LOAD, receiver)
    teardown_context(token)


@pytest.mark.django_db
def test_field_load_emits_when_corpus_enabled(deferred_patch, field_load_events, db):
    from testapp.models import User

    from django_nplus1 import corpus

    User.objects.create(name="A")
    corpus._corpus_enabled = True
    try:
        list(User.objects.all())
    finally:
        corpus._corpus_enabled = False

    assert any(model is User and field == "name" for (model, field, _instances, _site) in field_load_events)


@pytest.mark.django_db
def test_field_load_includes_call_site(deferred_patch, field_load_events, db):
    from testapp.models import User

    from django_nplus1 import corpus

    User.objects.create(name="A")
    corpus._corpus_enabled = True
    try:
        list(User.objects.all())  # ← attribution should point at this line
    finally:
        corpus._corpus_enabled = False

    sites = [site for (*_, site) in field_load_events if site is not None]
    assert any(s[0].endswith("test_corpus_fields.py") for s in sites)


@pytest.mark.django_db
def test_field_load_silent_when_corpus_disabled(deferred_patch, field_load_events, db):
    from testapp.models import User

    User.objects.create(name="A")
    list(User.objects.all())  # corpus disabled, no events
    assert field_load_events == []


@pytest.mark.django_db
def test_field_exclude_skips_emission(deferred_patch, field_load_events, db, settings):
    from testapp.models import User

    from django_nplus1 import corpus

    settings.NPLUS1_FIELD_EXCLUDE = ["testapp.User"]
    User.objects.create(name="A")
    corpus._corpus_enabled = True
    try:
        list(User.objects.all())
    finally:
        corpus._corpus_enabled = False

    assert all(model is not User for (model, *_) in field_load_events)


@pytest.mark.django_db
def test_field_exclude_wildcard_skips_all(deferred_patch, field_load_events, db, settings):
    from testapp.models import User

    from django_nplus1 import corpus

    settings.NPLUS1_FIELD_EXCLUDE = ["testapp.*"]
    User.objects.create(name="A")
    corpus._corpus_enabled = True
    try:
        list(User.objects.all())
    finally:
        corpus._corpus_enabled = False

    assert field_load_events == []


def test_activate_registers_field_listener():
    from django.db.models.query_utils import DeferredAttribute

    from django_nplus1 import corpus, detect

    original_eager = detect.LISTENERS["eager_load"]
    had_field = "field_load" in detect.LISTENERS
    original_field = detect.LISTENERS.get("field_load")
    try:
        corpus.activate()
        assert detect.LISTENERS["field_load"] is corpus.CorpusFieldListener
        assert hasattr(DeferredAttribute, "__set__")
    finally:
        detect.LISTENERS["eager_load"] = original_eager
        if had_field:
            detect.LISTENERS["field_load"] = original_field
        else:
            detect.LISTENERS.pop("field_load", None)
        corpus._corpus_enabled = False
        corpus._corpus_tracker = None
        corpus._corpus_field_tracker = None
        from django_nplus1 import fields as _fields

        _fields._unpatch_deferred_attribute()


def test_activate_resets_field_tracker_on_first_call():
    from django_nplus1 import corpus, detect

    original_eager = detect.LISTENERS["eager_load"]
    original_field = detect.LISTENERS.get("field_load")
    try:
        corpus._corpus_field_tracker = corpus.CorpusFieldTracker()
        site = ("/x.py", 1, "f")
        corpus._corpus_field_tracker.record_load(int, "bio", ["X:1"], site)
        corpus.activate()
        assert corpus.get_field_tracker().unused() == []
    finally:
        detect.LISTENERS["eager_load"] = original_eager
        if original_field is None:
            detect.LISTENERS.pop("field_load", None)
        else:
            detect.LISTENERS["field_load"] = original_field
        corpus._corpus_enabled = False
        corpus._corpus_tracker = None
        corpus._corpus_field_tracker = None
        from django_nplus1 import fields as _fields

        _fields._unpatch_deferred_attribute()


def test_activate_is_idempotent_for_field_tracker():
    from django_nplus1 import corpus, detect

    original_eager = detect.LISTENERS["eager_load"]
    original_field = detect.LISTENERS.get("field_load")
    try:
        corpus.activate()
        site = ("/x.py", 1, "f")
        corpus.get_field_tracker().record_load(int, "bio", ["X:1"], site)
        tracker_before = corpus._corpus_field_tracker
        corpus.activate()  # second call must not reset
        assert corpus._corpus_field_tracker is tracker_before
        assert corpus.get_field_tracker().unused() == [(int, "bio", site)]
    finally:
        detect.LISTENERS["eager_load"] = original_eager
        if original_field is None:
            detect.LISTENERS.pop("field_load", None)
        else:
            detect.LISTENERS["field_load"] = original_field
        corpus._corpus_enabled = False
        corpus._corpus_tracker = None
        corpus._corpus_field_tracker = None
        from django_nplus1 import fields as _fields

        _fields._unpatch_deferred_attribute()


def test_field_load_message_shape():
    from django_nplus1.detect import FieldLoadMessage

    msg = FieldLoadMessage(int, "bio")
    assert msg.label == "unused_field_load"
    assert "`int.bio`" in msg.message
    assert ".only()" in msg.message or ".defer()" in msg.message
