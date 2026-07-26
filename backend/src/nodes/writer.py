from typing import Dict, Any


def writer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    topic = state.get("topic", "")
    return {
        "article": f"Draft article about {topic}.",
    }
