import contextlib
import copy
import gc
import importlib
import pickle
import sys
import weakref
from pathlib import Path

import pytest
from django.contrib.auth.models import User as AuthUser
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.db.models import Prefetch, prefetch_related_objects
from django.template import engines
from testapp.models import Allergy, Company, Hobby, Occupation, Pet, Tag, User

from django_nplus1 import DetectionContext, NPlus1Error, Profiler, signals

pytestmark = pytest.mark.django_db

NAME_SQL = "SELECT name FROM testapp_user WHERE id = %s"


def occupation_users():
    return [occupation.user for occupation in Occupation.objects.all()]


def get_each_user():
    return [User.objects.get(pk=user.pk) for user in User.objects.all()]


def get_missing_users():
    for pk in (-1, -2):
        with contextlib.suppress(User.DoesNotExist):
            User.objects.get(pk=pk)


def select_each_name(sql=NAME_SQL):
    for pk in User.objects.values_list("pk", flat=True):
        with connection.cursor() as cursor:
            cursor.execute(sql, [pk])


def prefetch_per_row():
    for user in User.objects.all():
        prefetch_related_objects([user], "hobbies")
        list(user.hobbies.all())


def prefetch_pets_without_owner_column():
    pets = Prefetch("pet_set", queryset=Pet.objects.only("id"))
    return [list(user.pet_set.all()) for user in User.objects.prefetch_related(pets)]


class ComposedSQL:
    def __init__(self, text):
        self.text = text

    def as_string(self, context):
        return self.text


def execute_as_text(execute, sql, params, many, context):
    if isinstance(sql, bytes):
        sql = sql.decode()
    elif isinstance(sql, ComposedSQL):
        sql = sql.as_string(context["cursor"].cursor)
    return execute(sql, params, many, context)


@pytest.mark.parametrize(
    ("load", "model", "field"),
    [
        pytest.param(lambda: [pet.user for pet in Pet.objects.all()], Pet, "user", id="forward-fk"),
        pytest.param(occupation_users, Occupation, "user", id="forward-o2o"),
        pytest.param(lambda: [user.occupation for user in User.objects.all()], User, "occupation", id="reverse-o2o"),
        pytest.param(
            lambda: [list(user.addresses.all()) for user in User.objects.all()],
            User,
            "addresses",
            id="reverse-fk",
        ),
        pytest.param(
            lambda: [user.addresses.first() for user in User.objects.all()],
            User,
            "addresses",
            id="reverse-fk-first",
        ),
        pytest.param(lambda: [list(user.pet_set.all()) for user in User.objects.all()], User, "pet_set", id="pet-set"),
        pytest.param(lambda: [list(user.hobbies.all()) for user in User.objects.all()], User, "hobbies", id="m2m"),
        pytest.param(lambda: [list(hobby.users.all()) for hobby in Hobby.objects.all()], Hobby, "users", id="m2m-back"),
        pytest.param(lambda: [list(a.pets.all()) for a in Allergy.objects.all()], Allergy, "pets", id="m2m-unnamed"),
        pytest.param(
            lambda: [list(pet.allergy_set.all()) for pet in Pet.objects.all()],
            Pet,
            "allergy_set",
            id="m2m-unnamed-back",
        ),
        pytest.param(lambda: [list(user.tags.all()) for user in User.objects.all()], User, "tags", id="generic-rel"),
        pytest.param(lambda: [tag.content_object for tag in Tag.objects.all()], Tag, "content_object", id="generic-fk"),
        pytest.param(lambda: [user.name for user in User.objects.only("id")], User, "name", id="only"),
        pytest.param(lambda: [user.name for user in User.objects.defer("name")], User, "name", id="defer"),
        pytest.param(lambda: [o.user for o in Occupation.objects.iterator()], Occupation, "user", id="iterator"),
        pytest.param(prefetch_per_row, User, "hobbies", id="prefetch-per-row"),
        pytest.param(
            lambda: [pet.user for pet in Pet.objects.only("id").prefetch_related("user")],
            Pet,
            "user",
            id="prefetch-reads-deferred-fk",
        ),
        pytest.param(
            lambda: [pet.user for pet in Pet.objects.only("id").prefetch_related("user").iterator(chunk_size=10)],
            Pet,
            "user",
            id="iterator-prefetch-reads-deferred-fk",
        ),
        pytest.param(prefetch_pets_without_owner_column, Pet, "user", id="prefetch-queryset-defers-fk"),
    ],
)
def test_per_row_load_is_detected(objects, detected, load, model, field):
    with DetectionContext():
        load()
    assert [(m.label, m.model, m.field) for m in detected] == [("n_plus_one", model, field)]


