from typing import Dict, Any


def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    topic = state.get("topic", "")
    return {
        "plan": [f"Research the latest developments around {topic}"],
    }
