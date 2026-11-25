"""Extract source passages without replacing the full originals in research state."""
import re

from .errors import PipelineError
from .llm import token_bound


def clip_bytes(text: str, limit: int) -> str:
    return text.encode("utf-8")[:max(0, limit)].decode("utf-8", errors="ignore")


def select_passages(content: str, query: str, limit: int = 1600) -> str:
    if token_bound(content) <= limit:
        return content
    # Rank paragraphs/sentences using the claim/topic; include the lead and keep
    # selected passages in original order. Do not synthesize new evidence.
    chunks = []
    for paragraph in re.split(r"\n\s*\n|(?<=[.!?])\s+", content):
        if not paragraph.strip():
            continue
        encoded = paragraph.strip().encode("utf-8")
        # Auto-generated transcripts often lack punctuation. Search overlapping
        # windows through the entire text instead of discarding everything after
        # the first long sentence.
        if len(encoded) <= 600:
            chunks.append(paragraph.strip())
        else:
            chunks.extend(encoded[start:start + 600].decode("utf-8", errors="ignore").strip()
                          for start in range(0, len(encoded), 500))
    keywords = set(re.findall(r"\w{3,}", query.lower()))
    ranked = sorted(range(len(chunks)), key=lambda index:
                    (len(keywords & set(re.findall(r"\w{3,}", chunks[index].lower()))), -index), reverse=True)
    selected = {0} if chunks else set()
    used = token_bound(chunks[0]) if chunks else 0
    for index in ranked:
        if index in selected:
            continue
        size = token_bound(chunks[index]) + 5
        if used + size <= limit:
            selected.add(index)
            used += size
    return clip_bytes("\n[...]\n".join(chunks[index] for index in sorted(selected)), limit)


def excerpt_source(source: dict, query: str, limit: int = 1600) -> dict:
    return {**source, "content": select_passages(str(source.get("content", "")), query, limit)}


def format_evidence(sources: list[dict]) -> str:
    return "\n\n---\n\n".join(
        f"Topic: {source.get('topic', '')}\nTitle: {source.get('title', '')}\n"
        f"URL: {source.get('url', '')}\nSource type: {source.get('source_type', 'article')}\n"
        f"Published at: {source.get('published_at') or 'Unknown'}\n"
        f"Evidence: {source.get('content', '')}" for source in sources
    )


def evidence_batches(sources: list[dict], build_prompt, input_budget: int, query: str = "") -> list[list[dict]]:
    batches = []
    batch = []
    for source in sources:
        excerpt = excerpt_source(source, f"{query} {source.get('topic', '')} {source.get('title', '')}")
        if token_bound(build_prompt(format_evidence([excerpt]))) + 128 > input_budget:
            # Long metadata or a large draft can leave less room for evidence.
            overhead = token_bound(build_prompt(format_evidence([{**excerpt, 'content': ''}]))) + 128
            allowance = input_budget - overhead - 16
            if allowance < 200:
                raise PipelineError("Source metadata or draft exceeds the prompt budget. Use a shorter query or smaller batches.")
            excerpt = excerpt_source(source, query, min(1600, allowance))
        candidate = batch + [excerpt]
        if batch and (len(candidate) > 3 or
                      token_bound(build_prompt(format_evidence(candidate))) + 128 > input_budget):
            batches.append(batch)
            batch = []
        batch.append(excerpt)
    if batch:
        batches.append(batch)
    return batches
