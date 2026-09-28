"""AgentCore Platform v1.0"""

# Inner step 3 (Cat 2 subgraph) — LLM reasoning node: assemble match evidence
# into structured escalation claims ONLY (no free-form injection). Each claim
# = {claim_text, parsed_criterion_id, match_result_id, match_status,
#    inventory_record_ids[], source_span, action_rule_id}. action_rule_id must
# reference a pre-approved facility escalation-rule entry (never invented
# wording) — packet text is rendered strictly from these claim fields.

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.escalation_rules import (
    ACTION_RULE_BY_MATCH_STATUS,
    ACTION_WORDING,
    APPROVED_ACTION_RULE_IDS,
)


class EscalationRenderNode(FunctionNode):
    """Assembles match_result into a structured escalation_packet."""

    # S-1: inner subgraph node — trust authenticated once at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        match_result = state.get("match_result") or {}
        parsed_criteria = state.get("parsed_criteria") or {}

        if not match_result:
            emit_trace_event(
                "escalation_render_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "missing_match_result"},
                state,
            )
            return {"status": AgentStatus.ERROR.value, "error_log": ["EscalationRender: match_result missing"]}

        match_status = match_result.get("status", "possible")
        action_rule_id = ACTION_RULE_BY_MATCH_STATUS.get(match_status, "compliance_notify")
        assert action_rule_id in APPROVED_ACTION_RULE_IDS  # defensive — closed set above

        claims = []
        for idx, record in enumerate(match_result.get("matched_records", [])):
            record_id = f"{record.get('lot_number', '')}:{record.get('location_id', '')}"
            claims.append(
                {
                    "claim_text": (
                        f"Lot {record.get('lot_number')} at location {record.get('location_id')} "
                        f"matches recall criteria ({match_result.get('confidence_basis')})."
                    ),
                    "parsed_criterion_id": "parsed_criteria_1",
                    "match_result_id": f"match_result_{idx}",
                    "match_status": match_status,
                    "inventory_record_ids": [record_id],
                    "source_span": parsed_criteria.get("location_scope", ""),
                    "action_rule_id": action_rule_id,
                }
            )

        escalation_packet = {
            "summary": f"Recall lot match resolved as '{match_status}' ({match_result.get('confidence_basis')}).",
            "claims": claims,
            "recommended_action": ACTION_WORDING[action_rule_id],
            "match_status": match_status,
        }
        emit_trace_event(
            "escalation_rendered",
            {
                "correlation_id": state.get("correlation_id"),
                "claim_count": len(claims),
                "match_status": match_status,
            },
            state,
        )
        return {"escalation_packet": escalation_packet, "status": AgentStatus.SUCCESS.value}
