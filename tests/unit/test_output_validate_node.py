from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from src.nodes.output_validate_node import OutputValidateNode


def _grounded_claim(**overrides) -> dict:
    claim = {
        "claim_text": "Lot ABC123 matches recall criteria.",
        "parsed_criterion_id": "parsed_criteria_1",
        "match_result_id": "match_result_0",
        "match_status": "exact",
        "inventory_record_ids": ["ABC123:WARD-3"],
        "source_span": "WARD-3",
        "action_rule_id": "quarantine_review",
    }
    claim.update(overrides)
    return claim


def _base_state(escalation_packet: dict) -> dict:
    return {
        "escalation_packet": escalation_packet,
        "correlation_id": "test-corr-5",
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "execution_time": {},
        "status": None,
    }


class TestOutputValidateExecute:
    def test_success_grounded_exact_packet(self):
        node = OutputValidateNode()
        packet = {
            "summary": "resolved",
            "claims": [_grounded_claim()],
            "recommended_action": "Escalate to sterile-processing lead for physical quarantine review.",
            "match_status": "exact",
        }
        result = node.execute(_base_state(packet))
        assert result["status"] == AgentStatus.SUCCESS
        assert result["formatted_output"]["match_status"] == "exact"

    def test_success_no_match_empty_claims(self):
        node = OutputValidateNode()
        packet = {"summary": "no match", "claims": [], "recommended_action": "No action.", "match_status": "no_match"}
        result = node.execute(_base_state(packet))
        assert result["status"] == AgentStatus.SUCCESS

    def test_rejects_missing_packet(self):
        node = OutputValidateNode()
        result = node.execute(_base_state({}))
        assert result["status"] == AgentStatus.ERROR

    def test_rejects_unresolved_without_claims(self):
        node = OutputValidateNode()
        packet = {"summary": "x", "claims": [], "recommended_action": "x", "match_status": "possible"}
        result = node.execute(_base_state(packet))
        assert result["status"] == AgentStatus.ERROR

    def test_rejects_ungrounded_claim(self):
        node = OutputValidateNode()
        packet = {
            "summary": "x",
            "claims": [_grounded_claim(inventory_record_ids=[])],
            "recommended_action": "x",
            "match_status": "exact",
        }
        result = node.execute(_base_state(packet))
        assert result["status"] == AgentStatus.ERROR

    def test_rejects_unapproved_action_rule_id(self):
        node = OutputValidateNode()
        packet = {
            "summary": "x",
            "claims": [_grounded_claim(action_rule_id="invented_action")],
            "recommended_action": "x",
            "match_status": "exact",
        }
        result = node.execute(_base_state(packet))
        assert result["status"] == AgentStatus.ERROR


class TestOutputValidateSecurityGateOutputHook:
    def test_extra_security_gate_output_passes_clean_output(self):
        node = OutputValidateNode()
        state = _base_state({"claims": [], "match_status": "no_match"})
        state["formatted_output"] = {"summary": "clean", "claims": []}
        out = node._extra_security_gate_output(state)
        assert out is state

    def test_extra_security_gate_output_rejects_credential_in_formatted_output(self):
        node = OutputValidateNode()
        state = _base_state({})
        state["formatted_output"] = {"summary": "Authorization: Bearer sk-abcdefghijklmnop"}
        out = node._extra_security_gate_output(state)
        assert out["status"] == AgentStatus.ERROR


class TestOutputValidateTrustGate:
    def test_s1_denies_anonymous_caller(self):
        node = OutputValidateNode()
        packet = {
            "summary": "x",
            "claims": [_grounded_claim()],
            "recommended_action": "x",
            "match_status": "exact",
        }
        state = _base_state(packet)
        state["caller_trust_level"] = TrustLevel.ANONYMOUS.value
        result = node(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert any("S-1 trust gate denied" in e for e in result.get("error_log", []))
