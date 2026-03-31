import pytest
from django.conf import settings
from django.http.request import HttpRequest
from django.http.response import HttpResponse

from django_nplus1.exceptions import NPlus1Error
from django_nplus1.middleware import NPlus1Middleware


@pytest.mark.django_db
class TestIntegration:
    def test_one_to_one(self, objects, client, logger):
        client.get("/one_to_one/")
        assert len(logger.log.call_args_list) == 1
        args = logger.log.call_args[0]
        assert "Occupation.user" in args[1]

    def test_one_to_one_first(self, objects, client, logger):
        client.get("/one_to_one_first/")
        assert not logger.log.called

    def test_one_to_many(self, objects, client, logger):
        client.get("/one_to_many/")
        assert not logger.log.called

    def test_many_to_many(self, objects, client, logger):
        client.get("/many_to_many/")
        assert len(logger.log.call_args_list) == 1
        args = logger.log.call_args[0]
        assert "User.hobbies" in args[1]

    def test_many_to_many_get(self, objects, client, logger):
        client.get("/many_to_many_get/")
        assert len(logger.log.call_args_list) == 0

    def test_prefetch_one_to_one(self, objects, client, logger):
        client.get("/prefetch_one_to_one/")
        assert not logger.log.called

    def test_prefetch_many_to_many(self, objects, client, logger):
        client.get("/prefetch_many_to_many/")
        assert not logger.log.called

    def test_many_to_many_impossible(self, objects, client, logger):
        client.get("/many_to_many_impossible/")
        assert not logger.log.called

    def test_many_to_many_impossible_one(self, objects, client, logger):
        client.get("/many_to_many_impossible_one/")
        assert not logger.log.called

    def test_prefetch_many_to_many_render(self, objects, client, logger):
        client.get("/prefetch_many_to_many_render/")
        assert not logger.log.called

    def test_prefetch_many_to_many_empty(self, objects, client, logger):
        from testapp.models import User

        User.objects.all().delete()
        client.get("/prefetch_many_to_many/")
        assert not logger.log.called

    def test_prefetch_many_to_many_render_empty(self, objects, client, logger):
        from testapp.models import User

        User.objects.all().delete()
        client.get("/prefetch_many_to_many_render/")
        assert not logger.log.called

    def test_prefetch_many_to_many_single(self, objects, client, logger):
        client.get("/prefetch_many_to_many_single/")
        assert not logger.log.called

    def test_prefetch_many_to_many_no_related_name(self, objects, client, logger):
        client.get("/prefetch_many_to_many_no_related/")
        assert not logger.log.called

    def test_select_one_to_one(self, objects, client, logger):
        client.get("/select_one_to_one/")
        assert not logger.log.called

    def test_select_many_to_one(self, objects, client, logger):
        client.get("/select_many_to_one/")
        assert not logger.log.called

    def test_select_many_to_one_empty(self, objects, client, logger):
        from testapp.models import Pet

        Pet.objects.all().delete()
        client.get("/select_many_to_one/")
        assert not logger.log.called

    def test_many_to_many_whitelist(self, objects, client, logger, monkeypatch):
        monkeypatch.setattr(settings, "NPLUS1_WHITELIST", [{"model": "testapp.User"}])
        client.get("/many_to_many/")
        assert not logger.log.called

    def test_many_to_many_whitelist_wildcard(self, objects, client, logger, monkeypatch):
        monkeypatch.setattr(settings, "NPLUS1_WHITELIST", [{"model": "testapp.*"}])
        client.get("/many_to_many/")
        assert not logger.log.called


@pytest.mark.django_db
class TestConfig:
    def test_raise_on_detection(self, objects, client):
        """NPLUS1_RAISE=True causes NPlus1Error instead of logging."""
        settings.NPLUS1_RAISE = True
        try:
            with pytest.raises(NPlus1Error, match="User.hobbies"):
                client.get("/many_to_many/")
        finally:
            del settings.NPLUS1_RAISE

    def test_log_disabled(self, objects, client, logger):
        """NPLUS1_LOG=False suppresses log output entirely."""
        original = settings.NPLUS1_LOG
        settings.NPLUS1_LOG = False
        try:
            client.get("/many_to_many/")
            assert not logger.log.called
        finally:
            settings.NPLUS1_LOG = original

    def test_custom_error_class(self, objects, client):
        """NPLUS1_ERROR is used as the exception type when raising."""

        class CustomError(Exception):
            pass

        settings.NPLUS1_RAISE = True
        settings.NPLUS1_ERROR = CustomError
        try:
            with pytest.raises(CustomError):
                client.get("/many_to_many/")
        finally:
            del settings.NPLUS1_RAISE
            del settings.NPLUS1_ERROR


@pytest.mark.django_db
class TestPrefetchRelatedObjects:
    def test_loop_detected(self, objects, client, logger):
        """prefetch_related_objects([obj], 'field') in a loop is N+1."""
        client.get("/prefetch_related_objects_loop/")
        messages = [call[0][1] for call in logger.log.call_args_list]
        assert any("n+1 query" in m.lower() and "User.hobbies" in m for m in messages)

    def test_bulk_not_detected(self, objects, client, logger):
        """prefetch_related_objects(all_objs, 'field') is legitimate."""
        client.get("/prefetch_related_objects_bulk/")
        messages = [call[0][1] for call in logger.log.call_args_list]
        assert not any("n+1" in m.lower() for m in messages)

    def test_get_not_detected(self, objects, client, logger):
        """prefetch_related_objects on a .get() result is not N+1."""
        client.get("/prefetch_related_objects_get/")
        messages = [call[0][1] for call in logger.log.call_args_list]
        assert not any("n+1" in m.lower() for m in messages)

    def test_first_not_detected(self, objects, client, logger):
        """prefetch_related_objects on a .first() result is not N+1."""
        client.get("/prefetch_related_objects_first/")
        messages = [call[0][1] for call in logger.log.call_args_list]
        assert not any("n+1" in m.lower() for m in messages)


def test_middleware_no_process_request():
    middleware = NPlus1Middleware(lambda r: HttpResponse())
    req = HttpRequest()
    resp = middleware(req)
    assert resp.status_code == 200
