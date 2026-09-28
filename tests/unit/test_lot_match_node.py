from framework.schemas.agent_status import AgentStatus
from src.nodes.lot_match_node import LotMatchNode


def _state(parsed_criteria: dict, inventory_rows: list) -> dict:
    return {
        "parsed_criteria": parsed_criteria,
        "inventory_rows": inventory_rows,
        "correlation_id": "test-corr-3",
    }


class TestLotMatchNode:
    def test_exact_match(self):
        node = LotMatchNode()
        parsed = {"lot_numbers": ["ABC123"], "location_scope": "WARD-3", "parse_confidence": 0.9}
        rows = [{"lot_number": "ABC123", "location_id": "WARD-3"}]
        result = node.execute(_state(parsed, rows))
        assert result["status"] == AgentStatus.SUCCESS
        assert result["match_result"]["status"] == "exact"

    def test_no_match(self):
        node = LotMatchNode()
        parsed = {"lot_numbers": ["ZZZ999"], "location_scope": "WARD-3", "parse_confidence": 0.9}
        rows = [{"lot_number": "ABC123", "location_id": "WARD-3"}]
        result = node.execute(_state(parsed, rows))
        assert result["match_result"]["status"] == "no_match"

    def test_low_confidence_forces_possible(self):
        node = LotMatchNode()
        parsed = {"lot_numbers": ["ABC123"], "location_scope": "WARD-3", "parse_confidence": 0.4}
        rows = [{"lot_number": "ABC123", "location_id": "WARD-3"}]
        result = node.execute(_state(parsed, rows))
        assert result["match_result"]["status"] == "possible"
        assert result["match_result"]["confidence_basis"] == "sub_threshold_parse_confidence"

    def test_error_missing_parsed_criteria(self):
        node = LotMatchNode()
        result = node.execute({"correlation_id": "x"})
        assert result["status"] == AgentStatus.ERROR

    def test_error_path_emits_trace_event(self, monkeypatch):
        # R3a: the reject branch must trace too, not only the success path.
        events = []
        monkeypatch.setattr(
            "src.nodes.lot_match_node.emit_trace_event",
            lambda name, payload, state: events.append(name),
        )
        node = LotMatchNode()
        node.execute({"correlation_id": "x"})
        assert "lot_match_rejected" in events
