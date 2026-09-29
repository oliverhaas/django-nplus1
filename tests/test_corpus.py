import copy
import json

import pytest
from django.db.models import Prefetch
from testapp.models import Pet, Tag, User

from django_nplus1 import DetectionContext, corpus

pytestmark = pytest.mark.django_db


def findings(label):
    return [(f"{model.__name__}.{field}", funcname) for model, field, (_, _, funcname) in corpus.report(label)]


def load_hobbies():
    return list(User.objects.prefetch_related("hobbies"))


def read_hobbies():
    return [list(user.hobbies.all()) for user in User.objects.prefetch_related("hobbies")]


def load_owners():
    return list(Pet.objects.select_related("user"))


def read_owners():
    return [pet.user for pet in Pet.objects.select_related("user")]


def read_owner_ids():
    return [pet.user_id for pet in Pet.objects.all()]


def list_users():
    return list(User.objects.all())


def read_names():
    return [user.name for user in User.objects.all()]


def hobbies_declared():
    return User.objects.prefetch_related("hobbies")


def hobbies_prefetch_declared():
    return Prefetch("hobbies")


def owners_declared():
    return Pet.objects.select_related("user")


def hobbies_declared_corpus_ignored():
    return User.objects.prefetch_related("hobbies")  # nplus1: corpus-ignore


def hobbies_declared_scope_ignored():
    return User.objects.prefetch_related("hobbies")  # nplus1: ignore


def count_then_list_users():
    users = User.objects.all()
    len(users)
    return list(users)


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        (load_hobbies, [("User.hobbies", "load_hobbies")]),
        (read_hobbies, []),
        (load_owners, [("Pet.user", "load_owners")]),
        (read_owners, []),
    ],
    ids=lambda value: getattr(value, "__name__", None),
)
def test_unused_eager_load_is_reported_at_its_site(objects, corpus_mode, scenario, expected):
    with DetectionContext():
        scenario()
    assert findings("unused_eager_load") == expected


@pytest.mark.parametrize(
    ("queryset", "expected"),
    [
        pytest.param(
            lambda: hobbies_declared().filter(name="alice"),
            [("User.hobbies", "hobbies_declared")],
            id="prefetch-related",
        ),
        pytest.param(
            lambda: User.objects.prefetch_related(hobbies_prefetch_declared()),
            [("User.hobbies", "hobbies_prefetch_declared")],
            id="prefetch-object",
        ),
        pytest.param(
            lambda: owners_declared().filter(user__name="alice"),
            [("Pet.user", "owners_declared")],
            id="select-related",
        ),
    ],
)
def test_unused_eager_load_is_reported_where_it_was_declared(objects, corpus_mode, queryset, expected):
    with DetectionContext():
        list(queryset())
    assert findings("unused_eager_load") == expected


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        (list_users, [("User.name", "list_users")]),
        (read_names, []),
        (load_owners, [("Pet.user_id", "load_owners")]),
        (read_owners, []),
        (read_owner_ids, []),
    ],
    ids=lambda value: getattr(value, "__name__", None),
)
def test_unread_field_is_reported_at_its_site(objects, corpus_mode, scenario, expected):
    with DetectionContext():
        scenario()
    assert findings("unused_field_load") == expected


def test_read_in_another_scope_does_not_count(objects, corpus_mode):
    with DetectionContext():
        load_hobbies()
    with DetectionContext():
        read_hobbies()
    assert findings("unused_eager_load") == [("User.hobbies", "load_hobbies")]


def test_read_in_a_nested_scope_counts(objects, corpus_mode):
    with DetectionContext():
        users = load_hobbies()
        with DetectionContext():
            for user in users:
                list(user.hobbies.all())
    assert findings("unused_eager_load") == []


def test_site_read_in_any_scope_is_used(objects, corpus_mode):
    for read in (False, True):
        with DetectionContext():
            users = load_hobbies()
            if read:
                [list(user.hobbies.all()) for user in users]
    assert findings("unused_eager_load") == []


