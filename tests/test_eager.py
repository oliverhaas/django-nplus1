import pytest

from django_nplus1 import signals
from django_nplus1.detect import EagerListener


@pytest.mark.django_db
class TestSelectRelated:
    def test_select_one_to_one_unused(self, objects, client, logger):
        client.get("/select_one_to_one_unused/")
        assert len(logger.log.call_args_list) == 1
        args = logger.log.call_args[0]
        assert "User.occupation" in args[1]

    def test_select_many_to_one_unused(self, objects, client, logger):
        client.get("/select_many_to_one_unused/")
        assert len(logger.log.call_args_list) == 1
        args = logger.log.call_args[0]
        assert "Pet.user" in args[1]

    def test_select_nested(self, objects, client, logger):
        client.get("/select_nested/")
        assert not logger.log.called

    def test_select_nested_unused(self, objects, client, logger):
        client.get("/select_nested_unused/")
        assert len(logger.log.call_args_list) == 2
        calls = [call[0] for call in logger.log.call_args_list]
        assert any("Pet.user" in call[1] for call in calls)
        assert any("User.occupation" in call[1] for call in calls)


@pytest.mark.django_db
class TestPrefetchRelated:
    def test_prefetch_one_to_one_unused(self, objects, client, logger):
        client.get("/prefetch_one_to_one_unused/")
        assert len(logger.log.call_args_list) == 1
        args = logger.log.call_args[0]
        assert "User.occupation" in args[1]

    def test_prefetch_many_to_many_unused(self, objects, client, logger):
        client.get("/prefetch_many_to_many_unused/")
        assert len(logger.log.call_args_list) == 1
        args = logger.log.call_args[0]
        assert "User.hobbies" in args[1]

    def test_prefetch_nested(self, objects, client, logger):
        client.get("/prefetch_nested/")
        assert not logger.log.called

    def test_prefetch_nested_unused(self, objects, client, logger):
        client.get("/prefetch_nested_unused/")
        assert len(logger.log.call_args_list) == 2
        calls = [call[0] for call in logger.log.call_args_list]
        assert any("Pet.user" in call[1] for call in calls)
        assert any("User.occupation" in call[1] for call in calls)


class TestEagerListenerCleanup:
    def test_nested_unused_not_duplicated(self, objects, client, logger):
        """Multiple eager loads in one request should report each unused field exactly once."""
        client.get("/select_nested_unused/")
        messages = [call[0][1] for call in logger.log.call_args_list]
        assert sum(1 for m in messages if "Pet.user" in m) == 1
        assert sum(1 for m in messages if "User.occupation" in m) == 1

    def test_no_stale_handlers_after_teardown(self):
        """After teardown, all signal handlers registered by EagerListener must be removed."""

        class FakeParent:
            def notify(self, msg):
                pass

        worker = signals.get_worker()
        key = signals._key(signals.TOUCH, worker)
        before = len(signals._listeners[key])

        listener = EagerListener(FakeParent())
        listener.setup()
        for _ in range(3):
            listener.handle_eager(parser=lambda a, k, c: (object, "field", ["inst"], 1))
        listener.teardown()

        assert len(signals._listeners[key]) == before
