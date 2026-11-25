import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from ..config import settings
from ..graph.state import AgentState
from ..models import SearchPlan
from ..errors import PipelineError
from ..llm import generate_text

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "planner.txt"

_SMART_QUOTES = str.maketrans({
    "\u201c": '"', "\u201d": '"',  # “ ”
    "\u2018": "'", "\u2019": "'",  # ‘ ’
})
_ZERO_WIDTH_CHARS = re.compile(r"[\u200b\u200c\u200d\ufeff]")


def planner_node(state: AgentState) -> Dict[str, Any]:
    """Generate a search plan for the user's interests."""
    interests = _normalize_interests(state.get("interests", []))
    prompt = _build_prompt(interests)

    try:
        response_text = _generate_search_plan(prompt)
        response_text = _sanitize_plan_text(response_text)
        plan = SearchPlan.model_validate_json(response_text)
    except PipelineError:
        raise
    except Exception as error:
        logger.error("Planner API call failed, using fallback plan: %s", error)
        plan = _fallback_plan(interests)

    plan.web_queries = plan.web_queries[:settings.research_max_queries]
    plan.youtube_queries = plan.youtube_queries[:settings.research_max_queries]
    return {"interests": interests, "plan": plan.model_dump_json(), **plan.model_dump()}


def _build_prompt(interests: List[str]) -> str:
    """Load the planner prompt template and inject interests + today's date."""
    template = PROMPT_PATH.read_text(encoding="utf-8")
    interests_text = ", ".join(interests)
    today_text = date.today().strftime("%B %d, %Y")
    logger.debug("Building planner prompt for interests=%s today=%s", interests_text, today_text)

    prompt = template.replace("{interests}", interests_text)
    prompt = prompt.replace("{today}", today_text)
    prompt += f"\nGenerate at most {settings.research_max_queries} queries per list."
    return prompt


def _sanitize_plan_text(text: str) -> str:
    """Normalize LLM output so downstream regex parsing behaves reliably."""
    cleaned = text.translate(_SMART_QUOTES)
    cleaned = _ZERO_WIDTH_CHARS.sub("", cleaned)
    return cleaned


def _normalize_interests(interests: List[str]) -> List[str]:
    """Convert raw natural-language input into clean planner interests."""
    normalized_interests = []

    for interest in interests:
        normalized_interests.extend(_split_interest_text(interest))

    return _deduplicate(normalized_interests)


def _split_interest_text(text: str) -> List[str]:
    """Split one user-entered sentence into individual research topics."""
    cleaned_text = text.lower().replace("aboiut", "about")
    cleaned_text = re.sub(r"\bi\s+(want|need|would like)\b", "", cleaned_text)
    cleaned_text = re.sub(r"\b(show|get|give|find)\s+me\b", "", cleaned_text)
    cleaned_text = re.sub(r"\b(new|latest)\s+(updates?|news)\s+(about|on)\b", ",", cleaned_text)
    cleaned_text = re.sub(r"\b(news|updates?)\s+(about|on)\b", ",", cleaned_text)
    cleaned_text = re.sub(r"\b(and also|also)\b", ",", cleaned_text)

    parts = re.split(r"[,;]|\s+and\s+", cleaned_text)
    topics = [_clean_interest(part) for part in parts]
    return [topic for topic in topics if topic]


def _clean_interest(text: str) -> str:
    """Remove filler words while preserving the topic phrase."""
    cleaned_text = text.strip(" .")
    cleaned_text = re.sub(
        r"^(the\s+)?(latest\s+)?(news|updates?|articles?)\s+(about|on|for)\s+",
        "",
        cleaned_text,
    )
    cleaned_text = re.sub(r"^(about|on|regarding)\s+", "", cleaned_text)
    cleaned_text = re.sub(r"^the\s+", "", cleaned_text)
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()

    return cleaned_text


def _generate_search_plan(prompt: str) -> str:
    return generate_text(prompt, model=settings.planner_model, stage="Planner", json_mode=True)


def _fallback_plan(interests: List[str]) -> SearchPlan:
    """Create a simple search plan directly from user interests."""
    topics = interests or ["general"]
    return SearchPlan(
        web_queries=[f"{interest} news" for interest in topics],
        youtube_queries=[f"{interest} news briefing announcement interview" for interest in topics],
    )


def _deduplicate(items: List[str]) -> List[str]:
    """Remove duplicate strings while preserving order."""
    seen = set()
    deduplicated = []

    for item in items:
        normalized = item.lower()
        if normalized in seen:
            continue

        seen.add(normalized)
        deduplicated.append(item)

    return deduplicated
