import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from testapp.models import Pet, Tag, User

from django_nplus1 import DetectionContext

try:
    from django.core.exceptions import FieldFetchBlocked
    from django.db.models import FETCH_PEERS, FETCH_RAISE
except ImportError:
    pytest.skip("Fetch modes need Django 6.1", allow_module_level=True)

pytestmark = pytest.mark.django_db


def read_users_of_pets():
    return [pet.user for pet in Pet.objects.fetch_mode(FETCH_PEERS)]


def read_deferred_names():
    return [user.name for user in User.objects.only("id").fetch_mode(FETCH_PEERS)]


def read_occupations():
    return [user.occupation for user in User.objects.fetch_mode(FETCH_PEERS)]


def read_tagged_objects():
    return [tag.content_object for tag in Tag.objects.fetch_mode(FETCH_PEERS)]


@pytest.mark.parametrize(
    "loop",
    [read_users_of_pets, read_deferred_names, read_occupations, read_tagged_objects],
    ids=lambda loop: loop.__name__,
)
def test_fetch_peers_loops_are_not_reported(objects, detected, loop):
    with CaptureQueriesContext(connection) as queries, DetectionContext():
        loop()
        loop()
    assert len(queries) == 4
    assert detected == []


def test_fetch_peers_leaves_many_to_many_per_row(objects, detected):
    with DetectionContext():
        [list(user.hobbies.all()) for user in User.objects.fetch_mode(FETCH_PEERS)]
    assert [(m.label, m.model, m.field) for m in detected] == [("n_plus_one", User, "hobbies")]


@pytest.mark.parametrize(
    "read",
    [
        pytest.param(lambda: [user.name for user in User.objects.only("id").fetch_mode(FETCH_RAISE)], id="deferred"),
        pytest.param(lambda: [pet.user for pet in Pet.objects.fetch_mode(FETCH_RAISE)], id="fk"),
    ],
)
def test_blocked_fetch_is_not_a_load(objects, detected, settings, read):
    settings.NPLUS1_THRESHOLD = 1
    with pytest.raises(FieldFetchBlocked), DetectionContext():
        read()
    assert detected == []
