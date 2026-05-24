"""Concrete-field touch detection: data-descriptor patch on DeferredAttribute.

When corpus mode is active, DeferredAttribute is converted into a data
descriptor with both ``__set__`` and a wrapped ``__get__``. ``__set__``
routes writes into a per-instance side cache instead of ``__dict__``;
``__get__`` reads from the side cache and fires a FIELD_TOUCH signal on
every access. The combined effect: every concrete-field read passes
through our hook, matching the semantic "if this field were deferred,
would the access cause a database query?".

The fall-through path (cache miss) preserves Django's original
``_check_parent_chain`` behavior, so accesses to actually-deferred
fields still trigger LAZY_LOAD detection unchanged.
"""

from typing import Any

from django.db.models.query_utils import DeferredAttribute

from django_nplus1 import signals

_FIELD_CACHE_KEY = "_nplus1_field_cache"

_original_get: Any = None
_patched: bool = False


def _patched_set(self: Any, instance: Any, value: Any) -> None:
    cache = instance.__dict__.get(_FIELD_CACHE_KEY)
    if cache is None:
        cache = {}
        instance.__dict__[_FIELD_CACHE_KEY] = cache
    cache[self.field.attname] = value


def _safe_key(instance: Any) -> str:
    """Derive a stable key for *instance* without going through __get__.

    ``to_key`` calls ``instance.pk`` which resolves via the descriptor chain.
    While ``_patched_get`` is active that would recurse back into itself, so
    we read the pk attname directly from __dict__ and the side cache instead.
    """
    meta = type(instance)._meta
    pk_attname = meta.pk.attname
    # Look in the side cache first, then the real instance dict.
    cache = instance.__dict__.get(_FIELD_CACHE_KEY)
    pk = cache[pk_attname] if cache is not None and pk_attname in cache else instance.__dict__.get(pk_attname)
    if pk is None:
        return f"{type(instance).__name__}:{id(instance)}"
    return f"{type(instance).__name__}:{pk}"


def _patched_get(self: Any, instance: Any, cls: Any = None) -> Any:
    if instance is None:
        return self
    cache = instance.__dict__.get(_FIELD_CACHE_KEY)
    attname = self.field.attname
    if cache is not None and attname in cache:
        signals.send(
            signals.FIELD_TOUCH,
            args=(type(instance), attname, [_safe_key(instance)]),
            kwargs={},
            ret=None,
            context={},
            parser=_parse_field_touch,
        )
        return cache[attname]
    return _original_get(self, instance, cls)


def _parse_field_touch(
    args: Any,
    kwargs: Any,
    context: Any,
) -> tuple[type, str, list[str]]:
    model, field, keys = args
    return model, field, keys


def _patch_deferred_attribute() -> None:
    """Convert DeferredAttribute into a data descriptor. Idempotent."""
    global _original_get, _patched  # noqa: PLW0603
    if _patched:
        return
    _original_get = DeferredAttribute.__get__
    DeferredAttribute.__get__ = _patched_get  # type: ignore[method-assign]
    DeferredAttribute.__set__ = _patched_set  # type: ignore[attr-defined]
    _patched = True


def _unpatch_deferred_attribute() -> None:
    """Restore the original DeferredAttribute (test-only helper)."""
    global _original_get, _patched  # noqa: PLW0603
    if not _patched:
        return
    DeferredAttribute.__get__ = _original_get  # type: ignore[method-assign]
    del DeferredAttribute.__set__  # type: ignore[attr-defined]
    _original_get = None
    _patched = False
