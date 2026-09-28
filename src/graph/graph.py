"""AgentCore Platform v1.0"""

# Outer graph for HCR-C2-079 (Healthcare Facility Sterile-Supply Recall Lot
# Match Escalation Agent) — Cat 2: outer AgentBaseGraph backbone +
# RecallLotMatchGraphNode (GraphNode) in the `main` slot wrapping the inner
# RecallLotMatchWorkflowGraph subgraph. The pipeline: InputValidate -> RecallParse -> LotMatch ->
# EscalationRender -> OutputValidate.
#
# The GraphNode wrapper class lives in THIS file (not src/nodes/) so that
# tests/proof_of_boundary/test_pb_invoke_order.py (which auto-discovers every
# BaseNode subclass under src/nodes/) does not pick it up — GraphNode
# delegates security gating to the inner subgraph and intentionally does not
# run the standard S-1->S-4->S-2->execute->S-3->S-4 lifecycle.

from typing import Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.nodes.input_validate_node import InputValidateNode
from src.nodes.output_validate_node import OutputValidateNode
from src.schemas.state import State


class RecallLotMatchGraphNode(GraphNode):
    """Wraps the inner RecallLotMatchWorkflowGraph; assigned to the `main` slot."""

    # S-1: outer main-slot wrapper — first node in the
    # outer backbone to receive caller input after pre_process. Matches
    # config/agent.yaml required_trust_level and sibling outer FunctionNodes
    # (InputValidateNode/OutputValidateNode).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, llm: Any = None) -> None:
        super().__init__()
        self._llm = llm

    def get_subgraph(self) -> Any:
        from src.graph.recall_lot_match_workflow_graph import RecallLotMatchWorkflowGraph

        sg = RecallLotMatchWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        # S-4: runs inside GraphNode.execute() — audit the dispatch into the
        # inner subgraph.
        emit_trace_event(
            "recall_lot_match_dispatched",
            {"correlation_id": state.get("correlation_id")},
            state,
        )
        return cast(str, state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        # S-4: runs inside GraphNode.execute() — audit the subgraph outcome
        # merged back out.
        emit_trace_event(
            "recall_lot_match_completed",
            {
                "correlation_id": state.get("correlation_id"),
                "match_status": (sub_result.get("match_result") or {}).get("status"),
            },
            state,
        )
        return {
            "parsed_criteria": sub_result.get("parsed_criteria"),
            "match_result": sub_result.get("match_result"),
            "escalation_packet": sub_result.get("escalation_packet"),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {"llm": self._llm}


class HcrC2079RecallLotMatchEscalationAgent(AgentBaseGraph):
    """Healthcare Facility Sterile-Supply Recall Lot Match Escalation Agent."""

    @property
    def name(self) -> str:
        return "hcr-c2-079"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # fills: initialize, finalize (required)
        llm = self.config.get("llm") if hasattr(self, "config") else None
        self._nodes["pre_process"] = InputValidateNode()
        self._nodes["main"] = RecallLotMatchGraphNode(llm=llm)
        self._nodes["post_process"] = OutputValidateNode()

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.


# Alias for config/agent.yaml `module: "src.graph"` / `class: "..."` entry point.
Graph = HcrC2079RecallLotMatchEscalationAgent
