import json

from framework.schemas.agent_status import AgentStatus
from src.nodes.recall_parse_node import RecallParseNode


class FakeLLM:
    """Bare-string fake — backward-compatible shape, NOT the canonical dict."""

    def __init__(self, response: dict):
        self._response = response

    def complete(self, _messages: list) -> str:
        return json.dumps(self._response)


class DictLLM:
    """Canonical AgentCore BaseLLM.complete() shape: {"content": str, ...}."""

    def __init__(self, response: dict):
        self._response = response

    def complete(self, _messages: list) -> dict:
        return {"content": json.dumps(self._response), "tool_calls": [], "model": "fake", "usage": {}}


class RaisingLLM:
    def complete(self, _messages: list) -> dict:
        raise ConnectionError("provider unavailable")


class EmptyLLM:
    def complete(self, _messages: list) -> dict:
        return {"content": "", "tool_calls": [], "model": "fake", "usage": {}}


def _inner_state(user_input: str) -> dict:
    return {"user_input": user_input, "correlation_id": "test-corr-2"}


class TestRecallParseNode:
    def test_success_high_confidence(self):
        llm = FakeLLM({"lot_numbers": ["ABC123"], "product_id": "SUP-1", "location_scope": "WARD-3"})
        node = RecallParseNode(llm=llm)
        payload = json.dumps({"recall_text": "Lot ABC123 recalled", "inventory_rows": [{"lot_number": "ABC123"}]})
        result = node.execute(_inner_state(payload))
        assert result["status"] == AgentStatus.SUCCESS
        assert result["parsed_criteria"]["lot_numbers"] == ["ABC123"]
        assert result["parsed_criteria"]["parse_confidence"] >= 0.7

    def test_success_canonical_dict_llm_response(self):
        # R3m: BaseLLM.complete() returns the canonical dict shape — the node
        # must extract .content and parse it, not discard it as non-string.
        llm = DictLLM({"lot_numbers": ["ABC123"], "product_id": "SUP-1", "location_scope": "WARD-3"})
        node = RecallParseNode(llm=llm)
        payload = json.dumps({"recall_text": "Lot ABC123 recalled", "inventory_rows": [{"lot_number": "ABC123"}]})
        result = node.execute(_inner_state(payload))
        assert result["status"] == AgentStatus.SUCCESS
        assert result["parsed_criteria"]["lot_numbers"] == ["ABC123"]

    def test_error_empty_recall_text(self):
        node = RecallParseNode(llm=None)
        payload = json.dumps({"recall_text": "", "inventory_rows": []})
        result = node.execute(_inner_state(payload))
        assert result["status"] == AgentStatus.ERROR

    def test_no_llm_low_confidence(self):
        node = RecallParseNode(llm=None)
        payload = json.dumps({"recall_text": "some recall text", "inventory_rows": []})
        result = node.execute(_inner_state(payload))
        assert result["status"] == AgentStatus.SUCCESS
        assert result["parsed_criteria"]["parse_confidence"] < 0.7

    def test_no_llm_fallback_extracts_keyword_lot_numbers(self):
        node = RecallParseNode(llm=None)
        payload = json.dumps(
            {
                "recall_text": "Recall notice: Lot ABC123 and lot no. XYZ-7788 distributed to WARD-3.",
                "inventory_rows": [],
            }
        )
        result = node.execute(_inner_state(payload))
        assert result["status"] == AgentStatus.SUCCESS.value
        criteria = result["parsed_criteria"]
        assert criteria["lot_numbers"] == ["ABC123", "XYZ-7788"]
        assert criteria["parse_method"] == "deterministic_fallback"
        # location/product are never guessed on the fallback path, so the
        # confidence stays below the exact-match threshold.
        assert criteria["location_scope"] == ""
        assert criteria["parse_confidence"] < 0.7

    def test_no_llm_fallback_ignores_non_lot_tokens(self):
        node = RecallParseNode(llm=None)
        payload = json.dumps({"recall_text": "A lot of units need review.", "inventory_rows": []})
        result = node.execute(_inner_state(payload))
        assert result["parsed_criteria"]["lot_numbers"] == []

    def test_configured_llm_path_is_tagged_llm(self):
        llm = DictLLM({"lot_numbers": ["ABC123"], "product_id": "SUP-1", "location_scope": "WARD-3"})
        result = RecallParseNode(llm=llm).execute(_inner_state(json.dumps({"recall_text": "x"})))
        assert result["parsed_criteria"]["parse_method"] == "llm"

    def test_malformed_lot_number_lowers_confidence(self):
        llm = FakeLLM({"lot_numbers": ["!!bad!!"], "product_id": "SUP-1", "location_scope": "WARD-3"})
        node = RecallParseNode(llm=llm)
        payload = json.dumps({"recall_text": "bad lot recalled", "inventory_rows": []})
        result = node.execute(_inner_state(payload))
        assert result["status"] == AgentStatus.SUCCESS
        assert result["parsed_criteria"]["parse_confidence"] < 0.7

    def test_configured_llm_raises_is_error_not_fallback(self):
        # LLM WAS configured — a provider failure must
        # surface as ERROR, never a silent deterministic-looking SUCCESS.
        node = RecallParseNode(llm=RaisingLLM())
        payload = json.dumps({"recall_text": "Lot ABC123 recalled", "inventory_rows": []})
        result = node.execute(_inner_state(payload))
        assert result["status"] == AgentStatus.ERROR
        assert any("LLM call failed" in e for e in result["error_log"])

    def test_configured_llm_empty_response_is_error_not_fallback(self):
        # Empty/invalid response from a CONFIGURED LLM must
        # not be swallowed into a fabricated low-confidence SUCCESS.
        node = RecallParseNode(llm=EmptyLLM())
        payload = json.dumps({"recall_text": "Lot ABC123 recalled", "inventory_rows": []})
        result = node.execute(_inner_state(payload))
        assert result["status"] == AgentStatus.ERROR
        assert any("empty/invalid response" in e for e in result["error_log"])

    def test_reject_path_emits_trace_event(self, monkeypatch):
        # R3a: the reject branch must trace too, not only the success path.
        events = []
        monkeypatch.setattr(
            "src.nodes.recall_parse_node.emit_trace_event",
            lambda name, payload, state: events.append(name),
        )
        node = RecallParseNode(llm=None)
        payload = json.dumps({"recall_text": "", "inventory_rows": []})
        node.execute(_inner_state(payload))
        assert "recall_parse_rejected" in events

    def test_llm_failed_path_emits_trace_event(self, monkeypatch):
        events = []
        monkeypatch.setattr(
            "src.nodes.recall_parse_node.emit_trace_event",
            lambda name, payload, state: events.append(name),
        )
        node = RecallParseNode(llm=RaisingLLM())
        payload = json.dumps({"recall_text": "Lot ABC123 recalled", "inventory_rows": []})
        node.execute(_inner_state(payload))
        assert "recall_parse_llm_failed" in events
