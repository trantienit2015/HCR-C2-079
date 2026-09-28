"""TC-01..08 — AgentCore framework compliance tests for HCR-C2-079.

Adapted for the Cat 2 architecture: outer pre_process/post_process
(InputValidateNode/OutputValidateNode) + GraphNode main slot
(RecallLotMatchGraphNode) wrapping an inner subgraph
(RecallLotMatchWorkflowGraph: RecallParseNode -> LotMatchNode ->
EscalationRenderNode).
"""

import ast
import json
import os

import pytest

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from src.nodes.escalation_render_node import EscalationRenderNode
from src.nodes.input_validate_node import InputValidateNode
from src.nodes.lot_match_node import LotMatchNode
from src.nodes.output_validate_node import OutputValidateNode
from src.nodes.recall_parse_node import RecallParseNode
from src.schemas.state import State


# TC-01 — State contract: flat TypedDict extending AgentState, JSON-safe fields.
class TestTC01StateContract:
    def test_state_extends_agent_state(self):
        from framework.schemas.agent_state import AgentState

        # TypedDict does not support issubclass()/isinstance() checks (raises
        # TypeError), __bases__ collapses to (dict,) at runtime, and
        # __orig_bases__ presence is a CPython-typing-version detail (empty on
        # some environments) — verify inheritance structurally instead: every
        # AgentState field must be present in State's merged annotations.
        assert set(AgentState.__annotations__).issubset(set(State.__annotations__))

    def test_state_fields_are_json_safe_annotations(self):
        state_file = os.path.join(os.path.dirname(__file__), "..", "..", "src", "schemas", "state.py")
        with open(state_file, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        forbidden = {"BaseModel", "InvocationContext"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "State":
                for item in node.body:
                    if isinstance(item, ast.AnnAssign):
                        annotation_str = ast.dump(item.annotation)
                        assert not any(f in annotation_str for f in forbidden)


# TC-02 — Fail-closed validation: empty/invalid input -> ERROR, never raise.
class TestTC02FailClosedValidation:
    def test_input_validate_empty_returns_error_not_raise(self):
        node = InputValidateNode()
        result = node.execute({"user_input": "", "correlation_id": "tc02"})
        assert result["status"] == AgentStatus.ERROR

    def test_recall_parse_invalid_json_returns_error_not_raise(self):
        node = RecallParseNode(llm=None)
        result = node.execute({"user_input": "not-json{", "correlation_id": "tc02"})
        assert result["status"] == AgentStatus.ERROR

    def test_lot_match_missing_criteria_returns_error_not_raise(self):
        node = LotMatchNode()
        result = node.execute({"correlation_id": "tc02"})
        assert result["status"] == AgentStatus.ERROR

    def test_output_validate_missing_packet_returns_error_not_raise(self):
        node = OutputValidateNode()
        result = node.execute({"correlation_id": "tc02"})
        assert result["status"] == AgentStatus.ERROR


# TC-03 — No credentials / os.environ usage in src/ (business logic only —
# src/api/server.py is the documented entry-point auth exception).
class TestTC03NoCredentials:
    def test_no_os_environ_in_business_logic(self):
        src_dir = os.path.join(os.path.dirname(__file__), "..", "..", "src")
        for root, _dirs, files in os.walk(src_dir):
            if os.path.normpath(root).endswith(os.path.normpath("src/api")) or os.sep + "api" + os.sep in root + os.sep:
                continue
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(root, fname)
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                assert "os.environ" not in content, f"os.environ usage found in {path}"

    def test_no_credential_literals_in_src(self):
        import re

        src_dir = os.path.join(os.path.dirname(__file__), "..", "..", "src")
        patterns = [re.compile(r"sk-[a-zA-Z0-9]{20,}"), re.compile(r"AKIA[A-Z0-9]{16}")]
        for root, _dirs, files in os.walk(src_dir):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(root, fname)
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                for pattern in patterns:
                    assert not pattern.search(content), f"credential pattern found in {path}"


# TC-04 — InvocationContext accessed via config["configurable"] only, never stored in State.
class TestTC04InvocationContextIsolation:
    def test_state_class_has_no_invocation_context_field(self):
        assert "InvocationContext" not in State.__annotations__.values().__str__()


# TC-05 — Domain audit events; no backbone node_start/complete/error re-emit inside execute().
class TestTC05DomainAudit:
    @pytest.mark.parametrize(
        "module_name",
        [
            "src.nodes.input_validate_node",
            "src.nodes.recall_parse_node",
            "src.nodes.lot_match_node",
            "src.nodes.escalation_render_node",
            "src.nodes.output_validate_node",
        ],
    )
    def test_node_calls_emit_trace_event(self, module_name):
        import importlib

        module = importlib.import_module(module_name)
        source = open(module.__file__, encoding="utf-8").read()
        assert "emit_trace_event(" in source

    @pytest.mark.parametrize(
        "module_name",
        [
            "src.nodes.input_validate_node",
            "src.nodes.recall_parse_node",
            "src.nodes.lot_match_node",
            "src.nodes.escalation_render_node",
            "src.nodes.output_validate_node",
        ],
    )
    def test_node_does_not_reemit_backbone_events(self, module_name):
        import importlib

        module = importlib.import_module(module_name)
        source = open(module.__file__, encoding="utf-8").read()
        for backbone_event in ('"node_start"', '"node_complete"', '"node_error"'):
            assert backbone_event not in source


# TC-06/07 — S-2/S-3 gates are @final on FunctionNode; _extra_* hooks overridable.
class TestTC06TC07SecurityGatesFinal:
    def test_extra_security_gate_input_hook_present_on_input_validate(self):
        assert hasattr(InputValidateNode, "_extra_security_gate_input")

    def test_extra_security_gate_output_hook_present_on_output_validate(self):
        assert hasattr(OutputValidateNode, "_extra_security_gate_output")

    def test_output_validate_blocks_credential_pattern_in_own_output(self):
        node = OutputValidateNode()
        state = {"formatted_output": {"summary": "Authorization: Bearer sk-abcdefghijklmnop"}}
        result = node._extra_security_gate_output(state)
        assert result["status"] == AgentStatus.ERROR


# TC-08 — required_trust_level declared (valid enum) + enforced via __call__.
class TestTC08TrustGate:
    @pytest.mark.parametrize(
        "node_cls",
        [InputValidateNode, RecallParseNode, LotMatchNode, EscalationRenderNode, OutputValidateNode],
    )
    def test_required_trust_level_is_valid_enum(self, node_cls):
        assert node_cls.required_trust_level in (
            TrustLevel.ANONYMOUS,
            TrustLevel.VERIFIED_EXTERNAL,
            TrustLevel.INTERNAL,
        )

    def test_outer_boundary_node_matches_agent_yaml_trust_level(self):
        # config/agent.yaml declares required_trust_level: VERIFIED_EXTERNAL for
        # this agent; outer pre_process/post_process nodes must match.
        assert InputValidateNode.required_trust_level == TrustLevel.VERIFIED_EXTERNAL
        assert OutputValidateNode.required_trust_level == TrustLevel.VERIFIED_EXTERNAL

    def test_inner_nodes_use_anonymous(self):
        # Inner subgraph nodes: trust is authenticated once at the outer
        # backbone — requiring anything above ANONYMOUS here would be a
        # privilege-escalation the external caller cannot satisfy.
        for node_cls in (RecallParseNode, LotMatchNode, EscalationRenderNode):
            assert node_cls.required_trust_level == TrustLevel.ANONYMOUS

    def test_s1_denies_anonymous_caller_on_outer_node(self):
        node = InputValidateNode()
        state = {
            "user_input": json.dumps({"recall_text": "Lot ABC123", "inventory_rows": []}),
            "caller_trust_level": TrustLevel.ANONYMOUS.value,
            "correlation_id": "tc08",
            "execution_time": {},
            "status": None,
        }
        result = node(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert any("S-1 trust gate denied" in e for e in result.get("error_log", []))

    def test_s1_allows_sufficient_trust_on_outer_node(self):
        node = InputValidateNode()
        state = {
            "user_input": json.dumps({"recall_text": "Lot ABC123", "inventory_rows": []}),
            "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
            "correlation_id": "tc08",
            "execution_time": {},
            "status": None,
        }
        result = node(state)
        assert result["status"] == AgentStatus.SUCCESS.value
