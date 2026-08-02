import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..config import settings
from ..graph.state import AgentState

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "verifier.txt"
VERIFIER_MODEL = "openai/gpt-oss-120b"


def verifier_node(state: AgentState) -> Dict[str, Any]:
    """Verify a generated digest against source articles."""
    retry_count = state.get("retry_count", 0)
    draft = state.get("draft", "")
    sources = _format_sources(state.get("articles", []))
    prompt = _build_prompt(draft=draft, sources=sources)

    try:
        response_text = _generate_verification(prompt)
        score, issues = _parse_verification_response(response_text)
    except json.JSONDecodeError as error:
        logger.error("Verifier JSON parsing failed: %s", error)
        score, issues = 0.0, ["Verifier returned invalid JSON."]
    except Exception as error:
        logger.error("Verifier API call failed: %s", error)
        score, issues = 0.0, ["Verifier API call failed."]

    logger.info(
        "Verification score=%s threshold=%s retry_count=%s max_retries=%s",
        score,
        settings.verification_threshold,
        retry_count,
        settings.max_retries,
    )
    if issues:
        logger.warning("Verification issues: %s", issues)

    return {
        "verification_score": score,
        "verification_issues": issues,
        "retry_count": retry_count + 1,
    }


def _format_sources(articles: List[Dict[str, Any]]) -> str:
    """Format source articles with URLs and short summaries for verification."""
    if not articles:
        return "No source articles available."

    formatted_sources = []
    for article in articles:
        content = str(article.get("content", "")).strip()
        summary = content[:500] if content else str(article.get("snippet", "")).strip()
        formatted_sources.append(
            "\n".join(
                [
                    f"Topic: {article.get('topic', '')}",
                    f"Title: {article.get('title', '')}",
                    f"URL: {article.get('url', '')}",
                    f"Summary: {summary}...",
                ]
            )
        )

    return "\n\n---\n\n".join(formatted_sources)


def _build_prompt(draft: str, sources: str) -> str:
    """Load the verifier prompt template and inject draft and source data."""
    template = PROMPT_PATH.read_text(encoding="utf-8")
    logger.debug(
        "Building verifier prompt draft_length=%s sources_length=%s",
        len(draft),
        len(sources),
    )
    return template.replace("{draft}", draft).replace("{sources}", sources)


def _generate_verification(prompt: str) -> str:
    """Generate a JSON verification result using Groq JSON mode."""
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is required for verifier generation.")

    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict fact verifier. Return only valid JSON "
                    'with this schema: {"score": number, "issues": string[]}.'
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        model=VERIFIER_MODEL,
        response_format={"type": "json_object"},
        temperature=0,
    )

    response_text = response.choices[0].message.content or ""
    if not response_text.strip():
        raise ValueError("Verifier returned an empty response.")

    return response_text


def _parse_verification_response(response_text: str) -> Tuple[float, List[str]]:
    """Parse the verifier JSON response into a bounded score and issue list."""
    data = json.loads(response_text)
    score = float(data.get("score", 0))
    score = min(max(score, 0.0), 100.0)

    raw_issues = data.get("issues", [])
    issues = [str(issue) for issue in raw_issues] if isinstance(raw_issues, list) else []

    logger.debug("Parsed verifier response score=%s issues=%s", score, issues)
    return score, issues
