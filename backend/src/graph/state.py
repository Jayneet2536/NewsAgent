from typing import List, Optional, TypedDict


class GraphState(TypedDict, total=False):
    topic: str
    plan: List[str]
    research: List[str]
    article: Optional[str]
    verification: Optional[str]