def read_selected_users():
    for pet in Pet.objects.select_related("user"):
        pet.user


def read_prefetched_hobbies():
    for user in User.objects.prefetch_related("hobbies"):
        list(user.hobbies.all())


def read_nested_selected():
    for pet in Pet.objects.select_related("user__occupation"):
        pet.user.occupation


def read_nested_prefetched():
    for pet in Pet.objects.prefetch_related("user__occupation"):
        pet.user.occupation


def read_prefetched_generic_fk():
    for tag in Tag.objects.prefetch_related("content_object"):
        tag.content_object


def read_prefetched_generic_relation():
    for user in User.objects.prefetch_related("tags"):
        list(user.tags.all())


def read_hobbies_of_fetched_users():
    alice = User.objects.get(name="alice")
    bob = User.objects.get(name="bob")
    for user in (alice, bob):
        list(user.hobbies.all())


def read_owners_of_first_and_last():
    first = Occupation.objects.order_by("pk").first()
    last = Occupation.objects.order_by("-pk").first()
    for occupation in (first, last):
        occupation.user


def refetch_loaded_users_with_prefetch():
    list(User.objects.all())
    alice = User.objects.prefetch_related("hobbies").get(name="alice")
    bob = User.objects.prefetch_related("hobbies").get(name="bob")
    for user in (alice, bob):
        list(user.hobbies.all())


def prefetch_fetched_users_one_by_one():
    alice = User.objects.get(name="alice")
    bob = User.objects.get(name="bob")
    prefetch_related_objects([alice], "hobbies")
    prefetch_related_objects([bob], "hobbies")
    for user in (alice, bob):
        list(user.hobbies.all())


def prefetch_all_users():
    users = list(User.objects.all())
    prefetch_related_objects(users, "hobbies")
    for user in users:
        list(user.hobbies.all())


def prefetch_converging_chains():
    companies = list(Company.objects.all())
    prefetch_related_objects(companies, "main_store__region", "backup_store__region")
    for company in companies:
        company.main_store.region
        company.backup_store.region


def render_prefetched_hobbies():
    template = engines["django"].from_string(
        "{% for user in users %}{% for hobby in user.hobbies.all %}{{ hobby.pk }}{% endfor %}{% endfor %}",
    )
    template.render({"users": User.objects.prefetch_related("hobbies")})


def list_values_across_m2m():
    list(User.objects.values("name", "hobbies__id"))


def reselect_loaded_users():
    list(User.objects.all())
    for user in User.objects.select_related("occupation"):
        user.occupation


def read_one_user_through_two_instances():
    alone = User.objects.get(name="alice")
    (listed,) = User.objects.filter(name="alice")
    for user in (alone, listed):
        user.occupation


@pytest.mark.parametrize(
    "scenario",
    [
        read_selected_users,
        read_prefetched_hobbies,
        read_nested_selected,
        read_nested_prefetched,
        read_prefetched_generic_fk,
        read_prefetched_generic_relation,
        read_hobbies_of_fetched_users,
        read_owners_of_first_and_last,
        refetch_loaded_users_with_prefetch,
        prefetch_fetched_users_one_by_one,
        prefetch_all_users,
        prefetch_converging_chains,
        render_prefetched_hobbies,
        list_values_across_m2m,
        reselect_loaded_users,
        read_one_user_through_two_instances,
    ],
    ids=lambda scenario: scenario.__name__,
)
def test_batched_or_single_loads_are_not_reported(objects, shared_fk_objects, scenario):
    with Profiler():
        scenario()


def test_deferred_field_of_rows_fetched_one_by_one_is_detected(objects, detected):
    with DetectionContext():
        alice = User.objects.only("id").get(name="alice")
        bob = User.objects.only("id").get(name="bob")
        for user in (alice, bob):
            user.name
    assert [(m.label, m.model, m.field) for m in detected] == [("n_plus_one", User, "name")]


def test_rows_of_a_same_named_model_do_not_count(objects, detected):
    for user in objects:
        AuthUser.objects.create(pk=user.pk, username=user.name)
    with DetectionContext():
        list(AuthUser.objects.all())
        for user in objects:
            list(user.hobbies.all())
    assert detected == []


