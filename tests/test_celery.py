import logging

import pytest
from celery import Celery
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from testapp.models import Occupation, User

from django_nplus1 import NPlus1Error, nplus1_allow
from django_nplus1.celery import setup_celery_detection, teardown_celery_detection

pytestmark = pytest.mark.django_db

app = Celery("test_nplus1")


def read_occupation_users():
    return [occupation.user.name for occupation in Occupation.objects.order_by("pk")]


@app.task
def occupation_users():
    return read_occupation_users()


@app.task
def allowed_occupation_users():
    with nplus1_allow():
        return read_occupation_users()


@app.task
def first_occupation_user():
    occupations = list(Occupation.objects.order_by("pk"))
    return occupations[0].user.name


@app.task
def count_users():
    return len(User.objects.all())


@app.task
def count_users_with_unused_select():
    return len(User.objects.select_related("occupation"))


@app.task
def fail():
    raise ValueError("task failed")


@app.task(bind=True)
def replace_with_count_users(self):
    return self.replace(count_users.s())


@app.task
def occupation_users_in_subtask():
    return occupation_users.apply().get()


@pytest.fixture
def disconnect_detection():
    yield
    teardown_celery_detection()


@pytest.fixture
def celery_detection(settings, disconnect_detection):
    settings.NPLUS1_RAISE = True
    setup_celery_detection()


def test_detection_fails_the_task(objects, celery_detection):
    result = occupation_users.apply()
    with pytest.raises(NPlus1Error, match="Occupation.user"):
        result.get()


def test_each_task_run_counts_on_its_own(objects, celery_detection):
    assert [first_occupation_user.apply().get() for _ in range(2)] == ["alice", "alice"]


def test_allow_inside_task_suppresses_detection(objects, celery_detection):
    assert allowed_occupation_users.apply().get() == ["alice", "bob"]


@pytest.mark.parametrize(
    ("task", "state"),
    [(count_users, "SUCCESS"), (fail, "FAILURE"), (replace_with_count_users, "SUCCESS")],
    ids=["success", "failure", "eager-replace"],
)
def test_detection_ends_with_the_task(objects, celery_detection, task, state):
    assert task.apply().state == state
    assert read_occupation_users() == ["alice", "bob"]


def test_detection_at_the_end_of_a_task_is_logged(objects, celery_detection, caplog):
    assert count_users_with_unused_select.apply().get() == 2
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert [(record.name, type(record.exc_info[1])) for record in errors] == [("django_nplus1", NPlus1Error)]
    assert "User.occupation" in str(errors[0].exc_info[1])


def test_detection_in_a_subtask_is_logged_once(objects, disconnect_detection, caplog):
    setup_celery_detection()
    assert occupation_users_in_subtask.apply().get() == ["alice", "bob"]
    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "Occupation.user" in warnings[0]


def test_task_runs_when_detection_cannot_start(objects, celery_detection, settings, caplog):
    settings.NPLUS1_THRESHOLD = 0
    assert occupation_users.apply().get() == ["alice", "bob"]
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert [(record.name, type(record.exc_info[1])) for record in errors] == [("django_nplus1", ImproperlyConfigured)]


def test_setting_enables_detection_at_startup(objects, settings, disconnect_detection):
    settings.NPLUS1_CELERY = True
    settings.NPLUS1_RAISE = True
    apps.get_app_config("django_nplus1").ready()
    with pytest.raises(NPlus1Error, match="Occupation.user"):
        occupation_users.apply().get()


@pytest.mark.parametrize(
    ("name", "value", "error", "match"),
    [
        ("NPLUS1_THRESHOLD", 0, ImproperlyConfigured, "NPLUS1_THRESHOLD"),
        ("NPLUS1_ERROR", "builtins.NoSuchError", ImproperlyConfigured, "NPLUS1_ERROR"),
        ("NPLUS1_WHITELIST", [{"model": "testapp.Nothing"}], NPlus1Error, "testapp.Nothing"),
    ],
)
def test_setup_rejects_invalid_settings(settings, disconnect_detection, name, value, error, match):
    settings.NPLUS1_RAISE = True
    setattr(settings, name, value)
    with pytest.raises(error, match=match):
        setup_celery_detection()
