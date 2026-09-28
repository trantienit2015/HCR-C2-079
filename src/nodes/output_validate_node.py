"""AgentCore Platform v1.0"""

# Outer post_process — S-3 deterministic output gate. Two checks, BOTH fail the
# whole package (never a per-field drop): (a) claim-structure grounding
# validation on the escalation packet built by the inner pipeline (business
# logic, inside execute() -> ERROR dict, never raise); (b) credential-pattern
# scan on the node's own formatted_output via the _extra_security_gate_output
# hook (own-output-key re-check, not upstream state).

import json
import re
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.escalation_rules import APPROVED_ACTION_RULE_IDS

_CREDENTIAL_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.]+"),
    re.compile(r"eyJ[A-Za-z0-9._-]{10,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
]


def _claims_are_grounded(claims: list[Any]) -> bool:
    for claim in claims:
        if not claim.get("parsed_criterion_id") or not claim.get("match_result_id"):
            return False
        if not claim.get("inventory_record_ids"):
            return False
        if claim.get("action_rule_id") not in APPROVED_ACTION_RULE_IDS:
            return False
    return True


class OutputValidateNode(FunctionNode):
    """Whole-package pass/fail validation of the escalation packet."""

    # S-1: outer boundary node — matches config/agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        formatted = state.get("formatted_output")
        text = json.dumps(formatted, ensure_ascii=False) if formatted else ""
        for pattern in _CREDENTIAL_PATTERNS:
            if pattern.search(text):
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": ["S-3: credential pattern detected in formatted_output — whole package rejected"],
                }
        return state

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        packet = state.get("escalation_packet") or {}
        match_status = packet.get("match_status")
        claims = packet.get("claims", [])

        if match_status is None:
            emit_trace_event(
                "output_validate_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "missing_escalation_packet"},
                state,
            )
            return {"status": AgentStatus.ERROR.value, "error_log": ["OutputValidate: escalation_packet missing"]}

        if match_status in ("exact", "possible") and not claims:
            emit_trace_event(
                "output_validate_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "unresolved_without_claims"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["OutputValidate: match_status requires escalation but no grounded claims present"],
            }

        if claims and not _claims_are_grounded(claims):
            emit_trace_event(
                "output_validate_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "ungrounded_claim"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["OutputValidate: claim missing required grounding fields — whole package rejected"],
            }

        emit_trace_event(
            "output_validated",
            {"correlation_id": state.get("correlation_id"), "match_status": match_status, "claim_count": len(claims)},
            state,
        )
        return {"result": packet, "formatted_output": packet, "status": AgentStatus.SUCCESS.value}
