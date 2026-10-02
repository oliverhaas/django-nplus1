import pytest
from django.db.models import FilteredRelation, Prefetch, Q
from testapp.models import Child, Node, Pet, PetProxy, Tag, User

from django_nplus1 import DetectionContext, Profiler

pytestmark = pytest.mark.django_db


def with_hobby_list():
    return User.objects.prefetch_related(Prefetch("hobbies", to_attr="hobby_list"))


@pytest.mark.parametrize(
    ("queryset", "expected"),
    [
        pytest.param(lambda: Pet.objects.select_related("user"), ["Pet.user"], id="select-fk"),
        pytest.param(lambda: Pet.objects.select_related("user").iterator(), ["Pet.user"], id="select-iterator"),
        pytest.param(lambda: User.objects.select_related("occupation"), ["User.occupation"], id="select-reverse-o2o"),
        pytest.param(
            lambda: Pet.objects.select_related("user__occupation"),
            ["Pet.user", "User.occupation"],
            id="select-nested",
        ),
        pytest.param(lambda: User.objects.prefetch_related("hobbies"), ["User.hobbies"], id="prefetch-m2m"),
        pytest.param(lambda: User.objects.prefetch_related("occupation"), ["User.occupation"], id="prefetch-o2o"),
        pytest.param(
            lambda: Pet.objects.prefetch_related("user__occupation"),
            ["Pet.user", "User.occupation"],
            id="prefetch-nested",
        ),
        pytest.param(lambda: User.objects.prefetch_related("tags"), ["User.tags"], id="generic-relation"),
        pytest.param(with_hobby_list, ["User.hobby_list"], id="to-attr"),
        pytest.param(lambda: Tag.objects.prefetch_related("content_object"), ["Tag.content_object"], id="generic-fk"),
    ],
)
def test_unused_eager_load_is_detected(objects, detected, queryset, expected):
    with DetectionContext():
        list(queryset())
    assert sorted((m.label, f"{m.model.__name__}.{m.field}") for m in detected) == [
        ("unused_eager_load", name) for name in expected
    ]


def read_selected_user():
    for pet in Pet.objects.select_related("user"):
        pet.user


def read_selected_occupation():
    for user in User.objects.select_related("occupation"):
        user.occupation


def read_nested_selected():
    for pet in Pet.objects.select_related("user__occupation"):
        pet.user.occupation


def read_prefetched_hobbies():
    for user in User.objects.prefetch_related("hobbies"):
        list(user.hobbies.all())


def read_prefetched_occupation():
    for user in User.objects.prefetch_related("occupation"):
        user.occupation


def read_nested_prefetched():
    for pet in Pet.objects.prefetch_related("user__occupation"):
        pet.user.occupation


def read_prefetched_tags():
    for user in User.objects.prefetch_related("tags"):
        list(user.tags.all())


def read_prefetched_content_object():
    for tag in Tag.objects.prefetch_related("content_object"):
        tag.content_object


def iterate_hobby_list():
    for user in with_hobby_list():
        list(user.hobby_list)


def measure_hobby_list():
    for user in with_hobby_list():
        len(user.hobby_list)


def index_hobby_list():
    for user in with_hobby_list():
        user.hobby_list[0]


def search_hobby_list():
    return [None in user.hobby_list for user in with_hobby_list()]


def reverse_hobby_list():
    for user in with_hobby_list():
        list(reversed(user.hobby_list))


def count_prefetched_hobbies():
    for user in User.objects.prefetch_related("hobbies"):
        user.hobbies.count()


def check_prefetched_addresses():
    for user in User.objects.prefetch_related("addresses"):
        user.addresses.exists()


def read_one_row_of_the_group():
    users = list(User.objects.prefetch_related("hobbies"))
    list(users[0].hobbies.all())


def read_first_row_while_iterating():
    for index, pet in enumerate(Pet.objects.select_related("user").order_by("pk").iterator()):
        if index == 0:
            pet.user


def load_no_rows():
    list(User.objects.filter(name="nobody").select_related("occupation").prefetch_related("hobbies"))


def read_user_of_proxy():
    for pet in PetProxy.objects.select_related("user"):
        pet.user


def read_owner_of_mti_child():
    for child in Child.objects.select_related("owner"):
        child.owner


def read_child_of_self_relation():
    for node in Node.objects.filter(parent__isnull=True).select_related("child"):
        node.child


def read_filtered_relation():
    owners = Pet.objects.annotate(owner=FilteredRelation("user", condition=Q(user__name="alice")))
    for pet in owners.select_related("owner"):
        pet.owner


@pytest.mark.parametrize(
    "scenario",
    [
        read_selected_user,
        read_selected_occupation,
        read_nested_selected,
        read_prefetched_hobbies,
        read_prefetched_occupation,
        read_nested_prefetched,
        read_prefetched_tags,
        read_prefetched_content_object,
        iterate_hobby_list,
        measure_hobby_list,
        index_hobby_list,
        search_hobby_list,
        reverse_hobby_list,
        count_prefetched_hobbies,
        check_prefetched_addresses,
        read_one_row_of_the_group,
        read_first_row_while_iterating,
        load_no_rows,
        read_user_of_proxy,
        read_owner_of_mti_child,
        read_child_of_self_relation,
        read_filtered_relation,
    ],
    ids=lambda scenario: scenario.__name__,
)
def test_used_eager_load_is_not_reported(objects, scenario):
    for user in objects:
        Child.objects.create(owner=user)
        Node.objects.create(parent=Node.objects.create())
    with Profiler():
        scenario()
