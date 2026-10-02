import contextvars
import threading

import pytest
from asgiref.sync import async_to_sync
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


@pytest.mark.django_db
def test_failing_receiver_is_logged_and_detection_goes_on(objects, caplog):
    def fail(sender, message, **kwargs):
        raise RuntimeError("receiver failed")

    nplus1_detected.connect(fail)
    try:
        with pytest.raises(NPlus1Error, match="Occupation.user"), Profiler():
            occupation_users()
    finally:
        nplus1_detected.disconnect(fail)
    assert [(r.name, type(r.exc_info[1])) for r in caplog.records if r.exc_info] == [("django.dispatch", RuntimeError)]


@pytest.mark.django_db
@pytest.mark.parametrize("receiver_is_async", [False, True], ids=["sync", "async"])
def test_receiver_gets_detection_at_the_end_of_an_async_request(objects, async_client, receiver_is_async):
    labels = []

    def receiver(sender, message, **kwargs):
        labels.append(message.label)

    async def async_receiver(sender, message, **kwargs):
        receiver(sender, message)

    connected = async_receiver if receiver_is_async else receiver
    nplus1_detected.connect(connected)
    try:
        response = async_to_sync(async_client.get)("/async_unused_select/")
    finally:
        nplus1_detected.disconnect(connected)
    assert response.status_code == 200
    assert labels == ["unused_eager_load"]


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
