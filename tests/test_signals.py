import contextvars
import threading

import pytest
from testapp.models import Occupation

from django_nplus1 import DetectionContext, NPlus1Error, NPlus1Middleware, Profiler, nplus1_detected, signals


class CustomScope(DetectionContext):
    pass


def occupation_users():
    return [occupation.user for occupation in Occupation.objects.all()]


@pytest.fixture
def senders():
    received = []

    def receiver(sender, message, **kwargs):
        received.append(sender)

    nplus1_detected.connect(receiver)
    yield received
    nplus1_detected.disconnect(receiver)


@pytest.mark.django_db
@pytest.mark.parametrize("scope_class", [DetectionContext, CustomScope])
def test_detection_is_sent_by_the_scope_class(objects, senders, scope_class):
    with scope_class():
        occupation_users()
    assert senders == [scope_class]


@pytest.mark.django_db
def test_profiler_sends_detection_before_raising(objects, senders):
    with pytest.raises(NPlus1Error), Profiler():
        occupation_users()
    assert senders == [Profiler]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("whitelist", "expected"),
    [([], [NPlus1Middleware]), ([{"model": "testapp.Occupation"}], [])],
)
def test_middleware_sends_detection_unless_whitelisted(objects, client, settings, senders, whitelist, expected):
    settings.NPLUS1_WHITELIST = whitelist
    response = client.get("/lazy_loop/")
    assert response.status_code == 200
    assert senders == expected


def test_suppress_leaves_other_threads_of_the_scope_alone():
    received = []
    suppressing = threading.Event()
    release = threading.Event()

    def suppress_touches():
        with signals.suppress(signals.TOUCH):
            suppressing.set()
            release.wait(timeout=10)

    token = signals.setup_context()
    try:
        signals.connect(signals.TOUCH, lambda **kwargs: received.append(kwargs["args"]))
        thread = threading.Thread(target=contextvars.copy_context().run, args=(suppress_touches,))
        thread.start()
        try:
            suppressing.wait(timeout=10)
            signals.emit(signals.TOUCH, "row")
        finally:
            release.set()
            thread.join()
        signals.emit(signals.TOUCH, "next row")
    finally:
        signals.teardown_context(token)
    assert received == [("row",), ("next row",)]
