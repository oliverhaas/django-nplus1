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

    def test_warn_on_detection(self, objects, client):
        """NPLUS1_WARN=True emits UserWarning."""
        settings.NPLUS1_WARN = True
        try:
            with pytest.warns(UserWarning, match="User.hobbies"):
                client.get("/many_to_many/")
        finally:
            del settings.NPLUS1_WARN

    def test_warn_includes_location(self, objects, client):
        """Warning points to the actual view file location."""
        settings.NPLUS1_WARN = True
        try:
            with pytest.warns(UserWarning, match="User.hobbies") as record:
                client.get("/many_to_many/")
            assert "views.py" in record[0].filename
        finally:
            del settings.NPLUS1_WARN


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


@pytest.mark.django_db
class TestWhitelistValidation:
    def test_invalid_model_raises(self, client, monkeypatch):
        """Typo in model name raises NPlus1Error."""
        monkeypatch.setattr(
            settings,
            "NPLUS1_WHITELIST",
            [{"model": "testapp.NonExistent"}],
        )
        with pytest.raises(NPlus1Error, match="not found"):
            client.get("/many_to_many/")

    def test_invalid_field_raises(self, objects, client, monkeypatch):
        """Typo in field name raises NPlus1Error."""
        monkeypatch.setattr(
            settings,
            "NPLUS1_WHITELIST",
            [{"model": "testapp.User", "field": "nonexistent_field"}],
        )
        with pytest.raises(NPlus1Error, match="not found"):
            client.get("/many_to_many/")

    def test_wildcard_model_skips_validation(self, objects, client, logger, monkeypatch):
        """Wildcard patterns are not validated against registry."""
        monkeypatch.setattr(
            settings,
            "NPLUS1_WHITELIST",
            [{"model": "testapp.*"}],
        )
        client.get("/many_to_many/")
        assert not logger.log.called

    def test_valid_whitelist_passes(self, objects, client, logger, monkeypatch):
        """Valid model/field combo passes validation and suppresses detection."""
        monkeypatch.setattr(
            settings,
            "NPLUS1_WHITELIST",
            [{"model": "testapp.User", "field": "hobbies"}],
        )
        client.get("/many_to_many/")
        assert not logger.log.called


@pytest.mark.django_db
class TestDeferred:
    def test_deferred_field_detected(self, objects, client, logger):
        client.get("/deferred_field/")
        assert len(logger.log.call_args_list) == 1
        args = logger.log.call_args[0]
        assert "User.name" in args[1]

    def test_deferred_field_first_not_detected(self, objects, client, logger):
        client.get("/deferred_field_first/")
        assert not logger.log.called


@pytest.mark.django_db
class TestCallerInfo:
    def test_log_includes_caller_info(self, objects, client, logger):
        """Log message includes the file and function that caused the N+1."""
        client.get("/many_to_many/")
        args = logger.log.call_args[0]
        message = args[1]
        assert "views.py:" in message
        assert "in many_to_many" in message


@pytest.mark.django_db
class TestGetInLoop:
    def test_get_in_loop_detected(self, objects, client, logger):
        client.get("/get_in_loop/")
        messages = [call[0][1] for call in logger.log.call_args_list]
        assert any("get()" in m for m in messages)

    def test_get_single_not_detected(self, objects, client, logger):
        client.get("/get_single/")
        assert not logger.log.called

    def test_get_different_lines_not_detected(self, objects, client, logger):
        client.get("/get_different_lines/")
        messages = [call[0][1] for call in logger.log.call_args_list]
        assert not any("get()" in m for m in messages)


class TestThreshold:
    def test_threshold_setting(self, objects, client, logger, monkeypatch):
        """NPLUS1_THRESHOLD controls how many accesses trigger detection."""
        monkeypatch.setattr(settings, "NPLUS1_THRESHOLD", 10)
        client.get("/many_to_many/")  # accesses hobbies on 1 instance
        assert not logger.log.called


@pytest.mark.django_db
class TestShowAllCallers:
    def test_show_all_callers(self, objects, client, logger, monkeypatch):
        """NPLUS1_SHOW_ALL_CALLERS includes all call stacks."""
        monkeypatch.setattr(settings, "NPLUS1_SHOW_ALL_CALLERS", True)
        client.get("/one_to_one/")
        args = logger.log.call_args[0]
        message = args[1]
        assert "CALL 1:" in message
        assert "views.py:" in message

    def test_show_all_callers_disabled(self, objects, client, logger, monkeypatch):
        """Normal mode still shows single caller without CALL labels."""
        monkeypatch.setattr(settings, "NPLUS1_SHOW_ALL_CALLERS", False)
        client.get("/one_to_one/")
        args = logger.log.call_args[0]
        message = args[1]
        assert "CALL 1:" not in message
        assert "views.py:" in message

    def test_show_all_callers_many_to_many(self, objects, client, logger, monkeypatch):
        """NPLUS1_SHOW_ALL_CALLERS works with many-to-many lazy loads."""
        monkeypatch.setattr(settings, "NPLUS1_SHOW_ALL_CALLERS", True)
        client.get("/many_to_many/")
        args = logger.log.call_args[0]
        message = args[1]
        assert "CALL 1:" in message
        assert "with calls:" in message


def test_middleware_no_process_request():
    middleware = NPlus1Middleware(lambda r: HttpResponse())
    req = HttpRequest()
    resp = middleware(req)
    assert resp.status_code == 200
