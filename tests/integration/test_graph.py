import json
from uuid import uuid4

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from src.graph.graph import Graph


class FakeLLM:
    def complete(self, _prompt: str) -> str:
        return json.dumps({"lot_numbers": ["ABC123"], "product_id": "SUP-1", "location_scope": "WARD-3"})


def _ctx() -> InvocationContext:
    return InvocationContext(
        session_id=str(uuid4()),
        caller_trust_level=TrustLevel.VERIFIED_EXTERNAL,
        caller_id="test-caller",
    )


class TestGraphIntegration:
    def test_exact_match_end_to_end(self):
        agent = Graph(config={"llm": FakeLLM(), "max_retry": 1})
        agent.compile()
        user_input = json.dumps(
            {
                "recall_text": "Recall notice: Lot ABC123 in WARD-3 is affected.",
                "inventory_rows": [{"lot_number": "ABC123", "location_id": "WARD-3"}],
            }
        )
        result = agent.invoke(user_input, ctx=_ctx())
        assert result["status"] == "success"
        assert result["output"]["match_status"] == "exact"
        assert len(result["output"]["claims"]) == 1

    def test_empty_input_returns_error(self):
        agent = Graph(config={"llm": FakeLLM(), "max_retry": 1})
        agent.compile()
        result = agent.invoke("", ctx=_ctx())
        assert result["status"] in ("error", "cancelled")

    def test_no_llm_standalone_path_reaches_success(self):
        """The standalone path has no LLM: the deterministic fallback must still
        produce a grounded, compliance-review packet (never exact). Same input
        as the stage-5 deploy payload."""
        user_input = json.dumps(
            {
                "recall_text": (
                    "Recall notice: Lot ABC123 sterile-supply units distributed to WARD-3 are affected."
                ),
                "inventory_rows": [{"lot_number": "ABC123", "location_id": "WARD-3"}],
            }
        )
        agent = Graph(config={"llm": None, "max_retry": 1})
        agent.compile()
        result = agent.invoke(user_input, ctx=_ctx())
        assert result["status"] == "success"
        assert result["output"]["match_status"] == "possible"
        assert result["output"]["claims"][0]["action_rule_id"] == "compliance_notify"

    def test_no_match_end_to_end(self):
        agent = Graph(config={"llm": FakeLLM(), "max_retry": 1})
        agent.compile()
        user_input = json.dumps(
            {
                "recall_text": "Recall notice: Lot ABC123 in WARD-3 is affected.",
                "inventory_rows": [{"lot_number": "ZZZ999", "location_id": "WARD-9"}],
            }
        )
        result = agent.invoke(user_input, ctx=_ctx())
        assert result["status"] == "success"
        assert result["output"]["match_status"] == "no_match"
