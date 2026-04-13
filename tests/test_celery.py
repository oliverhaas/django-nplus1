import pytest
from celery import Celery

from django_nplus1.celery import _active_scopes, setup_celery_detection, teardown_celery_detection
from django_nplus1.exceptions import NPlus1Error

app = Celery("test_nplus1")
app.conf.update(
    task_always_eager=True,
    task_eager_propagates=True,
)


@app.task
def nplus1_task():
    from testapp.models import Occupation

    occupations = list(Occupation.objects.all())
    occupations[0].user


@app.task
def allowed_task():
    from testapp.models import Occupation

    from django_nplus1 import nplus1_allow

    with nplus1_allow():
        occupations = list(Occupation.objects.all())
        occupations[0].user


@app.task
def failing_task():
    raise ValueError("intentional")


@app.task
def clean_task():
    from testapp.models import User

    list(User.objects.all())


@pytest.fixture(autouse=True)
def _celery_detection(settings):
    settings.NPLUS1_RAISE = True
    setup_celery_detection()
    yield
    teardown_celery_detection()


@pytest.mark.django_db
class TestCeleryDetection:
    def test_detects_nplus1_in_task(self, objects):
        """N+1 in a task raises NPlus1Error."""
        with pytest.raises(NPlus1Error, match="Occupation.user"):
            nplus1_task.apply()

    def test_scope_isolation_between_tasks(self, objects, settings):
        """Each task gets its own scope; counts don't accumulate across tasks."""
        settings.NPLUS1_THRESHOLD = 2
        # Each call does one lazy load (below threshold=2).
        # If scopes leaked, the second call would see count=2 and raise.
        nplus1_task.apply()
        nplus1_task.apply()

    def test_nplus1_allow_suppresses_in_task(self, objects):
        """nplus1_allow() inside a task suppresses detection."""
        allowed_task.apply()  # Should not raise

    def test_scope_cleaned_up_on_task_failure(self, objects):
        """Scope teardown happens even when the task raises."""
        with pytest.raises(ValueError, match="intentional"):
            failing_task.apply()
        assert not _active_scopes

    def test_no_scope_leak_after_success(self, objects):
        """Active scopes dict is empty after task completes."""
        clean_task.apply()
        assert not _active_scopes

    def test_works_with_delay(self, objects):
        """Detection works via .delay() in eager mode."""
        with pytest.raises(NPlus1Error, match="Occupation.user"):
            nplus1_task.delay()
