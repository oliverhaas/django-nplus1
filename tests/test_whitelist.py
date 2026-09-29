import pytest
from django.db import connection
from testapp.models import Child, Occupation, Pet, PetProxy, User

from django_nplus1 import DetectionContext, Profiler, nplus1_allow

pytestmark = pytest.mark.django_db

BRACKET_SQL = "SELECT name FROM testapp_user WHERE [id] = %s"


def occupation_users():
    return [occupation.user for occupation in Occupation.objects.all()]


def user_hobbies():
    return [list(user.hobbies.all()) for user in User.objects.all()]


def get_each_user():
    return [User.objects.get(pk=user.pk) for user in User.objects.all()]


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"model": "User"}, []),
        ({"model": "testapp.User"}, []),
        ({"model": "testapp.*"}, []),
        ({"model": User}, []),
        ({"model": "User", "field": "hobbies"}, []),
        ({"field": "hob*"}, []),
        ({"label": "n_plus_one"}, []),
        ({"model": "auth.User"}, ["User.hobbies"]),
        ({"model": "User", "field": "occupation"}, ["User.hobbies"]),
        ({"label": "unused_eager_load"}, ["User.hobbies"]),
    ],
)
def test_whitelist_entry(objects, detected, entry, expected):
    with DetectionContext(whitelist=[entry]):
        user_hobbies()
    assert [f"{m.model.__name__}.{m.field}" for m in detected] == expected


@pytest.mark.parametrize(
    ("entry", "load"),
    [
        ({"model": "Pet"}, lambda: [pet.user for pet in PetProxy.objects.all()]),
        ({"model": Pet}, lambda: [pet.user for pet in PetProxy.objects.all()]),
        ({"model": "testapp.Base"}, lambda: [child.owner for child in Child.objects.all()]),
    ],
    ids=["proxy-by-name", "proxy-by-class", "mti-child"],
)
def test_parent_model_entry_covers_subclasses(objects, entry, load):
    for user in objects:
        Child.objects.create(owner=user)
    with Profiler(whitelist=[entry]):
        load()


def test_whitelist_covers_deferred_field(objects):
    with Profiler(whitelist=[{"model": "User", "field": "name"}]):
        [user.name for user in User.objects.only("id")]


@pytest.mark.parametrize(
    ("field", "expected"),
    [(BRACKET_SQL, []), ("SELECT name FROM testapp_user *", []), ("SELECT id *", ["duplicate_query"])],
)
def test_duplicate_query_whitelist_matches_sql(objects, detected, settings, field, expected):
    settings.NPLUS1_DETECT_DUPLICATE_QUERIES = True
    with DetectionContext(whitelist=[{"label": "duplicate_query", "field": field}]):
        for pk in User.objects.values_list("pk", flat=True):
            with connection.cursor() as cursor:
                cursor.execute(BRACKET_SQL, [pk])
    assert [m.label for m in detected] == expected


@pytest.mark.parametrize(
    "load",
    [occupation_users, get_each_user, lambda: list(User.objects.select_related("occupation"))],
    ids=["lazy-load", "get-in-loop", "unused-eager-load"],
)
def test_allow_without_arguments_suppresses_everything(objects, load):
    with Profiler(), nplus1_allow():
        load()


@pytest.mark.parametrize(
    ("whitelist", "expected"),
    [
        ([{"model": "Occupation"}], []),
        ([{"model": "Occupation", "field": "user"}], []),
        ([{"model": "User"}], ["Occupation.user"]),
        ([{"model": "Occupation", "field": "user_id"}], ["Occupation.user"]),
        ([], ["Occupation.user"]),
    ],
)
def test_allow_suppresses_matching_detections(objects, detected, whitelist, expected):
    with DetectionContext(), nplus1_allow(whitelist):
        occupation_users()
    assert [f"{m.model.__name__}.{m.field}" for m in detected] == expected


@pytest.mark.parametrize("whitelist", [None, [{"model": "User", "field": "occupation"}]])
def test_allowed_eager_load_stays_allowed_after_the_block(objects, whitelist):
    with Profiler(), nplus1_allow(whitelist):
        list(User.objects.select_related("occupation"))


def test_allow_rules_end_with_their_block(objects, detected):
    with DetectionContext(), nplus1_allow([{"model": "User"}]):
        with nplus1_allow([{"model": "Occupation"}]):
            occupation_users()
        user_hobbies()
        occupation_users()
    assert [f"{m.model.__name__}.{m.field}" for m in detected] == ["Occupation.user"]


def ignore_all():
    return [occupation.user for occupation in Occupation.objects.all()]  # nplus1: ignore


def ignore_n_plus_one():
    return [occupation.user for occupation in Occupation.objects.all()]  # nplus1: ignore[n_plus_one]


def ignore_both_labels():
    return [occupation.user for occupation in Occupation.objects.all()]  # nplus1: ignore[get_in_loop, n_plus_one]


def ignore_get_in_loop():
    return [User.objects.get(pk=user.pk) for user in User.objects.all()]  # nplus1: ignore[get_in_loop]


def ignore_other_label():
    return [occupation.user for occupation in Occupation.objects.all()]  # nplus1: ignore[get_in_loop]


def unrelated_comment():
    return [occupation.user for occupation in Occupation.objects.all()]  # the owner of each occupation


@pytest.mark.parametrize(
    ("load", "expected"),
    [
        (ignore_all, []),
        (ignore_n_plus_one, []),
        (ignore_both_labels, []),
        (ignore_get_in_loop, []),
        (ignore_other_label, ["Occupation.user"]),
        (unrelated_comment, ["Occupation.user"]),
    ],
    ids=lambda value: getattr(value, "__name__", None),
)
def test_inline_ignore_comment(objects, detected, load, expected):
    with DetectionContext():
        load()
    assert [f"{m.model.__name__}.{m.field}" for m in detected] == expected


@pytest.mark.parametrize("show_all_callers", [False, True])
def test_ignored_line_does_not_hide_other_lines(objects, detected, settings, show_all_callers):
    settings.NPLUS1_SHOW_ALL_CALLERS = show_all_callers
    with DetectionContext():
        ignore_all()
        occupation_users()
    assert [f"{m.model.__name__}.{m.field}" for m in detected] == ["Occupation.user"]
