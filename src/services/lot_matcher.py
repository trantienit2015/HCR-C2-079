"""AgentCore Platform v1.0"""

# Deterministic lot/location matcher — the "shared/tools/"-equivalent helper
# (Agent-vs-Tool boundary): a pure
# function with no state, no side effects, no security gates. Invoked by
# LotMatchNode (src/nodes/lot_match_node.py), never registered as a graph node.
#
# Deterministic status-rule contract (locked, docs/02_design.md):
#   parse_confidence < 0.7                -> possible
#   malformed/missing lot number(s)       -> possible
#   >1 distinct matching location code    -> possible
#   candidate count > CANDIDATE_CAP       -> possible
#   exact key match, confidence >= 0.7,
#     unambiguous location               -> exact
#   zero candidates, no ambiguity/malform -> no_match
#   anything not enumerated above        -> possible (fail-safe, never
#                                            silently collapses to no_match)

from __future__ import annotations

import re
from typing import Any

LOT_GRAMMAR = re.compile(r"^[A-Z0-9]{3,20}(-[A-Z0-9]{3,20})?$")
CANDIDATE_CAP = 20


def match_lot(parsed_criteria: dict[str, Any], inventory_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Match parsed recall criteria against read-only lot/location inventory.

    parsed_criteria: {lot_numbers: list[str], product_id: str,
                       location_scope: str, parse_confidence: float}
    inventory_rows: list of {lot_number: str, location_id: str, ...}

    Returns {status, matched_records, confidence_basis, status_reason}.
    """
    lot_numbers = parsed_criteria.get("lot_numbers") or []
    location_scope = parsed_criteria.get("location_scope") or None
    parse_confidence = parsed_criteria.get("parse_confidence", 0.0) or 0.0

    malformed = (not lot_numbers) or any(not LOT_GRAMMAR.match(str(lot)) for lot in lot_numbers)

    def _is_candidate(row: dict[str, Any]) -> bool:
        if row.get("lot_number") not in lot_numbers:
            return False
        if location_scope is not None and row.get("location_id") != location_scope:
            return False
        return True

    candidates = [row for row in inventory_rows if _is_candidate(row)]
    matching_locations = {row.get("location_id") for row in candidates}
    location_ambiguous = len(matching_locations) > 1
    overflow = len(candidates) > CANDIDATE_CAP

    if parse_confidence < 0.7:
        status, basis, reason = (
            "possible",
            "sub_threshold_parse_confidence",
            f"parse_confidence {parse_confidence} < 0.7",
        )
    elif malformed:
        status, basis, reason = (
            "possible",
            "malformed_lot_range",
            "lot number(s) missing or failed normalized grammar",
        )
    elif location_ambiguous:
        status, basis, reason = (
            "possible",
            "location_ambiguous",
            f"{len(matching_locations)} distinct location codes matched",
        )
    elif overflow:
        status, basis, reason = (
            "possible",
            "candidate_cap_overflow",
            f">{CANDIDATE_CAP} candidate matches",
        )
    elif candidates:
        status, basis, reason = (
            "exact",
            "exact_key_match",
            "exact lot+location match, parse_confidence >= 0.7",
        )
    elif not candidates:
        status, basis, reason = (
            "no_match",
            "zero_candidates",
            "no inventory rows matched lot/location criteria",
        )
    else:  # pragma: no cover - fail-safe branch, all conditions above are exhaustive
        status, basis, reason = (
            "possible",
            "unenumerated_condition",
            "condition not explicitly enumerated — fail-safe to possible",
        )

    return {
        "status": status,
        "matched_records": candidates[:CANDIDATE_CAP],
        "confidence_basis": basis,
        "status_reason": reason,
    }
