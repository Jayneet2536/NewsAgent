import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import settings
from ..errors import PipelineError
from ..evidence import evidence_batches, format_evidence
from ..graph.state import AgentState
from ..llm import generate_text

logger = logging.getLogger(__name__)
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "verifier.txt"
_LINK = re.compile(r"https?://[^\s<>)\]]+")


class VerificationResult(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    score: float = Field(ge=0, le=100)
    issues: list[str]


def _digest_items(draft: str) -> list[str]:
    # Every paragraph/bullet is checked, including prose outside the expected format.
    parts = re.split(r"\n(?=[-*] )|\n\s*\n", draft.strip())
    heading = ""
    items = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if all(line.startswith("#") for line in part.splitlines() if line.strip()):
            heading = part
        else:
            items.append(f"{heading}\n\n{part}" if heading else part)
    return items


def verifier_node(state: AgentState) -> Dict[str, Any]:
    draft = state.get("draft", "").strip()
    if not draft:
        raise PipelineError("There is no generated draft to verify.")
    originals = state.get("sources", state.get("articles", []))
    batches = state.get("draft_batches") or [{"draft": draft, "sources": originals}]
    scores = []
    issues = []
    for batch_index, batch in enumerate(batches, 1):
        evidence = batch["sources"]
        known_urls = {str(source["url"]) for source in evidence}
        for item in _digest_items(batch["draft"]):
            cited = set(_LINK.findall(item))
            if not cited or not cited <= known_urls:
                scores.append(0.0)
                issues.append("Missing or unknown supporting source link in: " + item[:200])
            related = [source for source in evidence if str(source["url"]) in cited] or evidence
            if not related:
                raise PipelineError("No original source evidence is available for verification.")
            build_prompt = lambda context: _build_prompt(item, context)
            chunks = evidence_batches(related, build_prompt, settings.llm_input_budget, item)
            if len(chunks) > 1:
                raise PipelineError("A digest item cites too much evidence for one verification request. Use shorter items.")
            logger.info("Verifier batch=%s item_sources=%s", batch_index, len(chunks[0]))
            try:
                score, item_issues = _parse_verification_response(
                    _generate_verification(build_prompt(format_evidence(chunks[0]))))
            except ValidationError as error:
                raise PipelineError("Verifier returned invalid JSON or an invalid score. Try again.") from error
            scores.append(score)
            issues.extend(item_issues)
    if not scores:
        raise PipelineError("The writer produced no verifiable news items.")
    score = min(scores)
    retry_count = state.get("retry_count", 0) + 1
    logger.info("Verification score=%s threshold=%s attempt=%s issues=%s",
                score, settings.verification_threshold, retry_count, len(issues))
    return {"verification_score": score, "verification_issues": list(dict.fromkeys(issues)),
            "retry_count": retry_count}


def _format_sources(articles: List[Dict[str, Any]]) -> str:
    return format_evidence(articles) if articles else "No source evidence available."


def _build_prompt(draft: str, sources: str) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{draft}", draft).replace("{sources}", sources)


def _generate_verification(prompt: str) -> str:
    return generate_text(prompt, model=settings.verifier_model, stage="Verifier", json_mode=True)


def _parse_verification_response(response_text: str) -> Tuple[float, List[str]]:
    result = VerificationResult.model_validate_json(response_text)
    return result.score, result.issues
