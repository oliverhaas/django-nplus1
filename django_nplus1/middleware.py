from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING, Any

from asgiref.sync import iscoroutinefunction
from django.apps import apps
from django.conf import settings
from django.utils.decorators import sync_and_async_middleware

from django_nplus1 import notifiers
from django_nplus1.detect import Rule
from django_nplus1.exceptions import NPlus1Error
from django_nplus1.scope import DetectionScope

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

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
            meta = getattr(model, "_meta", None)
            if meta is None:
                return False
            return fnmatch.fnmatch(
                f"{meta.app_label}.{model.__name__}",
                self.model,
            )
        return False


_last_validated_whitelist: tuple[int, int] | None = None


def _load_config() -> tuple[list[notifiers.Notifier], list[DjangoRule]]:
    """Load notifiers and whitelist from settings."""
    global _last_validated_whitelist  # noqa: PLW0603
    nots = notifiers.init(settings)
    whitelist_data = getattr(settings, "NPLUS1_WHITELIST", [])
    cache_key = (id(whitelist_data), len(whitelist_data))
    if cache_key != _last_validated_whitelist:
        _validate_whitelist(whitelist_data)
        _last_validated_whitelist = cache_key
    whitelist = [DjangoRule(**item) for item in whitelist_data]
    return nots, whitelist


@sync_and_async_middleware
def NPlus1Middleware(get_response: Any) -> Any:  # noqa: N802
    if iscoroutinefunction(get_response):

        async def async_middleware(request: HttpRequest) -> HttpResponse:
            nots, whitelist = _load_config()
            with DetectionScope(notifiers=nots, whitelist=whitelist, sender=NPlus1Middleware):
                return await get_response(request)

        return async_middleware

    def sync_middleware(request: HttpRequest) -> HttpResponse:
        nots, whitelist = _load_config()
        with DetectionScope(notifiers=nots, whitelist=whitelist, sender=NPlus1Middleware):
            return get_response(request)

    return sync_middleware
