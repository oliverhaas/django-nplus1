from collections import defaultdict

from django_nplus1 import signals
from django_nplus1.signals import _listeners


class TestSendIterationSafety:
    def test_all_callbacks_fire_when_one_disconnects_itself(self):
        """Callbacks that disconnect during send must not cause others to be skipped."""
        token = _listeners.set(defaultdict(list))
        calls = []
        signal = "test_iter_safety"

        def self_removing(**kwargs):
            signals.disconnect(signal, self_removing)
            calls.append("first")

        def observer(**kwargs):
            calls.append("second")

        signals.connect(signal, self_removing)
        signals.connect(signal, observer)
        try:
            signals.send(signal)
            assert calls == ["first", "second"]
        finally:
            signals.disconnect(signal, self_removing)
            signals.disconnect(signal, observer)
            _listeners.reset(token)
