from __future__ import annotations

import fnmatch
import weakref
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from django.apps import apps
from django.conf import settings

from django_nplus1 import notifiers
from django_nplus1.detect import LISTENERS, Message, Rule
from django_nplus1.exceptions import NPlus1Error
from django_nplus1.signals import _listeners, nplus1_detected

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
        fields |= {rel.get_accessor_name() for rel in model._meta.related_objects}
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


class NPlus1Middleware:
    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response
        self._request_listeners: weakref.WeakKeyDictionary[HttpRequest, dict[str, Listener]] = (
            weakref.WeakKeyDictionary()
        )
        self._notifiers: list[notifiers.Notifier] = []
        self._whitelist: list[DjangoRule] = []

    def _load_config(self) -> None:
        self._notifiers = notifiers.init(settings)
        whitelist_data = getattr(settings, "NPLUS1_WHITELIST", [])
        _validate_whitelist(whitelist_data)
        self._whitelist = [DjangoRule(**item) for item in whitelist_data]

    def __call__(self, request: HttpRequest) -> HttpResponse:
        token = _listeners.set(defaultdict(list))
        self._load_config()
        self._request_listeners[request] = {}
        for name, listener_type in LISTENERS.items():
            self._request_listeners[request][name] = listener_type(self)
            self._request_listeners[request][name].setup()
        try:
            response = self.get_response(request)
        finally:
            for name in list(LISTENERS.keys()):
                listener = self._request_listeners.get(request, {}).pop(name, None)
                if listener:
                    listener.teardown()
            _listeners.reset(token)
        return response

    def notify(self, message: Message) -> None:
        if not message.match(self._whitelist):
            nplus1_detected.send(sender=self.__class__, message=message)
            for notifier in self._notifiers:
                notifier.notify(message)
