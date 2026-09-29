"""Corpus mode: eager loads and field loads that no test of the session reads.

Findings are ``(model label, field, load site)`` entries loaded somewhere and never read.
"""

import linecache
import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured

from django_nplus1 import detect, fields, signals
from django_nplus1.detect import EagerLoadMessage, Listener
from django_nplus1.middleware import DjangoRule

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.models import Model

    from django_nplus1.util import CallSite

UNUSED_FIELD_LOAD = "unused_field_load"

Entry = tuple[str, str, "CallSite"]


class CorpusTracker:
    """Load sites seen in the session, and the ones whose rows had the field read."""

    def __init__(self) -> None:
        self.loaded: set[Entry] = set()
        self.used: set[Entry] = set()

    def unused(self) -> list[Entry]:
        return sorted(self.loaded - self.used)

    def serialize(self) -> dict[str, list[list[Any]]]:
        return {
            "loaded": [[label, field, list(site)] for label, field, site in self.loaded],
            "used": [[label, field, list(site)] for label, field, site in self.used],
        }

    def merge(self, payload: dict[str, Any]) -> None:
        for name, entries in (("loaded", self.loaded), ("used", self.used)):
            for label, field, site in payload.get(name, ()):
                entries.add((label, field, tuple(site)))

    def reset(self) -> None:
        self.loaded.clear()
        self.used.clear()


TRACKERS = {EagerLoadMessage.label: CorpusTracker(), UNUSED_FIELD_LOAD: CorpusTracker()}


class _CorpusListener(Listener):
    label: str

    def setup(self) -> None:
        self.tracker = TRACKERS[self.label]
        # Primary keys repeat across tests, so a read only counts for rows loaded in
        # the same scope. Nested scopes share the outermost scope's rows.
        outer = self.parent.outer_listener(type(self))
        self.sites: defaultdict[tuple[type[Model], str], defaultdict[str, set[CallSite]]] = (
            outer.sites if outer is not None else defaultdict(lambda: defaultdict(set))
        )
        super().setup()

    def record_load(self, model: type[Model], field: str, keys: list[str], site: CallSite | None) -> None:
        if site is None:
            return
        self.tracker.loaded.add((model._meta.label, field, site))
        sites = self.sites[(model, field)]
        for key in keys:
            sites[key].add(site)

    def record_touch(self, model: type[Model], field: str, keys: list[str]) -> None:
        sites = self.sites.get((model, field))
        if not sites:
            return
        label = model._meta.label
        for key in keys:
            for site in sites.get(key, ()):
                self.tracker.used.add((label, field, site))


class CorpusEagerListener(_CorpusListener):
    label = EagerLoadMessage.label

    def handlers(self) -> dict[str, Callable[..., None]]:
        return {signals.EAGER_LOAD: self.handle_eager, signals.TOUCH: self.handle_touch}

    def handle_eager(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        model, field, keys, _group, site = parser(args, kwargs, context)
        self.record_load(model, field, keys, site)

    def handle_touch(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        self.record_touch(*parser(args, kwargs, context))


class CorpusFieldListener(_CorpusListener):
    label = UNUSED_FIELD_LOAD

    def handlers(self) -> dict[str, Callable[..., None]]:
        return {
            signals.FIELD_LOAD: self.handle_load,
            signals.FIELD_TOUCH: self.handle_touch,
            signals.TOUCH: self.handle_relation_touch,
        }

    def handle_load(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        self.record_load(*parser(args, kwargs, context))

    def handle_touch(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        self.record_touch(*parser(args, kwargs, context))

    def handle_relation_touch(self, args: Any, kwargs: Any, context: Any, ret: Any, parser: Any) -> None:
        # A cached forward relation is read without its foreign key column, but needs it.
        model, name, keys = parser(args, kwargs, context)
        try:
            attname = model._meta.get_field(name).attname
        except FieldDoesNotExist, AttributeError:
            return
        self.record_touch(model, attname, keys)


_enabled = False


def is_enabled() -> bool:
    return _enabled


def activate() -> None:
    """Start collecting, with empty findings."""
    global _enabled  # noqa: PLW0603
    for tracker in TRACKERS.values():
        tracker.reset()
    if _enabled:
        return
    detect.LISTENERS["eager_load"] = CorpusEagerListener
    detect.LISTENERS["field_load"] = CorpusFieldListener
    fields.patch_deferred_attribute()
    _enabled = True


def deactivate() -> None:
    """Stop collecting and restore the per-scope eager load detection. Findings stay readable."""
    global _enabled  # noqa: PLW0603
    detect.LISTENERS["eager_load"] = detect.EagerListener
    detect.LISTENERS.pop("field_load", None)
    fields.unpatch_deferred_attribute()
    _enabled = False


def serialize() -> dict[str, Any]:
    return {label: tracker.serialize() for label, tracker in TRACKERS.items()}


def merge(payload: dict[str, Any]) -> None:
    """Add the findings of another process, such as a pytest-xdist worker."""
    for label, tracker in TRACKERS.items():
        tracker.merge(payload.get(label, {}))


_INLINE_CORPUS_IGNORE_RE = re.compile(r"#\s*nplus1:\s*corpus-ignore")


def _is_inline_corpus_ignored(site: CallSite) -> bool:
    filename, lineno, _ = site
    return bool(_INLINE_CORPUS_IGNORE_RE.search(linecache.getline(filename, lineno)))


def _whitelist_rules() -> list[DjangoRule]:
    try:
        whitelist = getattr(settings, "NPLUS1_WHITELIST", [])
    except ImproperlyConfigured:
        return []
    return [DjangoRule(**item) for item in whitelist]


def report(label: str) -> list[tuple[type[Model], str, CallSite]]:
    """Return the unused loads for ``label``, minus whitelisted and ``corpus-ignore`` sites."""
    rules = _whitelist_rules()
    findings = []
    for model_label, field, site in TRACKERS[label].unused():
        try:
            model = apps.get_model(model_label)
        except LookupError:
            continue
        if _is_inline_corpus_ignored(site) or any(rule.compare(label, model, field) for rule in rules):
            continue
        findings.append((model, field, site))
    return findings


def format_findings(label: str, findings: list[tuple[type[Model], str, CallSite]]) -> str:
    count = len(findings)
    lines = [f"django-nplus1: corpus-wide {label} ({count} finding{'' if count == 1 else 's'})"]
    for model, field, (filename, lineno, funcname) in findings:
        name = f"{model.__name__}.{field}"
        lines.append(f"  {name:30} at {filename}:{lineno} in {funcname}")
    return "\n".join(lines)
