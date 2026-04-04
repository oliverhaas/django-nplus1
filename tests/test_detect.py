import pytest
from testapp import models


@pytest.mark.django_db
class TestOneToOne:
    def test_one_to_one(self, objects, calls):
        occupation = models.Occupation.objects.first()
        occupation.user
        assert len(calls) == 1
        call = calls[0]
        assert call == (models.Occupation, f"Occupation:{occupation.pk}", "user")

    def test_one_to_one_select(self, objects, calls):
        occupation = models.Occupation.objects.select_related("user").first()
        occupation.user
        assert len(calls) == 0

    def test_one_to_one_prefetch(self, objects, calls):
        occupation = models.Occupation.objects.prefetch_related("user").first()
        occupation.user
        assert len(calls) == 0

    def test_one_to_one_reverse(self, objects, calls):
        user = models.User.objects.first()
        user.occupation
        assert len(calls) == 1
        call = calls[0]
        assert call == (models.User, f"User:{user.pk}", "occupation")


@pytest.mark.django_db
class TestManyToOne:
    def test_many_to_one(self, objects, calls):
        address = models.Address.objects.first()
        address.user
        assert len(calls) == 1
        call = calls[0]
        assert call == (models.Address, f"Address:{address.pk}", "user")

    def test_many_to_one_select(self, objects, calls):
        address = list(models.Address.objects.select_related("user").all())
        address[0].user
        assert len(calls) == 0

    def test_many_to_one_prefetch(self, objects, calls):
        address = list(models.Address.objects.prefetch_related("user").all())
        address[0].user
        assert len(calls) == 0

    def test_many_to_one_reverse(self, objects, calls):
        user = models.User.objects.first()
        user.addresses.first()
        assert len(calls) == 1
        call = calls[0]
        assert call == (models.User, f"User:{user.pk}", "addresses")

    def test_many_to_one_reverse_no_related_name(self, objects, calls):
        user = models.User.objects.first()
        user.pet_set.first()
        assert len(calls) == 1
        call = calls[0]
        assert call == (models.User, f"User:{user.pk}", "pet_set")


@pytest.mark.django_db
class TestManyToMany:
    def test_many_to_many(self, objects, calls):
        users = models.User.objects.all()
        list(users[0].hobbies.all())
        assert len(calls) == 1
        call = calls[0]
        assert call == (models.User, f"User:{users[0].pk}", "hobbies")

    def test_many_to_many_prefetch(self, objects, calls):
        users = models.User.objects.all().prefetch_related("hobbies")
        list(users[0].hobbies.all())
        assert len(calls) == 0

    def test_many_to_many_reverse(self, objects, calls):
        hobbies = models.Hobby.objects.all()
        list(hobbies[0].users.all())
        assert len(calls) == 1
        call = calls[0]
        assert call == (models.Hobby, f"Hobby:{hobbies[0].pk}", "users")

    def test_many_to_many_reverse_prefetch(self, objects, calls):
        hobbies = models.Hobby.objects.all().prefetch_related("users")
        list(hobbies[0].users.all())
        assert len(calls) == 0

    def test_many_to_many_reverse_no_related_name(self, objects, calls):
        pet = models.Pet.objects.first()
        pet.allergy_set.first()
        assert len(calls) == 1
        call = calls[0]
        assert call == (models.Pet, f"Pet:{pet.pk}", "allergy_set")


@pytest.mark.django_db
class TestCallerInfo:
    def test_lazy_load_message_includes_caller(self, objects, lazy_listener):
        """LazyLoadMessage includes filename, line, and function."""
        users = list(models.User.objects.all())
        list(users[0].hobbies.all())  # triggers lazy load
        assert lazy_listener.parent.notify.called
        message = lazy_listener.parent.notify.call_args[0][0]
        # The message should contain caller info
        assert "test_lazy_load_message_includes_caller" in message.message
        assert ".py:" in message.message


@pytest.mark.django_db
def test_values(objects, lazy_listener):
    list(models.User.objects.values("id"))
