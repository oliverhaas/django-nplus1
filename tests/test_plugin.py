import pytest

from django_nplus1.exceptions import NPlusOneError
from django_nplus1.profiler import Profiler


@pytest.mark.django_db
class TestProfiler:
    def test_profiler_detects_nplus1(self, objects):
        from testapp.models import Occupation

        with pytest.raises(NPlusOneError, match="Occupation.user"), Profiler():
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

    def test_profiler_detects_unused_eager(self, objects):
        from testapp.models import User

        with pytest.raises(NPlusOneError, match="User.occupation"), Profiler():
            users = list(User.objects.all().select_related("occupation"))
            str(users[0])


@pytest.mark.django_db
class TestNplus1Fixture:
    def test_nplus1_fixture_detects(self, objects, nplus1):
        from testapp.models import Occupation

        with pytest.raises(NPlusOneError, match="Occupation.user"):
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
