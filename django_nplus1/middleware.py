from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING, Any

from asgiref.sync import iscoroutinefunction
from django.apps import apps
from django.conf import settings
from django.utils.decorators import sync_and_async_middleware

from django_nplus1 import notifiers
from django_nplus1.detect import LISTENERS, Message, Rule
from django_nplus1.exceptions import NPlus1Error
from django_nplus1.signals import nplus1_detected, setup_context, teardown_context

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from django_nplus1.detect import Listener

_FNMATCH_CHARS = set("*?[]")


def _validate_whitelist(whitelist: list[dict[str, Any]]) -> None:
    """Validate whitelist entries against the Django model registry.

    Raises NPlus1Error for invalid model or field names.
    Skips entries that use fnmatch wildcards (* ? [ ]).
    """
    # Build registry: {"app_label.ModelName": set_of_field_names}
    registry: dict[str, set[str]] = {}
    for model in apps.get_models():
        key = f"{model._meta.app_label}.{model.__name__}"
        fields = {f.name for f in model._meta.get_fields(include_hidden=True)}
        # Include reverse relation accessor names
        fields |= {name for rel in model._meta.related_objects if (name := rel.get_accessor_name()) is not None}
        registry[key] = fields

    for entry in whitelist:
        model_pattern = entry.get("model")
        if not model_pattern:
            continue

        # Skip fnmatch patterns
        if any(c in model_pattern for c in _FNMATCH_CHARS):
            continue

        if model_pattern not in registry:
            suffix = model_pattern.split(".")[-1].lower()
            similar = sorted(k for k in registry if suffix in k.lower())[:3]
            msg = f"NPLUS1_WHITELIST: model '{model_pattern}' not found in installed Django models."
            if similar:
                msg += f" Did you mean one of: {', '.join(similar)}?"
            raise NPlus1Error(msg)

        field_name = entry.get("field")
        if not field_name:
            continue
        if any(c in field_name for c in _FNMATCH_CHARS):
            continue

        if field_name not in registry[model_pattern]:
            raise NPlus1Error(
                f"NPLUS1_WHITELIST: field '{field_name}' not found on '{model_pattern}'",
            )


class DjangoRule(Rule):
    def match_model(self, model: type) -> bool:
        if self.model is model:
            return True
        if isinstance(self.model, str):
            return fnmatch.fnmatch(
                f"{model._meta.app_label}.{model.__name__}",  # type: ignore[attr-defined]
                self.model,
            )
        return False


_last_validated_whitelist_id: int | None = None


def _load_config() -> tuple[list[notifiers.Notifier], list[DjangoRule]]:
    """Load notifiers and whitelist from settings."""
    global _last_validated_whitelist_id  # noqa: PLW0603
    nots = notifiers.init(settings)
    whitelist_data = getattr(settings, "NPLUS1_WHITELIST", [])
    if id(whitelist_data) != _last_validated_whitelist_id:
        _validate_whitelist(whitelist_data)
        _last_validated_whitelist_id = id(whitelist_data)
    whitelist = [DjangoRule(**item) for item in whitelist_data]
    return nots, whitelist


class _DetectionContext:
    """Manages listener setup/teardown for a single request scope."""

    def __init__(self, nots: list[notifiers.Notifier], whitelist: list[DjangoRule]) -> None:
        self.nots = nots
        self.whitelist = whitelist
        self.listeners: dict[str, Listener] = {}

    def setup(self) -> None:
        for name, listener_type in LISTENERS.items():
            self.listeners[name] = listener_type(self)
            self.listeners[name].setup()

    def teardown(self) -> None:
        for name in list(LISTENERS.keys()):
            listener = self.listeners.pop(name, None)
            if listener:
                listener.teardown()

    def notify(self, message: Message) -> None:
        if not message.match(self.whitelist):
            nplus1_detected.send(sender=NPlus1Middleware, message=message)
            for notifier in self.nots:
                notifier.notify(message)


@sync_and_async_middleware
def NPlus1Middleware(get_response: Any) -> Any:  # noqa: N802
    if iscoroutinefunction(get_response):

        async def async_middleware(request: HttpRequest) -> HttpResponse:
            token = setup_context()
            nots, whitelist = _load_config()
            ctx = _DetectionContext(nots, whitelist)
            ctx.setup()
            try:
                response = await get_response(request)
            finally:
                ctx.teardown()
                teardown_context(token)
            return response

        return async_middleware

    def sync_middleware(request: HttpRequest) -> HttpResponse:
        token = setup_context()
        nots, whitelist = _load_config()
        ctx = _DetectionContext(nots, whitelist)
        ctx.setup()
        try:
            response = get_response(request)
        finally:
            ctx.teardown()
            teardown_context(token)
        return response

    return sync_middleware
