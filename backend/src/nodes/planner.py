import logging
from pathlib import Path
from typing import Any, Dict, List

from ..config import settings
from ..graph.state import AgentState

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "planner.txt"


def planner_node(state: AgentState) -> Dict[str, Any]:
    """Generate a search plan for the user's interests."""
    interests = state.get("interests", [])
    prompt = _build_prompt(interests)

    try:
        response_text = _generate_search_plan(prompt)
        logger.debug("Planner generated search plan: %s", response_text)
        return {"plan": response_text}
    except Exception as error:
        logger.error("Planner API call failed, using fallback plan: %s", error)
        return {"plan": _fallback_plan(interests)}


def _build_prompt(interests: List[str]) -> str:
    """Load the planner prompt template and inject comma-separated interests."""
    template = PROMPT_PATH.read_text(encoding="utf-8")
    interests_text = ", ".join(interests)
    logger.debug("Building planner prompt for interests: %s", interests_text)
    return template.replace("{interests}", interests_text)


def _generate_search_plan(prompt: str) -> str:
    """Call Groq through the official groq SDK."""
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is required for planner generation.")

    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = (response.choices[0].message.content or "").strip()

    if not response_text:
        raise ValueError("Planner returned an empty response.")

    return response_text


def _fallback_plan(interests: List[str]) -> str:
    """Create a simple search plan directly from user interests."""
    if not interests:
        return "- Search for latest general news from the last 7 days"

    return "\n".join(
        f'- Search for "latest {interest} news last 7 days"' for interest in interests
    )
