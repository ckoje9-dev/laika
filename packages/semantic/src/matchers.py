"""Rule matching logic for entities."""
from typing import Any, Optional

from .rules import SELECTION_RULE_MAP


def match_rule(entity: dict[str, Any], rules: list[dict[str, Any]]) -> tuple[Optional[str], Optional[str]]:
    """Match entity against a list of rules.

    Args:
        entity: DXF entity dictionary
        rules: List of rule dictionaries

    Returns:
        Tuple of (kind, source_rule) if matched, (None, None) otherwise
    """
    layer = str(entity.get("layer") or entity.get("layerName") or "").upper()
    dtype = str(entity.get("type") or "").upper()
    name = str(entity.get("name") or entity.get("block") or entity.get("block_name") or "").upper()

    for rule in rules:
        keys = rule.get("keys") or []
        src = rule["source"]
        match_type = rule.get("match", "contains")

        if src == "layer":
            if match_type == "exact" and layer in keys:
                return rule["kind"], f"layer:{layer}"
            if match_type != "exact" and any(k in layer for k in keys):
                return rule["kind"], f"layer:{layer}"

        if src == "type":
            if match_type == "exact" and dtype in keys:
                return rule["kind"], f"type:{dtype}"
            if match_type != "exact" and any(k in dtype for k in keys):
                return rule["kind"], f"type:{dtype}"

        if src == "block":
            if match_type == "exact" and name in keys:
                return rule["kind"], f"block:{name}"
            if match_type != "exact" and any(k in name for k in keys):
                return rule["kind"], f"block:{name}"

    return None, None


def rules_from_selections(selections: dict[str, list[str]] | None) -> list[dict[str, Any]]:
    """Convert user selections to rule format.

    Args:
        selections: Dictionary of selection keys to selected values

    Returns:
        List of rule dictionaries
    """
    if not selections:
        return []

    rules: list[dict[str, Any]] = []
    for key, values in selections.items():
        if key not in SELECTION_RULE_MAP:
            continue

        kind, source = SELECTION_RULE_MAP[key]
        if not values:
            continue

        keys = [str(v).upper() for v in values if v]
        if not keys:
            continue

        rules.append({"kind": kind, "keys": keys, "source": source, "match": "exact"})

    return rules
