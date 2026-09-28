"""AgentCore Platform v1.0"""

# Inner graph (Cat 2 subgraph) for HCR-C2-079 — the multi-step domain workflow
# wrapped by RecallLotMatchGraphNode (main slot of the outer graph.py).
# Topology: START -> recall_parse -> lot_match -> escalation_render -> END.

from typing import Any
from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from src.nodes.escalation_render_node import EscalationRenderNode
from src.nodes.lot_match_node import LotMatchNode
from src.nodes.recall_parse_node import RecallParseNode
from src.schemas.state import State


class RecallLotMatchWorkflowGraph(BaseGraph):
    """Inner graph: recall_parse -> lot_match -> escalation_render."""

    @property
    def name(self) -> str:
        return "hcr_c2_079_recall_lot_match_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        llm = self.config.get("llm") if hasattr(self, "config") else None
        self._nodes["recall_parse"] = RecallParseNode(llm=llm)
        self._nodes["lot_match"] = LotMatchNode()
        self._nodes["escalation_render"] = EscalationRenderNode(llm=llm)

    def add_edges(self) -> None:
        self._sg.add_edge(START, "recall_parse")
        self._sg.add_edge("recall_parse", "lot_match")
        self._sg.add_edge("lot_match", "escalation_render")
        self._sg.add_edge("escalation_render", END)

    def route(self, state: AgentState) -> str:
        # Required by BaseGraph ABC; linear topology never invokes conditional
        # routing, but the method must exist.
        return END if state.get("status") == AgentStatus.ERROR.value else "escalation_render"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "parsed_criteria": state.get("parsed_criteria"),
            "match_result": state.get("match_result"),
            "escalation_packet": state.get("escalation_packet"),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
