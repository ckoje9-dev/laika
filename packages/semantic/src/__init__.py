"""Semantic analysis package for rule-based entity classification."""
from .rules import DEFAULT_RULES, SELECTION_RULE_MAP
from .matchers import match_rule, rules_from_selections
from .builder import build_semantic_records, build_all_records

__all__ = [
    "DEFAULT_RULES",
    "SELECTION_RULE_MAP",
    "match_rule",
    "rules_from_selections",
    "build_semantic_records",
    "build_all_records",
]
