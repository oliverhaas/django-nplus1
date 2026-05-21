from __future__ import annotations

from collections import defaultdict
from typing import Any

CallSite = tuple[str, int, str]


class CorpusEagerTracker:
    """Session-lifetime accumulator for unused eager-load detection.

    `data` maps (model, field, call_site) to the set of instance keys ever
    loaded at that declaration site. `touched` maps (model, field) to the
    set of instance keys ever accessed. An entry in `data` is "unused"
    iff none of its instance keys appear in `touched[(model, field)]`.
    """

    def __init__(self) -> None:
        self.data: dict[tuple[type, str, CallSite], set[str]] = defaultdict(set)
        self.touched: dict[tuple[type, str], set[str]] = defaultdict(set)

    def record_load(self, model: type, field: str, instances: list[str], site: CallSite) -> None:
        self.data[(model, field, site)].update(instances)

    def record_touch(self, model: type, field: str, instance_keys: list[str]) -> None:
        self.touched[(model, field)].update(instance_keys)

    def unused(self) -> list[tuple[type, str, CallSite]]:
        result = []
        for (model, field, site), insts in self.data.items():
            if not insts & self.touched.get((model, field), set()):
                result.append((model, field, site))
        return result

    def serialize(self) -> dict[str, Any]:
        return {
            "data": [
                {
                    "model": f"{m.__module__}.{m.__qualname__}",
                    "field": f,
                    "site": list(s),
                    "instances": sorted(insts),
                }
                for (m, f, s), insts in self.data.items()
            ],
            "touched": [
                {
                    "model": f"{m.__module__}.{m.__qualname__}",
                    "field": f,
                    "instances": sorted(insts),
                }
                for (m, f), insts in self.touched.items()
            ],
        }

    def merge(self, payload: dict[str, Any]) -> None:
        for entry in payload.get("data", []):
            model = _resolve_model(entry["model"])
            site = tuple(entry["site"])
            self.data[(model, entry["field"], site)].update(entry["instances"])
        for entry in payload.get("touched", []):
            model = _resolve_model(entry["model"])
            self.touched[(model, entry["field"])].update(entry["instances"])


_model_resolver_cache: dict[str, type] = {}


def _resolve_model(dotted: str) -> type:
    cached = _model_resolver_cache.get(dotted)
    if cached is not None:
        return cached
    import importlib

    module_name, _, qual = dotted.rpartition(".")
    obj: Any = importlib.import_module(module_name)
    for part in qual.split("."):
        obj = getattr(obj, part)
    _model_resolver_cache[dotted] = obj
    return obj
