import contextlib
import copy
import fnmatch
import warnings
from inspect import iscoroutinefunction, markcoroutinefunction
from typing import TYPE_CHECKING, Any

from django.apps import apps
from django.conf import settings

from django_nplus1 import conf, notifiers
from django_nplus1.detect import DuplicateQueryMessage, Rule
from django_nplus1.exceptions import NPlus1Error
from django_nplus1.scope import DetectionContext

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Sequence

    from django.db.models import Model
    from django.http import HttpRequest

_PATTERN_CHARS = frozenset("*?[")


def _is_pattern(value: str) -> bool:
    return not _PATTERN_CHARS.isdisjoint(value)


def _field_names(model: type[Model]) -> set[str]:
    meta = model._meta
    names = {"get()"}
    names.update(field.name for field in meta.get_fields(include_hidden=True))
    names.update(field.attname for field in meta.concrete_fields)
    names.update(name for rel in meta.related_objects if (name := rel.get_accessor_name()))
    return names


def validate_whitelist(whitelist: Sequence[dict[str, Any]]) -> None:
    """Check ``NPLUS1_WHITELIST`` entries against the installed models.

    An unknown model raises ``NPlus1Error``. An unknown field only warns, because a
    ``Prefetch(to_attr=...)`` name is no model field.
    """
    registry = {model._meta.label: model for model in apps.get_models()}
    for entry in whitelist:
        name = entry.get("model")
        if isinstance(name, type):
            meta = name.__dict__.get("_meta")
            if meta is None:
                continue
            name = meta.label
        if not isinstance(name, str) or _is_pattern(name):
            continue
        model = registry.get(name)
        if model is None:
            suffix = name.rsplit(".", 1)[-1].lower()
            similar = sorted(label for label in registry if suffix in label.lower())[:3]
            msg = f"NPLUS1_WHITELIST: model '{name}' not found in installed Django models."
            if similar:
                msg += f" Did you mean one of: {', '.join(similar)}?"
            raise NPlus1Error(msg)
        field = entry.get("field")
        if entry.get("label") == DuplicateQueryMessage.label or not isinstance(field, str) or _is_pattern(field):
            continue
        if field not in _field_names(model):
            warnings.warn(
                f"NPLUS1_WHITELIST: '{field}' is not a field of '{name}'. "
                "Only a Prefetch(to_attr=...) name is expected here.",
                UserWarning,
                stacklevel=2,
            )


class DjangoRule(Rule):
    """A ``NPLUS1_WHITELIST`` entry. Model names match ``app_label.ModelName`` only."""

    def match_class(self, cls: type) -> bool:
        if self.model is cls:
            return True
        meta = cls.__dict__.get("_meta")
        return isinstance(self.model, str) and meta is not None and fnmatch.fnmatch(meta.label, self.model)


_validated_whitelist: list[dict[str, Any]] | None = None


def whitelist_rules() -> list[DjangoRule]:
    """Read ``NPLUS1_WHITELIST``. An entry naming an unknown model raises ``NPlus1Error``."""
    global _validated_whitelist  # noqa: PLW0603
    whitelist = list(getattr(settings, "NPLUS1_WHITELIST", []))
    # A copy, so entries added to the settings list in place get validated too.
    if whitelist != _validated_whitelist:
        validate_whitelist(whitelist)
        _validated_whitelist = copy.deepcopy(whitelist)
    return [DjangoRule(**item) for item in whitelist]


def load_config() -> tuple[list[notifiers.Notifier], list[DjangoRule]]:
    """Read the notifiers and the whitelist from settings. Invalid settings raise."""
    nots = notifiers.init(settings)
    conf.check_thresholds(settings)
    conf.project_packages(settings)
    return nots, whitelist_rules()


_VIEW_EXCEPTION = "_nplus1_view_exception"


class NPlus1Middleware:
    """Detects N+1 queries per request and reports them through the ``NPLUS1_*`` notifiers."""

    async_capable = True
    sync_capable = True

    def __init__(self, get_response: Callable[[HttpRequest], Any]) -> None:
        self.get_response = get_response
        # Invalid settings fail at startup instead of on the first request.
        conf.check_installed()
        load_config()
        if iscoroutinefunction(get_response):
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> Any:
        if iscoroutinefunction(self):
            return self.__acall__(request)
        with self._detect(request):
            return self.get_response(request)

    async def __acall__(self, request: HttpRequest) -> Any:
        with self._detect(request):
            return await self.get_response(request)

    def process_exception(self, request: HttpRequest, exception: Exception) -> None:
        # Django turns a view's exception into an error response before it reaches
        # __call__. Keep it, so detections at the end of the request don't replace it.
        request.__dict__[_VIEW_EXCEPTION] = exception

    @contextlib.contextmanager
    def _detect(self, request: HttpRequest) -> Generator[None]:
        nots, whitelist = load_config()
        scope = DetectionContext(notifiers=nots, whitelist=whitelist, sender=NPlus1Middleware)
        scope.__enter__()
        try:
            yield
        except BaseException as exc:
            scope.__exit__(type(exc), exc, exc.__traceback__)
            raise
        view_exception = request.__dict__.pop(_VIEW_EXCEPTION, None)
        if view_exception is None:
            scope.__exit__(None, None, None)
        else:
            scope.__exit__(type(view_exception), view_exception, view_exception.__traceback__)
