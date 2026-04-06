import pytest

from django_nplus1.detect import nplus1_allow
from django_nplus1.exceptions import NPlus1Error
from django_nplus1.profiler import Profiler


@pytest.mark.django_db
class TestProfiler:
    def test_profiler_detects_nplus1(self, objects):
        from testapp.models import Occupation

        with pytest.raises(NPlus1Error, match="Occupation.user"), Profiler():
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_profiler_no_false_positive_on_get(self, objects):
        from testapp.models import User

        with Profiler():
            user = User.objects.get(pk=1)
            user.hobbies.all()

    def test_profiler_no_false_positive_on_first(self, objects):
        from testapp.models import Occupation

        with Profiler():
            occupation = Occupation.objects.first()
            occupation.user

    def test_profiler_whitelist(self, objects):
        from testapp.models import Occupation

        with Profiler(whitelist=[{"model": "Occupation"}]):
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_profiler_detects_prefetch_related_objects_loop(self, objects):
        from django.db.models import prefetch_related_objects
        from testapp.models import User

        with pytest.raises(NPlus1Error, match="n\\+1 query.*User.hobbies"), Profiler():
            users = list(User.objects.all())
            for user in users:
                prefetch_related_objects([user], "hobbies")

    def test_profiler_no_false_positive_prefetch_related_objects_bulk(self, objects):
        from django.db.models import prefetch_related_objects
        from testapp.models import User

        with Profiler():
            users = list(User.objects.all())
            prefetch_related_objects(users, "hobbies")
            for user in users:
                list(user.hobbies.all())

    def test_profiler_error_includes_caller(self, objects):
        from testapp.models import Occupation

        with pytest.raises(NPlus1Error, match=r"at .+\.py:\d+ in"), Profiler():
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_profiler_detects_deferred_field(self, objects):
        from testapp.models import User

        with pytest.raises(NPlus1Error, match="User.name"), Profiler():
            users = list(User.objects.only("id"))
            users[0].name

    def test_profiler_detects_unused_eager(self, objects):
        from testapp.models import User

        with pytest.raises(NPlus1Error, match="User.occupation"), Profiler():
            users = list(User.objects.all().select_related("occupation"))
            str(users[0])

    def test_profiler_detects_get_in_loop(self, objects):
        from testapp.models import User

        with pytest.raises(NPlus1Error, match=r"get\(\)"), Profiler():
            for user in User.objects.all():
                User.objects.get(pk=user.pk)


@pytest.mark.django_db
class TestNPlus1Allow:
    def test_allow_all_suppresses(self, objects):
        """nplus1_allow() with no args suppresses all detections."""
        from testapp.models import Occupation

        with Profiler(), nplus1_allow():
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_allow_specific_model(self, objects):
        """nplus1_allow with model suppresses only that model."""
        from testapp.models import Occupation

        with Profiler(), nplus1_allow([{"model": "Occupation"}]):
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_allow_specific_model_and_field(self, objects):
        """nplus1_allow with model+field suppresses only that combination."""
        from testapp.models import User

        with Profiler(), nplus1_allow([{"model": "User", "field": "hobbies"}]):
            users = list(User.objects.all())
            list(users[0].hobbies.all())

    def test_allow_does_not_suppress_other_models(self, objects):
        """nplus1_allow for one model does not suppress another."""
        from testapp.models import Occupation

        with pytest.raises(NPlus1Error, match="Occupation.user"), Profiler(), nplus1_allow([{"model": "User"}]):
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_allow_does_not_suppress_other_fields(self, objects):
        """nplus1_allow for one field does not suppress another field on same model."""
        from testapp.models import User

        with (
            pytest.raises(NPlus1Error, match="User.hobbies"),
            Profiler(),
            nplus1_allow([{"model": "User", "field": "pet_set"}]),
        ):
            users = list(User.objects.all())
            list(users[0].hobbies.all())

    def test_allow_nesting(self, objects):
        """Nested nplus1_allow combines rules; inner exit restores outer."""
        from testapp.models import Occupation, User

        with Profiler():
            with nplus1_allow([{"model": "User"}]):
                users = list(User.objects.all())
                list(users[0].hobbies.all())  # allowed

                with nplus1_allow([{"model": "Occupation"}]):
                    occupations = list(Occupation.objects.all())
                    occupations[0].user  # allowed

            # Outside both: detection should fire again
            with pytest.raises(NPlus1Error, match="User.hobbies"), Profiler():
                users = list(User.objects.all())
                list(users[0].hobbies.all())

    def test_allow_wildcard(self, objects):
        """nplus1_allow with wildcard suppresses all models."""
        from testapp.models import Occupation

        with Profiler(), nplus1_allow([{"model": "*"}]):
            occupations = list(Occupation.objects.all())
            occupations[0].user


@pytest.mark.django_db
class TestNplus1Fixture:
    def test_nplus1_fixture_detects(self, objects, nplus1):
        from testapp.models import Occupation

        with pytest.raises(NPlus1Error, match="Occupation.user"):
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_nplus1_fixture_clean(self, objects, nplus1):
        from testapp.models import Occupation

        occupation = Occupation.objects.first()
        occupation.user


@pytest.mark.nplus1
@pytest.mark.django_db
class TestNplus1Marker:
    def test_marker_clean(self, objects):
        from testapp.models import Occupation

        occupation = Occupation.objects.first()
        occupation.user
