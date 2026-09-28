import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from src.nodes.input_validate_node import InputValidateNode


def _base_state(user_input: str) -> dict:
    return {
        "user_input": user_input,
        "correlation_id": "test-corr-1",
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "execution_time": {},
        "status": None,
    }


class TestInputValidateNodeExecute:
    def test_success_valid_envelope(self):
        node = InputValidateNode()
        payload = json.dumps({"recall_text": "Lot ABC123 affected", "inventory_rows": [{"lot_number": "ABC123"}]})
        result = node.execute(_base_state(payload))
        assert result["status"] == AgentStatus.SUCCESS
        assert result["recall_text"] == "Lot ABC123 affected"
        assert json.loads(result["validated_input"])["recall_text"] == "Lot ABC123 affected"

    def test_error_empty_recall_text(self):
        node = InputValidateNode()
        payload = json.dumps({"recall_text": "", "inventory_rows": []})
        result = node.execute(_base_state(payload))
        assert result["status"] == AgentStatus.ERROR
        assert result["error_log"]

    def test_error_invalid_json(self):
        node = InputValidateNode()
        result = node.execute(_base_state("not-json{"))
        assert result["status"] == AgentStatus.ERROR


class TestInputValidateSecurityGateInputHook:
    def test_extra_security_gate_input_passes_clean_text(self):
        node = InputValidateNode()
        state = _base_state(json.dumps({"recall_text": "clean recall notice", "inventory_rows": []}))
        out = node._extra_security_gate_input(state)
        assert out is state

    def test_extra_security_gate_input_rejects_credential_pattern(self):
        node = InputValidateNode()
        state = _base_state("Authorization: Bearer sk-abcdefghijklmnop")
        out = node._extra_security_gate_input(state)
        assert out["status"] == AgentStatus.ERROR

    def test_extra_security_gate_input_rejects_patient_identifier(self):
        node = InputValidateNode()
        state = _base_state("patient_id: 12345 recall notice")
        out = node._extra_security_gate_input(state)
        assert out["status"] == AgentStatus.ERROR


class TestInputValidateTrustGate:
    def test_s1_denies_anonymous_caller(self):
        node = InputValidateNode()
        state = _base_state(json.dumps({"recall_text": "Lot ABC123", "inventory_rows": []}))
        state["caller_trust_level"] = TrustLevel.ANONYMOUS.value
        result = node(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert any("S-1 trust gate denied" in e for e in result.get("error_log", []))

    def test_s1_allows_verified_external_caller(self):
        node = InputValidateNode()
        state = _base_state(json.dumps({"recall_text": "Lot ABC123", "inventory_rows": []}))
        result = node(state)
        assert result["status"] == AgentStatus.SUCCESS.value
