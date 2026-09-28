"""AgentCore Platform v1.0"""

# Outer pre_process — S-1 trust gate (VERIFIED_EXTERNAL, matches config/agent.yaml
# for this outer-boundary node) + S-2 deterministic input scan: regex/pattern
# check for credential-like strings and facility/patient identifiers embedded
# in free text. Clean input passes through unchanged (NOT an LLM check).

import json
import re
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

_CREDENTIAL_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.]+"),
    re.compile(r"eyJ[A-Za-z0-9._-]{10,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r'"(api_key|secret|password|token)"\s*:\s*"[^"]+"', re.IGNORECASE),
]
_IDENTIFIER_PATTERNS = [
    re.compile(r"\bpatient[_ ]?id\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\bmrn\s*[:=]\s*\S+", re.IGNORECASE),
]


class InputValidateNode(FunctionNode):
    """Parses the caller's JSON envelope ({recall_text, inventory_rows}) and
    scans for credential-like strings / facility-patient identifiers before
    the recall notice enters the parse->match->render pipeline.
    """

    # S-1: outer boundary node — matches config/agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "") or ""
        for pattern in _CREDENTIAL_PATTERNS:
            if pattern.search(raw):
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": ["S-2: credential-like pattern detected in recall input"],
                }
        for pattern in _IDENTIFIER_PATTERNS:
            if pattern.search(raw):
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": ["S-2: facility/patient identifier detected in recall input"],
                }
        return state

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "") or ""
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except (ValueError, TypeError):
            emit_trace_event(
                "input_validate_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "invalid_json"},
                state,
            )
            return {"status": AgentStatus.ERROR.value, "error_log": ["InputValidate: user_input is not valid JSON"]}

        recall_text = (payload.get("recall_text") or "").strip() if isinstance(payload, dict) else ""
        inventory_rows = payload.get("inventory_rows") or [] if isinstance(payload, dict) else []

        if not recall_text:
            emit_trace_event(
                "input_validate_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "empty_recall_text"},
                state,
            )
            return {"status": AgentStatus.ERROR.value, "error_log": ["InputValidate: recall_text is empty"]}

        validated_input = json.dumps({"recall_text": recall_text, "inventory_rows": inventory_rows}, ensure_ascii=False)
        emit_trace_event(
            "input_validated",
            {"correlation_id": state.get("correlation_id"), "inventory_row_count": len(inventory_rows)},
            state,
        )
        return {
            "recall_text": recall_text,
            "inventory_rows": inventory_rows,
            "validated_input": validated_input,
            "status": AgentStatus.SUCCESS.value,
        }
