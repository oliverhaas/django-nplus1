from unittest import mock

import pytest
from django.conf import settings


@pytest.fixture
def logger(monkeypatch):
    mock_logger = mock.Mock()
    monkeypatch.setattr(settings, "NPLUS1_LOGGER", mock_logger)
    return mock_logger


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
