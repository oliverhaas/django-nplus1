from __future__ import annotations

import fnmatch
import weakref
from typing import TYPE_CHECKING, Any

from django.conf import settings

from django_nplus1 import notifiers
from django_nplus1.detect import LISTENERS, Message, Rule

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from django_nplus1.detect import Listener


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


class NPlusOneMiddleware:
    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response
        self._listeners: weakref.WeakKeyDictionary[HttpRequest, dict[str, Listener]] = weakref.WeakKeyDictionary()
        self._notifiers: list[notifiers.Notifier] = []
        self._whitelist: list[DjangoRule] = []

    def _load_config(self) -> None:
        config = dict(vars(settings._wrapped))  # type: ignore[misc]
        self._notifiers = notifiers.init(config)
        self._whitelist = [DjangoRule(**item) for item in getattr(settings, "NPLUS1_WHITELIST", [])]

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self._load_config()
        self._listeners[request] = {}
        for name, listener_type in LISTENERS.items():
            self._listeners[request][name] = listener_type(self)
            self._listeners[request][name].setup()
        try:
            response = self.get_response(request)
        finally:
            for name in list(LISTENERS.keys()):
                listener = self._listeners.get(request, {}).pop(name, None)
                if listener:
                    listener.teardown()
        return response

    def notify(self, message: Message) -> None:
        if not message.match(self._whitelist):
            for notifier in self._notifiers:
                notifier.notify(message)
