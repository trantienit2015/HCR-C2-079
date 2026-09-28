"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict (see ADR-005 for the prohibited
# alternatives). LangGraph checkpoints use msgpack serialization, so only
# plain serializable fields are allowed. Do NOT add credentials or secrets.

from typing import NotRequired

from framework.schemas.agent_state import AgentState


# Type-check note: the wheel ships no py.typed, so mypy resolves AgentState to Any
# and reports every NotRequired below as valid-type. The fields are correct (the state
# contract requires NotRequired) -- the report is a packaging artifact, suppressed per field.
# Drop these ignores once the wheel ships py.typed.
class State(AgentState):
    """Agent state for HCR-C2-079 (Healthcare Facility Sterile-Supply Recall
    Lot Match Escalation Agent).

    Shared fields (user_input, validated_input, status, session_id,
    node_history, error_log, hitl_*, etc.) are inherited from AgentState.
    Only agent-specific fields are declared below, all wrapped in
    NotRequired[...] (a bare field is not msgpack-checkpoint-safe and
    causes KeyError when a node downstream in the pipeline runs before the
    field is written).
    """

    # Raw recall notice text submitted by the caller (pre-sanitization).
    recall_text: NotRequired[str]  # type: ignore[valid-type]

    # Read-only lot/location inventory rows to match against.
    inventory_rows: NotRequired[list[dict]]  # type: ignore[valid-type]

    # Structured match criteria produced by RecallParse (inner step 1).
    # Shape: {lot_numbers: list[str], product_id: str, location_scope: str,
    #         parse_confidence: float}
    parsed_criteria: NotRequired[dict]  # type: ignore[valid-type]

    # Match result produced by LotMatch (inner step 2).
    # Shape: {status: "exact"|"possible"|"no_match", matched_records: list[dict],
    #         confidence_basis: str, status_reason: str}
    match_result: NotRequired[dict]  # type: ignore[valid-type]

    # Escalation packet produced by EscalationRender (inner step 3).
    # Shape: {summary: str, claims: list[dict], recommended_action: str,
    #         match_status: str}
    escalation_packet: NotRequired[dict]  # type: ignore[valid-type]
