import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from ..config import settings
from ..errors import PipelineError
from ..evidence import evidence_batches, format_evidence
from ..graph.state import AgentState
from ..llm import generate_text

logger = logging.getLogger(__name__)
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "writer.txt"


def writer_node(state: AgentState) -> Dict[str, Any]:
    sources = state.get("sources", state.get("articles", []))
    if not sources:
        raise PipelineError("No usable news sources were found in the 24-hour window. Try a different topic.")
    feedback = "\n".join(state.get("verification_issues", []))
    # Feedback is bounded separately; original evidence always retains priority.
    feedback = feedback.encode("utf-8")[:600].decode("utf-8", errors="ignore")
    def build_prompt(context):
        prompt = _build_prompt(context)
        if feedback:
            prompt += "\nCorrect these verification issues:\n" + feedback
        return prompt

    batches = evidence_batches(sources, build_prompt, settings.llm_input_budget,
                               " ".join(state.get("interests", [])))
    drafts = []
    for index, batch in enumerate(batches, 1):
        logger.info("Writer batch %s/%s sources=%s", index, len(batches), len(batch))
        draft = _generate_digest(build_prompt(format_evidence(batch)))
        drafts.append({"draft": draft, "sources": batch})
    sections = defaultdict(list)
    for batch in drafts:
        topic = ""
        for paragraph in re.split(r"\n\s*\n", batch["draft"]):
            if paragraph.startswith("## ") and "\n" not in paragraph.strip():
                topic = paragraph.strip()
            else:
                sections[topic].append(paragraph)
    merged = "\n\n".join("\n\n".join(([topic] if topic else []) + paragraphs)
                          for topic, paragraphs in sections.items())
    return {"draft": merged, "draft_batches": drafts}


def _format_articles(articles: List[Dict[str, Any]]) -> str:
    return format_evidence(articles) if articles else "No sources available."


def _build_prompt(articles_context: str) -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").replace("{articles}", articles_context)


def _generate_digest(prompt: str) -> str:
    return generate_text(prompt, model=settings.writer_model, stage="Writer")
