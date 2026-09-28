"""AgentCore Platform v1.0"""

# Inner step 1 (Cat 2 subgraph) — LLM reasoning node: normalize the free-text
# recall notice into structured lot number(s)/range, device/product identifier,
# and affected-location criteria, plus a deterministic parse_confidence (0-1)
# computed from field-completeness + grammar match.

import json
import re
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.lot_matcher import LOT_GRAMMAR

# No-LLM fallback: a lot number is the token directly after a "lot" keyword
# (optionally "lot number" / "lot no." / "lot #") that also matches LOT_GRAMMAR.
# Every quantifier is bounded.
_LOT_KEYWORD_TOKEN = re.compile(
    r"\blots?\b(?:\s{1,5}(?:number|no\.?|#))?\s{0,5}[:#]?\s{0,5}([A-Za-z0-9]{3,20}(?:-[A-Za-z0-9]{3,20})?)",
    re.IGNORECASE,
)


def _fallback_lot_numbers(recall_text: str) -> list[str]:
    """Deterministic lot-number extraction used only when no LLM is configured."""
    found: list[str] = []
    for match in _LOT_KEYWORD_TOKEN.finditer(recall_text):
        token = match.group(1)
        if LOT_GRAMMAR.match(token) and token not in found:
            found.append(token)
    return found


class RecallParseNode(FunctionNode):
    """Parses recall_text (+ inventory_rows passthrough) into parsed_criteria."""

    # S-1: inner subgraph node — trust authenticated once at the outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    @staticmethod
    def _extract_text(raw: Any) -> str:
        """Normalise an LLM response into assistant text.

        AgentCore BaseLLM.complete() returns the canonical dict
        {"content": str, ...}; a bare string is also accepted for
        backward-compatible fakes. Anything else yields "".
        """
        if isinstance(raw, dict):
            content = raw.get("content", "")
            return content if isinstance(content, str) else ""
        if isinstance(raw, str):
            return raw
        return ""

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) and raw.strip() else raw
        except (ValueError, TypeError):
            payload = None

        if not isinstance(payload, dict) or not (payload.get("recall_text") or "").strip():
            emit_trace_event(
                "recall_parse_rejected",
                {"correlation_id": state.get("correlation_id"), "reason": "missing_or_empty_recall_text"},
                state,
            )
            return {"status": AgentStatus.ERROR.value, "error_log": ["RecallParse: recall_text missing or empty"]}

        recall_text = payload["recall_text"]
        inventory_rows = payload.get("inventory_rows") or []

        extracted: dict[str, Any] = {}
        parse_method = "llm"
        if self._llm is None:
            # No LLM configured (for example a standalone deployment without a provider
            # key): deterministic keyword extraction of lot numbers only. Location and
            # product stay empty, so parse_confidence remains below the 0.7 exact-match
            # threshold and the lot matcher can only return "possible" (compliance
            # review), never an "exact" or "no_match" decided by a heuristic parse.
            parse_method = "deterministic_fallback"
            extracted = {"lot_numbers": _fallback_lot_numbers(recall_text)}
        else:
            # BaseLLM.complete() requires `messages: list` — pass the canonical
            # system/user message list, not a bare prompt string.
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You extract structured recall criteria from sterile-supply "
                        "recall notices. Respond as JSON with keys lot_numbers "
                        "(list), product_id, location_scope."
                    ),
                },
                {"role": "user", "content": recall_text},
            ]
            try:
                text = self._extract_text(self._llm.complete(messages))
            except (ConnectionError, TimeoutError, ValueError, RuntimeError) as exc:
                # S-4: non-sensitive degradation event — exception type only, no
                # recall/patient content.
                emit_trace_event(
                    "recall_parse_llm_failed",
                    {"correlation_id": state.get("correlation_id"), "reason": type(exc).__name__},
                    state,
                )
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": [f"RecallParse: configured LLM call failed ({type(exc).__name__})"],
                }

            try:
                extracted = json.loads(text) if text else {}
                if not isinstance(extracted, dict):
                    extracted = {}
            except (ValueError, TypeError):
                extracted = {}

            if not extracted:
                # An LLM WAS configured but returned an empty/non-JSON/invalid
                # response — a provider/protocol failure, NOT the no-LLM
                # deterministic mode. Surface ERROR instead of silently
                # degrading to a fabricated low-confidence parse.
                emit_trace_event(
                    "recall_parse_llm_degraded",
                    {"correlation_id": state.get("correlation_id"), "reason": "empty_or_invalid_response"},
                    state,
                )
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": ["RecallParse: configured LLM returned an empty/invalid response"],
                }

        lot_numbers = extracted.get("lot_numbers") or []
        product_id = extracted.get("product_id") or ""
        location_scope = extracted.get("location_scope") or ""

        fields_present = sum(1 for v in (lot_numbers, product_id, location_scope) if v)
        completeness = fields_present / 3
        grammar_ok = bool(lot_numbers) and all(bool(LOT_GRAMMAR.match(str(lot))) for lot in lot_numbers)
        parse_confidence = round((completeness * 0.6) + (0.4 if grammar_ok else 0.0), 2)

        parsed_criteria = {
            "lot_numbers": lot_numbers,
            "product_id": product_id,
            "location_scope": location_scope,
            "parse_confidence": parse_confidence,
            "parse_method": parse_method,
        }
        emit_trace_event(
            "recall_parsed",
            {
                "correlation_id": state.get("correlation_id"),
                "lot_count": len(lot_numbers),
                "parse_confidence": parse_confidence,
                "parse_method": parse_method,
            },
            state,
        )
        return {
            "parsed_criteria": parsed_criteria,
            "inventory_rows": inventory_rows,
            "status": AgentStatus.SUCCESS.value,
        }
