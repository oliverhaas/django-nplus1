from django_nplus1 import signals


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
