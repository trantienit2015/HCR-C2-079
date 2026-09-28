"""AgentCore Platform v1.0"""

# Inner step 2 (Cat 2 subgraph) — FunctionNode wrapping the deterministic
# src/services/lot_matcher.py helper (the "shared/tools/"-equivalent per the
# Agent-vs-Tool boundary). Not a graph node in
# its own right in the sense of holding LLM/reasoning logic — pure orchestration
# of the deterministic tool call + classification.

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.lot_matcher import match_lot


class LotMatchNode(FunctionNode):
    """Calls the deterministic lot_matcher against parsed_criteria + inventory_rows."""

    # S-1: inner subgraph node — trust authenticated once at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        parsed_criteria = state.get("parsed_criteria") or {}
        inventory_rows = state.get("inventory_rows") or []

        if not parsed_criteria:
            emit_trace_event(
                "lot_match_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "missing_parsed_criteria"},
                state,
            )
            return {"status": AgentStatus.ERROR.value, "error_log": ["LotMatch: parsed_criteria missing"]}

        match_result = match_lot(parsed_criteria, inventory_rows)
        emit_trace_event(
            "lot_match_computed",
            {
                "correlation_id": state.get("correlation_id"),
                "match_status": match_result["status"],
                "candidate_count": len(match_result["matched_records"]),
            },
            state,
        )
        return {"match_result": match_result, "status": AgentStatus.SUCCESS.value}
