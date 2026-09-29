"""Field-level load and read tracking for corpus mode.

Corpus mode gives DeferredAttribute a ``__set__``, which turns it into a data descriptor,
so every read of a loaded field runs ``__get__`` and reports a FIELD_TOUCH.
"""

import fnmatch
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db.models.query_utils import DeferredAttribute

from django_nplus1 import signals
from django_nplus1.util import to_key

if TYPE_CHECKING:
    from django.db.models import Model

    from django_nplus1.util import CallSite


def _set(self: DeferredAttribute, instance: Model, value: Any) -> None:
    instance.__dict__[self.field.attname] = value


def _delete(self: DeferredAttribute, instance: Model) -> None:
    try:
        del instance.__dict__[self.field.attname]
    except KeyError:
        raise AttributeError(self.field.attname) from None


def patch_deferred_attribute() -> None:
    """Make DeferredAttribute a data descriptor. Idempotent."""
    DeferredAttribute.__set__ = _set  # type: ignore[attr-defined]
    DeferredAttribute.__delete__ = _delete  # type: ignore[attr-defined]


def unpatch_deferred_attribute() -> None:
    """Restore DeferredAttribute as a non-data descriptor. Idempotent."""
    for name in ("__set__", "__delete__"):
        if name in DeferredAttribute.__dict__:
            delattr(DeferredAttribute, name)


def _excluded(model: type[Model]) -> bool:
    """Check ``NPLUS1_FIELD_EXCLUDE``, whose patterns match ``app_label.ModelName``."""
    label = model._meta.label
    return any(fnmatch.fnmatch(label, pattern) for pattern in getattr(settings, "NPLUS1_FIELD_EXCLUDE", ()))


def emit_field_loads(instances: list[Model], site: CallSite | None) -> None:
    """Report a FIELD_LOAD for each loaded concrete field of the rows, except primary keys."""
    model = type(instances[0])
    if _excluded(model):
        return
    meta = model._meta
    loaded = instances[0].__dict__
    key_attnames = {field.attname for field in meta.pk_fields}
    keys = [to_key(instance) for instance in instances]
    for field in meta.concrete_fields:
        if field.attname in loaded and not field.primary_key and field.attname not in key_attnames:
            signals.emit(signals.FIELD_LOAD, model, field.attname, keys, site)