@pytest.mark.parametrize("loop", [get_each_user, get_missing_users], ids=["found", "missing"])
def test_get_in_loop_is_detected(objects, detected, loop):
    with DetectionContext():
        loop()
    assert [(m.label, m.model, m.field) for m in detected] == [("get_in_loop", User, "get()")]


LOOKUPS = """\
from testapp.models import User


def flag(name):
    try:
        return User.objects.get(name=name)
    except User.DoesNotExist:
        return User.objects.get_or_create(name=name)[0]


def find(path):
    try:
        return User.objects.get(name=path)
    except User.DoesNotExist:
        return None


def redirect(path):
    found = find(path)
    if found is None and "?" in path:
        found = find(path.partition("?")[0])
    return found
"""


@pytest.fixture
def installed_lookups(tmp_path, monkeypatch):
    """A third-party module that looks a row up again another way when the first lookup finds none."""
    directory = tmp_path / "site-packages"
    directory.mkdir()
    (directory / "installed_lookups.py").write_text(LOOKUPS)
    monkeypatch.syspath_prepend(directory)
    yield importlib.import_module("installed_lookups")
    sys.modules.pop("installed_lookups", None)


@pytest.mark.parametrize(
    ("lookup", "expected"),
    [
        pytest.param(lambda lookups: lookups.flag("missing"), [], id="create-missing"),
        pytest.param(lambda lookups: lookups.redirect("/missing/?x=1"), [], id="retry-without-query"),
        pytest.param(
            lambda lookups: [lookups.flag(name) for name in ("a", "b")],
            [("get_in_loop", User, "get()")],
            id="in-a-loop",
        ),
    ],
)
def test_library_fallback_lookups_are_a_get_loop_only_when_called_in_a_loop(
    detected,
    installed_lookups,
    lookup,
    expected,
):
    with DetectionContext():
        lookup(installed_lookups)
    assert [(m.label, m.model, m.field) for m in detected] == expected


def test_rows_fetched_one_by_one_count_again_when_loaded_together(objects, detected):
    with DetectionContext():
        [pet.user for pet in Pet.objects.all()]
        [user.occupation for user in User.objects.all()]
    assert [(m.model, m.field) for m in detected] == [(Pet, "user"), (User, "occupation")]


@pytest.mark.parametrize(
    ("setting", "label", "loop"),
    [
        ("NPLUS1_THRESHOLD", "n_plus_one", occupation_users),
        ("NPLUS1_GET_THRESHOLD", "get_in_loop", get_each_user),
        ("NPLUS1_DUPLICATE_QUERY_THRESHOLD", "duplicate_query", select_each_name),
    ],
)
@pytest.mark.parametrize(("threshold", "expected"), [(2, 1), (3, 0)])
def test_threshold_sets_the_repetitions_needed(objects, detected, settings, setting, label, loop, threshold, expected):
    settings.NPLUS1_DETECT_DUPLICATE_QUERIES = True
    setattr(settings, setting, threshold)
    with DetectionContext():
        loop()
    assert [m.label for m in detected].count(label) == expected


@pytest.mark.parametrize(("enabled", "expected"), [(True, ["duplicate_query"]), (False, [])])
def test_duplicate_query_detection_follows_setting(objects, detected, settings, enabled, expected):
    settings.NPLUS1_DETECT_DUPLICATE_QUERIES = enabled
    with DetectionContext():
        select_each_name()
    assert [m.label for m in detected] == expected


@pytest.mark.parametrize("convert", [str.encode, ComposedSQL], ids=["bytes", "composed"])
def test_duplicate_query_reads_sql_that_is_not_str(objects, detected, settings, convert):
    settings.NPLUS1_DETECT_DUPLICATE_QUERIES = True
    with DetectionContext(), connection.execute_wrapper(execute_as_text):
        select_each_name(convert(NAME_SQL))
    assert [(m.label, m.field) for m in detected] == [("duplicate_query", NAME_SQL)]


@pytest.mark.parametrize("name", ["NPLUS1_THRESHOLD", "NPLUS1_GET_THRESHOLD", "NPLUS1_DUPLICATE_QUERY_THRESHOLD"])
@pytest.mark.parametrize("value", [0, -1, "2", True, 1.5])
def test_invalid_threshold_fails_at_scope_entry(settings, name, value):
    settings.NPLUS1_DETECT_DUPLICATE_QUERIES = True
    setattr(settings, name, value)
    with pytest.raises(ImproperlyConfigured, match=name), Profiler():
        pass
    assert not signals.active()


