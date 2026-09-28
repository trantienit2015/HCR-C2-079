from framework.schemas.agent_status import AgentStatus
from src.nodes.escalation_render_node import EscalationRenderNode


def _state(match_result: dict, parsed_criteria: dict | None = None) -> dict:
    return {
        "match_result": match_result,
        "parsed_criteria": parsed_criteria or {},
        "correlation_id": "test-corr-4",
    }


class TestEscalationRenderNode:
    def test_exact_match_produces_grounded_claim(self):
        node = EscalationRenderNode()
        match_result = {
            "status": "exact",
            "matched_records": [{"lot_number": "ABC123", "location_id": "WARD-3"}],
            "confidence_basis": "exact_key_match",
            "status_reason": "ok",
        }
        result = node.execute(_state(match_result, {"location_scope": "WARD-3"}))
        assert result["status"] == AgentStatus.SUCCESS
        packet = result["escalation_packet"]
        assert packet["match_status"] == "exact"
        assert len(packet["claims"]) == 1
        claim = packet["claims"][0]
        assert claim["action_rule_id"] == "quarantine_review"
        assert claim["inventory_record_ids"] == ["ABC123:WARD-3"]

    def test_no_match_produces_no_claims(self):
        node = EscalationRenderNode()
        match_result = {
            "status": "no_match",
            "matched_records": [],
            "confidence_basis": "zero_candidates",
            "status_reason": "no rows",
        }
        result = node.execute(_state(match_result))
        packet = result["escalation_packet"]
        assert packet["match_status"] == "no_match"
        assert packet["claims"] == []
        assert packet["recommended_action"]

    def test_error_missing_match_result(self):
        node = EscalationRenderNode()
        result = node.execute({"correlation_id": "x"})
        assert result["status"] == AgentStatus.ERROR

    def test_error_path_emits_trace_event(self, monkeypatch):
        # R3a: the reject branch must trace too, not only the success path.
        events = []
        monkeypatch.setattr(
            "src.nodes.escalation_render_node.emit_trace_event",
            lambda name, payload, state: events.append(name),
        )
        node = EscalationRenderNode()
        node.execute({"correlation_id": "x"})
        assert "escalation_render_rejected" in events
