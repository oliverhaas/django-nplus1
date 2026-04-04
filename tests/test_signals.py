import pytest
from django.conf import settings

from django_nplus1 import signals
from django_nplus1.detect import LazyLoadMessage
from django_nplus1.exceptions import NPlus1Error
from django_nplus1.middleware import NPlus1Middleware
from django_nplus1.profiler import Profiler
from django_nplus1.signals import nplus1_detected


class TestSendIterationSafety:
    def test_all_callbacks_fire_when_one_disconnects_itself(self):
        """Callbacks that disconnect during send must not cause others to be skipped."""
        calls = []
        worker = signals.get_worker()
        signal = "test_iter_safety"

        def self_removing(**kwargs):
            signals.disconnect(signal, self_removing, sender=worker)
            calls.append("first")

        def observer(**kwargs):
            calls.append("second")

        signals.connect(signal, self_removing, sender=worker)
        signals.connect(signal, observer, sender=worker)
        try:
            signals.send(signal, sender=worker)
            assert calls == ["first", "second"]
        finally:
            signals.disconnect(signal, self_removing, sender=worker)
            signals.disconnect(signal, observer, sender=worker)


@pytest.mark.django_db
class TestNPlus1DetectedSignalMiddleware:
    def test_signal_emitted_on_detection(self, objects, client, logger):
        """nplus1_detected signal fires when middleware detects an N+1."""
        received = []

        def handler(sender, message, **kwargs):
            received.append(message)

        nplus1_detected.connect(handler)
        try:
            client.get("/many_to_many/")
            assert len(received) == 1
            assert isinstance(received[0], LazyLoadMessage)
            assert received[0].field == "hobbies"
        finally:
            nplus1_detected.disconnect(handler)

    def test_signal_not_emitted_when_whitelisted(self, objects, client, logger, monkeypatch):
        """nplus1_detected signal does not fire for whitelisted models."""
        monkeypatch.setattr(settings, "NPLUS1_WHITELIST", [{"model": "testapp.User"}])
        received = []

        def handler(sender, message, **kwargs):
            received.append(message)

        nplus1_detected.connect(handler)
        try:
            client.get("/many_to_many/")
            assert len(received) == 0
        finally:
            nplus1_detected.disconnect(handler)

    def test_signal_sender_is_middleware_class(self, objects, client, logger):
        """The sender kwarg is the NPlus1Middleware class."""
        received = []

        def handler(sender, message, **kwargs):
            received.append(sender)

        nplus1_detected.connect(handler)
        try:
            client.get("/many_to_many/")
            assert received[0] is NPlus1Middleware
        finally:
            nplus1_detected.disconnect(handler)

    def test_signal_carries_correct_model(self, objects, client, logger):
        """The message in the signal has the correct model."""
        from testapp.models import User

        received = []

        def handler(sender, message, **kwargs):
            received.append(message)

        nplus1_detected.connect(handler)
        try:
            client.get("/many_to_many/")
            assert received[0].model is User
        finally:
            nplus1_detected.disconnect(handler)


@pytest.mark.django_db
class TestNPlus1DetectedSignalProfiler:
    def test_signal_emitted_on_detection(self, objects):
        from testapp.models import User

        received = []

        def handler(sender, message, **kwargs):
            received.append(message)

        nplus1_detected.connect(handler)
        try:
            with pytest.raises(NPlus1Error), Profiler():
                users = list(User.objects.all())
                for user in users:
                    list(user.hobbies.all())
            assert len(received) >= 1
            assert isinstance(received[0], LazyLoadMessage)
            assert received[0].field == "hobbies"
        finally:
            nplus1_detected.disconnect(handler)

    def test_signal_sender_is_profiler_class(self, objects):
        from testapp.models import User

        received = []

        def handler(sender, message, **kwargs):
            received.append(sender)

        nplus1_detected.connect(handler)
        try:
            with pytest.raises(NPlus1Error), Profiler():
                users = list(User.objects.all())
                for user in users:
                    list(user.hobbies.all())
            assert received[0] is Profiler
        finally:
            nplus1_detected.disconnect(handler)

    def test_signal_not_emitted_when_whitelisted(self, objects):
        from testapp.models import User

        received = []

        def handler(sender, message, **kwargs):
            received.append(message)

        nplus1_detected.connect(handler)
        try:
            with Profiler(whitelist=[{"model": "User", "field": "hobbies"}]):
                users = list(User.objects.all())
                for user in users:
                    list(user.hobbies.all())
            assert len(received) == 0
        finally:
            nplus1_detected.disconnect(handler)