def test_reported_callers_stop_growing(objects, detected, settings):
    settings.NPLUS1_SHOW_ALL_CALLERS = True
    with DetectionContext():
        occupation_users()
        occupation_users()
    assert [len(m.callers) for m in detected] == [2]


def test_detection_names_the_loading_line(objects):
    with (
        pytest.raises(NPlus1Error, match=r"`Occupation\.user` at .+test_detect\.py:\d+ in occupation_users"),
        Profiler(),
    ):
        occupation_users()


@pytest.fixture
def installed_views(tmp_path, monkeypatch):
    """A module of a project package that is installed into site-packages, as in a Docker image."""
    package = tmp_path / "site-packages" / "installed_project"
    package.mkdir(parents=True)
    (package / "__init__.py").touch()
    (package / "views.py").write_text(
        "from testapp.models import Occupation\n\n\n"
        "def occupation_users():\n"
        "    return [occupation.user for occupation in Occupation.objects.all()]\n",
    )
    monkeypatch.syspath_prepend(package.parent)
    yield importlib.import_module("installed_project.views")
    for name in ("installed_project.views", "installed_project"):
        sys.modules.pop(name, None)


@pytest.mark.parametrize(("packages", "file"), [([], "test_detect.py"), (["installed_project"], "views.py")])
def test_project_packages_are_project_code_in_site_packages(
    objects,
    detected,
    settings,
    installed_views,
    packages,
    file,
):
    settings.NPLUS1_PROJECT_PACKAGES = packages
    with DetectionContext():
        installed_views.occupation_users()
    assert [Path(m.caller[0]).name for m in detected] == [file]


@pytest.mark.parametrize(
    "clone",
    [lambda queryset: pickle.loads(pickle.dumps(queryset)), copy.deepcopy],  # noqa: S301
    ids=["pickle", "deepcopy"],
)
def test_relation_queryset_can_be_copied(objects, clone):
    with Profiler():
        hobbies = objects[0].hobbies.all()
        assert list(clone(hobbies)) == list(hobbies)


def test_prefetched_to_attr_list_pickles(objects):
    with Profiler():
        user = User.objects.prefetch_related(Prefetch("hobbies", to_attr="hobby_list")).get(name="alice")
        restored = pickle.loads(pickle.dumps(user))  # noqa: S301
        assert restored.hobby_list == list(user.hobby_list)


def test_prefetched_instance_can_be_deepcopied(objects):
    with Profiler():
        user = User.objects.prefetch_related("hobbies").get(name="alice")
        copied = copy.deepcopy(user)
        assert list(copied.hobbies.all()) == list(user.hobbies.all())


@pytest.mark.parametrize(("relation", "count"), [("hobbies", 2), ("pet_set", 1)])
def test_related_manager_with_named_manager(objects, relation, count):
    with Profiler():
        assert len(getattr(objects[0], relation)(manager="objects").all()) == count


def test_prefetched_relation_read_many_times(objects):
    with Profiler():
        user = User.objects.prefetch_related("hobbies").get(name="alice")
        for _ in range(sys.getrecursionlimit()):
            user.hobbies.all()
        assert len(user.hobbies.all()) == 2


def test_relation_queryset_is_freed_without_garbage_collection(objects):
    gc.disable()
    try:
        with Profiler():
            hobbies = objects[0].hobbies.all()
            list(hobbies)
            ref = weakref.ref(hobbies)
            del hobbies
            assert ref() is None
    finally:
        gc.enable()


def test_prefetch_related_objects_imported_before_setup(django_pytester, monkeypatch):
    django_pytester.makepyfile(
        early_helper="""
        from django.db.models import prefetch_related_objects


        def prefetch_stores(companies):
            prefetch_related_objects(companies, "main_store__region", "backup_store__region")
        """,
        early_settings="""
        import early_helper
        from settings.base import *
        """,
    )
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "early_settings")
    django_pytester.makepyfile(
        """
        import early_helper
        import pytest
        from testapp.models import Company, Region, Store

        from django_nplus1 import Profiler


        @pytest.mark.django_db
        def test_converging_prefetch():
            Company.objects.create(
                main_store=Store.objects.create(region=Region.objects.create()),
                backup_store=Store.objects.create(region=Region.objects.create()),
            )
            with Profiler():
                companies = list(Company.objects.all())
                early_helper.prefetch_stores(companies)
                for company in companies:
                    company.main_store.region
                    company.backup_store.region
        """,
    )
    result = django_pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
