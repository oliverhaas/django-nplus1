import pytest
from django.conf import settings
from django.db import connection
from django.db.models import prefetch_related_objects
from testapp.models import Occupation, User

from django_nplus1.detect import nplus1_allow
from django_nplus1.exceptions import NPlus1Error
from django_nplus1.profiler import Profiler


@pytest.mark.django_db
class TestProfiler:
    def test_profiler_detects_nplus1(self, objects):
        with pytest.raises(NPlus1Error, match="Occupation.user"), Profiler():
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_profiler_no_false_positive_on_get(self, objects):
        with Profiler():
            user = User.objects.get(pk=1)
            user.hobbies.all()

    def test_profiler_no_false_positive_on_first(self, objects):
        with Profiler():
            occupation = Occupation.objects.first()
            occupation.user

    def test_profiler_whitelist(self, objects):
        with Profiler(whitelist=[{"model": "Occupation"}]):
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_profiler_detects_prefetch_related_objects_loop(self, objects):
        with pytest.raises(NPlus1Error, match="n\\+1 query.*User.hobbies"), Profiler():
            users = list(User.objects.all())
            for user in users:
                prefetch_related_objects([user], "hobbies")

    def test_profiler_no_false_positive_prefetch_related_objects_bulk(self, objects):
        with Profiler():
            users = list(User.objects.all())
            prefetch_related_objects(users, "hobbies")
            for user in users:
                list(user.hobbies.all())

    def test_profiler_no_false_positive_single_result_prefetch(self, objects, settings):
        from django.db.models import prefetch_related_objects
        from testapp.models import User

        with Profiler():
            users = list(User.objects.filter(pk=1))
            prefetch_related_objects(users, "hobbies")
            list(users[0].hobbies.all())

    def test_profiler_error_includes_caller(self, objects):
        with pytest.raises(NPlus1Error, match=r"at .+\.py:\d+ in"), Profiler():
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_profiler_detects_deferred_field(self, objects):
        with pytest.raises(NPlus1Error, match="User.name"), Profiler():
            users = list(User.objects.only("id"))
            users[0].name

    def test_profiler_detects_unused_eager(self, objects):
        with pytest.raises(NPlus1Error, match="User.occupation"), Profiler():
            users = list(User.objects.all().select_related("occupation"))
            str(users[0])

    def test_profiler_detects_get_in_loop(self, objects):
        with pytest.raises(NPlus1Error, match=r"get\(\)"), Profiler():
            for user in User.objects.all():
                User.objects.get(pk=user.pk)

    def test_profiler_detects_raw_sql_loop(self, objects):
        settings.NPLUS1_DETECT_DUPLICATE_QUERIES = True
        try:
            with pytest.raises(NPlus1Error, match="duplicate query"), Profiler():
                pks = list(range(1, 3))
                for pk in pks:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT id FROM testapp_user WHERE id = %s", [pk])
        finally:
            del settings.NPLUS1_DETECT_DUPLICATE_QUERIES


@pytest.mark.django_db
class TestNPlus1Allow:
    def test_allow_all_suppresses(self, objects):
        """nplus1_allow() with no args suppresses all detections."""
        with Profiler(), nplus1_allow():
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_allow_specific_model(self, objects):
        """nplus1_allow with model suppresses only that model."""
        with Profiler(), nplus1_allow([{"model": "Occupation"}]):
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_allow_specific_model_and_field(self, objects):
        """nplus1_allow with model+field suppresses only that combination."""
        with Profiler(), nplus1_allow([{"model": "User", "field": "hobbies"}]):
            users = list(User.objects.all())
            list(users[0].hobbies.all())

    def test_allow_does_not_suppress_other_models(self, objects):
        """nplus1_allow for one model does not suppress another."""
        with pytest.raises(NPlus1Error, match="Occupation.user"), Profiler(), nplus1_allow([{"model": "User"}]):
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_allow_does_not_suppress_other_fields(self, objects):
        """nplus1_allow for one field does not suppress another field on same model."""
        with (
            pytest.raises(NPlus1Error, match="User.hobbies"),
            Profiler(),
            nplus1_allow([{"model": "User", "field": "pet_set"}]),
        ):
            users = list(User.objects.all())
            list(users[0].hobbies.all())

    def test_allow_nesting(self, objects):
        """Nested nplus1_allow combines rules; inner exit restores outer."""
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
        with Profiler(), nplus1_allow([{"model": "*"}]):
            occupations = list(Occupation.objects.all())
            occupations[0].user


@pytest.mark.django_db
class TestNplus1Fixture:
    def test_nplus1_fixture_detects(self, objects, nplus1):
        with pytest.raises(NPlus1Error, match="Occupation.user"):
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_nplus1_fixture_clean(self, objects, nplus1):
        occupation = Occupation.objects.first()
        occupation.user


@pytest.mark.django_db
class TestNPlus1AllowWithFixture:
    def test_allow_with_nplus1_fixture(self, objects, nplus1):
        """nplus1_allow works inside the nplus1 fixture."""
        with nplus1_allow([{"model": "Occupation"}]):
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_allow_partial_with_nplus1_fixture(self, objects, nplus1):
        """nplus1_allow suppresses one model but fixture still catches another."""
        with pytest.raises(NPlus1Error, match="User.hobbies"), nplus1_allow([{"model": "Occupation"}]):
            users = list(User.objects.all())
            list(users[0].hobbies.all())


@pytest.mark.nplus1
@pytest.mark.django_db
class TestNPlus1AllowWithMarker:
    def test_allow_with_marker(self, objects):
        """nplus1_allow works inside a @pytest.mark.nplus1 test."""
        with nplus1_allow([{"model": "Occupation"}]):
            occupations = list(Occupation.objects.all())
            occupations[0].user


@pytest.mark.django_db
class TestNPlus1AllowWithProfilerWhitelist:
    def test_allow_combined_with_profiler_whitelist(self, objects):
        """nplus1_allow and Profiler whitelist work together."""
        with Profiler(whitelist=[{"model": "User"}]):
            # User is whitelisted by Profiler
            users = list(User.objects.all())
            list(users[0].hobbies.all())

            # Occupation is allowed by nplus1_allow
            with nplus1_allow([{"model": "Occupation"}]):
                occupations = list(Occupation.objects.all())
                occupations[0].user

    def test_profiler_whitelist_without_allow_still_raises(self, objects):
        """Profiler whitelist alone does not cover what nplus1_allow would."""
        with pytest.raises(NPlus1Error, match="Occupation.user"), Profiler(whitelist=[{"model": "User"}]):
            occupations = list(Occupation.objects.all())
            occupations[0].user


@pytest.mark.nplus1
@pytest.mark.django_db
class TestNplus1Marker:
    def test_marker_clean(self, objects):
        occupation = Occupation.objects.first()
        occupation.user