def test_loads_outside_a_scope_are_not_tracked(objects, corpus_mode):
    load_hobbies()
    assert (findings("unused_eager_load"), findings("unused_field_load")) == ([], [])


@pytest.mark.parametrize(
    ("declare", "expected"),
    [
        (hobbies_declared_corpus_ignored, []),
        (
            hobbies_declared_scope_ignored,
            [("User.hobbies", "hobbies_declared_scope_ignored"), ("User.name", "hobbies_declared_scope_ignored")],
        ),
    ],
    ids=lambda value: getattr(value, "__name__", None),
)
def test_corpus_ignore_comment_on_the_declaration_covers_every_finding(objects, corpus_mode, declare, expected):
    with DetectionContext():
        list(declare())
    assert findings("unused_eager_load") + findings("unused_field_load") == expected


@pytest.mark.parametrize(
    ("patterns", "expected"),
    [
        (["testapp.User"], []),
        (["testapp.*"], []),
        (["User"], [("User.name", "list_users")]),
    ],
)
def test_field_exclude_skips_matching_models(objects, corpus_mode, settings, patterns, expected):
    settings.NPLUS1_FIELD_EXCLUDE = patterns
    with DetectionContext():
        list_users()
    assert findings("unused_field_load") == expected


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"label": "unused_field_load", "model": "testapp.User", "field": "name"}, []),
        ({"model": "testapp.User"}, []),
        ({"label": "unused_eager_load", "model": "testapp.User"}, [("User.name", "list_users")]),
        ({"label": "unused_field_load", "model": "User"}, [("User.name", "list_users")]),
    ],
)
def test_whitelist_applies_to_findings(objects, corpus_mode, settings, entry, expected):
    settings.NPLUS1_WHITELIST = [entry]
    with DetectionContext():
        list_users()
    assert findings("unused_field_load") == expected


def test_queryset_evaluated_twice_is_one_site(objects, corpus_mode):
    with DetectionContext():
        count_then_list_users()
    assert findings("unused_field_load") == [("User.name", "count_then_list_users")]


def rename_and_reload(tag):
    tag.label = "carol"
    tag.save()
    return Tag.objects.get(pk=tag.pk).label


def refresh_after_update(tag):
    Tag.objects.filter(pk=tag.pk).update(label="carol")
    tag.refresh_from_db()
    return tag.label


def read_deferred_label(tag):
    return Tag.objects.only("id").get(pk=tag.pk).label


def rename_copy(tag):
    duplicate = copy.copy(tag)
    duplicate.label = "carol"
    return tag.label, duplicate.label


def delete_loaded_label(tag):
    del tag.label
    return tag.label


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        (rename_and_reload, "carol"),
        (refresh_after_update, "carol"),
        (read_deferred_label, "alice"),
        (rename_copy, ("alice", "carol")),
        (delete_loaded_label, "alice"),
    ],
    ids=lambda value: getattr(value, "__name__", None),
)
def test_model_fields_behave_as_without_corpus_mode(objects, corpus_mode, scenario, expected):
    with DetectionContext():
        tag = Tag.objects.get(label="alice")
        assert scenario(tag) == expected


def test_deactivate_restores_per_scope_detection(objects, detected):
    corpus.activate()
    corpus.deactivate()
    with DetectionContext():
        load_hobbies()
    assert [(m.label, f"{m.model.__name__}.{m.field}") for m in detected] == [("unused_eager_load", "User.hobbies")]
    assert (findings("unused_eager_load"), findings("unused_field_load")) == ([], [])


def test_findings_survive_serialization(objects, corpus_mode):
    with DetectionContext():
        list_users()
    with DetectionContext():
        read_names()
    payload = json.loads(json.dumps(corpus.serialize()))
    corpus.activate()
    corpus.merge(payload)
    assert findings("unused_field_load") == [("User.name", "list_users")]


def test_findings_of_unknown_models_are_skipped(corpus_mode):
    site = ["/project/views.py", 3, "view"]
    corpus.merge({"unused_field_load": {"loaded": [["__fake__.User", "name", site]], "used": []}})
    assert corpus.report("unused_field_load") == []
