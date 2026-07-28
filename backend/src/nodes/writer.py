import logging
from pathlib import Path
from typing import Any, Dict, List

from ..config import settings
from ..graph.state import AgentState

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "writer.txt"
WRITER_MODEL = "llama-3.3-70b-versatile"


def writer_node(state: AgentState) -> Dict[str, Any]:
    """Generate a markdown news digest from researched articles."""
    articles = state.get("articles", [])
    articles_context = _format_articles(articles)
    prompt = _build_prompt(articles_context)

    try:
        response_text = _generate_digest(prompt)
        logger.debug("Writer generated draft length=%s", len(response_text))
        return {"draft": response_text}
    except Exception as error:
        logger.error("Writer API call failed: %s", error)
        return {
            "draft": (
                "Unable to generate the news digest right now. "
                "Please try again after checking the Groq configuration."
            )
        }


def _format_articles(articles: List[Dict[str, Any]]) -> str:
    """Format article dictionaries into prompt-ready context text."""
    if not articles:
        return "No articles available."

    formatted_articles = []
    for article in articles:
        content = str(article.get("content", ""))
        formatted_articles.append(
            "\n".join(
                [
                    f"Topic: {article.get('topic', '')}",
                    f"Title: {article.get('title', '')}",
                    f"URL: {article.get('url', '')}",
                    f"Content: {content[:500]}...",
                ]
            )
        )

    return "\n\n---\n\n".join(formatted_articles)


def _build_prompt(articles_context: str) -> str:
    """Load the writer prompt template and inject formatted articles."""
    template = PROMPT_PATH.read_text(encoding="utf-8")
    logger.debug("Building writer prompt with article context length=%s", len(articles_context))
    return template.replace("{articles}", articles_context)


def _generate_digest(prompt: str) -> str:
    """Generate the digest using Groq's streaming chat completion API."""
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is required for writer generation.")

    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    stream = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model=WRITER_MODEL,
        stream=True,
    )

    response_parts = []
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            response_parts.append(delta)

    response_text = "".join(response_parts).strip()
    if not response_text:
        raise ValueError("Writer returned an empty response.")

    return response_text
