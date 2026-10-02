import contextlib

import pytest
from testapp.models import Occupation, User

from django_nplus1 import DetectionContext, NPlus1Error, Profiler

pytestmark = pytest.mark.django_db


class RecordingNotifier:
    def __init__(self):
        self.messages = []

    def notify(self, message):
        self.messages.append(message.message)


def occupation_users():
    return [occupation.user for occupation in Occupation.objects.all()]


def test_inner_detection_reaches_every_enclosing_scope(objects, detected):
    outer, inner = RecordingNotifier(), RecordingNotifier()
    with DetectionContext(notifiers=[outer]), DetectionContext(notifiers=[inner]):
        occupation_users()
    assert [(m.model, m.field) for m in detected] == [(Occupation, "user")]
    assert outer.messages == inner.messages == [detected[0].message]


def test_enclosing_profiler_raises_for_inner_detection(objects):
    with pytest.raises(NPlus1Error, match="Occupation.user"), Profiler(), DetectionContext():
        occupation_users()


@pytest.mark.parametrize(
    ("whitelist", "expected"),
    [([{"model": "Occupation"}], []), ([{"model": "Pet"}], [(Occupation, "user")])],
)
def test_enclosing_whitelist_applies_to_inner_scope(objects, detected, whitelist, expected):
    with DetectionContext(whitelist=whitelist), DetectionContext():
        occupation_users()
    assert [(m.model, m.field) for m in detected] == expected


def test_inner_scope_reads_rows_of_enclosing_scope(objects):
    with Profiler():
        users = list(User.objects.prefetch_related("hobbies"))
        with DetectionContext():
            for user in users:
                list(user.hobbies.all())


def test_reentering_an_active_scope_raises(objects, detected):
    scope = DetectionContext()
    with scope:
        with pytest.raises(RuntimeError, match="already active"), scope:
            pass
        occupation_users()
    assert [(m.model, m.field) for m in detected] == [(Occupation, "user")]


def test_body_exception_wins_over_detection_at_exit(objects):
    with pytest.raises(RuntimeError, match="body failed"), Profiler():
        list(User.objects.select_related("occupation"))
        raise RuntimeError("body failed")


def test_detection_at_exit_still_ends_the_scope(objects, settings):
    settings.NPLUS1_DETECT_DUPLICATE_QUERIES = True
    with pytest.raises(NPlus1Error, match="unnecessary eager load"), Profiler():
        list(User.objects.select_related("occupation"))
    for _ in range(2):
        list(User.objects.all())


@pytest.mark.parametrize(
    ("block_error", "raised"),
    [(RuntimeError, NPlus1Error), (KeyboardInterrupt, KeyboardInterrupt)],
    ids=["exception", "base-exception"],
)
def test_caught_detection_replaces_only_an_exception_of_the_block(objects, block_error, raised):
    with pytest.raises(raised), Profiler():
        with contextlib.suppress(Exception):
            occupation_users()
        raise block_error


def test_enclosing_scope_raises_detection_caught_outside_the_inner_scope(objects):
    with (
        pytest.raises(NPlus1Error, match="Occupation.user"),
        Profiler(),
        contextlib.suppress(NPlus1Error),
        Profiler(),
    ):
        occupation_users()


def test_enclosing_scope_ignores_detection_dropped_by_failed_inner_block(objects):
    with Profiler(), pytest.raises(RuntimeError, match="body failed"), DetectionContext():
        list(User.objects.select_related("occupation"))
        raise RuntimeError("body failed")


def test_reentered_scope_forgets_the_detection_of_its_last_run(objects):
    profiler = Profiler()
    with pytest.raises(NPlus1Error), profiler, contextlib.suppress(NPlus1Error):
        occupation_users()
    with profiler:
        pass
