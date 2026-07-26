from typing import Callable

from langgraph.graph import END, StateGraph

from .state import GraphState
from ..nodes.planner import planner_node
from ..nodes.researcher import researcher_node
from ..nodes.writer import writer_node
from ..nodes.verifier import verifier_node


def build_workflow() -> Callable:
    workflow = StateGraph(GraphState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("verifier", verifier_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "researcher")
    workflow.add_edge("researcher", "writer")
    workflow.add_edge("writer", "verifier")
    workflow.add_edge("verifier", END)

    return workflow.compile()
