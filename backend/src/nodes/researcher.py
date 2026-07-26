from typing import Dict, Any


def researcher_node(state: Dict[str, Any]) -> Dict[str, Any]:
    topic = state.get("topic", "")
    return {
        "research": [f"Collected background notes for: {topic}"],
    }
