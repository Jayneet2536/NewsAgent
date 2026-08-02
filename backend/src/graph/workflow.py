from typing import Callable, Literal

from langgraph.graph import END, StateGraph

from ..config import settings
from ..nodes.planner import planner_node
from ..nodes.researcher import researcher_node
from ..nodes.verifier import verifier_node
from ..nodes.writer import writer_node
from .state import AgentState


def should_continue(state: AgentState) -> Literal["rewrite", "end"]:
    verification_score = state.get("verification_score", 0)
    retry_count = state.get("retry_count", 0)

    if (
        verification_score < settings.verification_threshold
        and retry_count < settings.max_retries
    ):
        return "rewrite"

    return "end"


workflow = StateGraph(AgentState)

workflow.add_node("planner_node", planner_node)
workflow.add_node("researcher_node", researcher_node)
workflow.add_node("writer_node", writer_node)
workflow.add_node("verifier_node", verifier_node)

workflow.set_entry_point("planner_node")

workflow.add_edge("planner_node", "researcher_node")
workflow.add_edge("researcher_node", "writer_node")
workflow.add_edge("writer_node", "verifier_node")
workflow.add_conditional_edges(
    "verifier_node",
    should_continue,
    {
        "rewrite": "writer_node",
        "end": END,
    },
)

app = workflow.compile()


def build_workflow() -> Callable:
    return app
