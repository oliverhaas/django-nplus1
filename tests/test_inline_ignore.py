import pytest

from django_nplus1.exceptions import NPlus1Error
from django_nplus1.profiler import Profiler


@pytest.mark.django_db
class TestInlineIgnore:
    def test_unscoped_ignore_suppresses_lazy_load(self, objects):
        from testapp.models import Occupation

        with Profiler():
            occupations = list(Occupation.objects.all())
            occupations[0].user  # nplus1: ignore

    def test_scoped_ignore_suppresses_matching_label(self, objects):
        from testapp.models import Occupation

        with Profiler():
            occupations = list(Occupation.objects.all())
            occupations[0].user  # nplus1: ignore[n_plus_one]

    def test_scoped_ignore_does_not_suppress_other_label(self, objects):
        from testapp.models import User

        with pytest.raises(NPlus1Error, match=r"get\(\)"), Profiler():
            for user in User.objects.all():
                User.objects.get(pk=user.pk)  # nplus1: ignore[n_plus_one]

    def test_ignore_with_multiple_labels(self, objects):
        from testapp.models import User

        with Profiler():
            for user in User.objects.all():
                User.objects.get(pk=user.pk)  # nplus1: ignore[n_plus_one, get_in_loop]

    def test_no_ignore_comment_still_detects(self, objects):
        from testapp.models import Occupation

        with pytest.raises(NPlus1Error, match="Occupation.user"), Profiler():
            occupations = list(Occupation.objects.all())
            occupations[0].user

    def test_unrelated_comment_does_not_suppress(self, objects):
        from testapp.models import Occupation

        with pytest.raises(NPlus1Error, match="Occupation.user"), Profiler():
            occupations = list(Occupation.objects.all())
            occupations[0].user  # regular comment, not a suppression
