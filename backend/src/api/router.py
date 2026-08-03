import json
import logging
from collections import defaultdict
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..graph.workflow import app as graph_app
from .schemas import (
    ArticleOut,
    ErrorResponse,
    ResearchRequest,
    ResearchResponse,
    SectionOut,
    StatsOut,
    VerificationOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

NODE_LABELS: Dict[str, str] = {
    "planner_node": "Planner",
    "researcher_node": "Researcher",
    "writer_node": "Writer",
    "verifier_node": "Verifier",
}


@router.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/research",
    response_model=ResearchResponse,
    responses={
        422: {"description": "Query is empty or whitespace-only"},
        500: {"model": ErrorResponse, "description": "Graph run failed"},
    },
)
async def run_research(request: ResearchRequest) -> ResearchResponse:
    logger.info("POST /api/research query=%r", request.query)

    try:
        final_state: Dict[str, Any] = graph_app.invoke(_initial_state(request.query))
    except Exception as exc:
        logger.exception("Graph run failed for query=%r", request.query)
        raise HTTPException(
            status_code=500,
            detail="Research pipeline failed. Check server logs for details.",
        ) from exc

    response = _build_research_response(final_state)
    logger.info(
        "POST /api/research completed interests=%s articles=%s score=%s retries=%s",
        response.interests,
        response.stats.articles_fetched,
        response.verification.score,
        response.stats.retries,
    )
    return response


@router.get("/research/stream")
async def stream_research(
    q: str = Query(..., description="Natural-language research query"),
) -> StreamingResponse:
    if not q or not q.strip():
        raise HTTPException(status_code=422, detail="Query must not be empty.")

    query = q.strip()
    logger.info("GET /api/research/stream q=%r", query)
    return StreamingResponse(
        _stream_research_events(query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _initial_state(query: str) -> Dict[str, Any]:
    return {
        "interests": [query],
        "retry_count": 0,
    }


async def _stream_research_events(query: str):
    """Async generator that streams SSE events with keepalive heartbeats.

    The LangGraph ``graph_app.stream()`` call is **synchronous and blocking**
    — it can take minutes per node.  We push it into a background thread so
    this async generator can keep yielding SSE heartbeat comments while the
    graph is working.  Without the heartbeats, Nginx (or the browser's
    EventSource) would decide the connection is dead and close it.
    """
    import asyncio
    import concurrent.futures
    from queue import Queue, Empty

    # Sentinel that signals "the producer thread is done"
    _DONE = object()
    q: Queue = Queue()

    # ---- producer: runs in a thread, pushes SSE strings into the queue ----
    def _produce():
        accumulated_state = _initial_state(query)
        last_node = ""
        try:
            q.put(_sse_event("pipeline_start", {"nodes": list(NODE_LABELS.keys())}))

            for event_chunk in graph_app.stream(
                _initial_state(query), stream_mode="updates"
            ):
                for node_name, state_update in event_chunk.items():
                    if last_node:
                        q.put(_node_event("node_done", last_node))
                    q.put(_node_event("node_start", node_name))
                    last_node = node_name
                    if isinstance(state_update, dict):
                        accumulated_state.update(state_update)

            if last_node:
                q.put(_node_event("node_done", last_node))

            response = _build_research_response(accumulated_state)
            logger.info(
                "SSE stream completed query=%r articles=%s score=%s retries=%s",
                query,
                response.stats.articles_fetched,
                response.verification.score,
                response.stats.retries,
            )
            q.put(_sse_event("done", {"data": response.model_dump()}))
        except Exception as exc:
            logger.exception("SSE stream failed for query=%r: %s", query, exc)
            q.put(
                _sse_event(
                    "error",
                    {"message": "Research pipeline failed. Check server logs for details."},
                )
            )
        finally:
            q.put(_DONE)

    # ---- kick off the producer in a thread ----
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _produce)

    # ---- consumer: drain the queue, yielding heartbeats while waiting ----
    HEARTBEAT = ": heartbeat\n\n"  # SSE comment — ignored by EventSource
    HEARTBEAT_INTERVAL = 15  # seconds

    while True:
        try:
            item = await asyncio.to_thread(q.get, timeout=HEARTBEAT_INTERVAL)
        except Empty:
            # Nothing from the graph yet — send a keepalive comment
            yield HEARTBEAT
            continue

        if item is _DONE:
            break
        yield item


def _node_event(event_type: str, node_name: str) -> str:
    return _sse_event(
        event_type,
        {
            "node": node_name,
            "label": NODE_LABELS.get(node_name, node_name),
        },
    )


def _sse_event(event_type: str, payload: Dict[str, Any]) -> str:
    data = json.dumps({"event": event_type, **payload}, ensure_ascii=False)
    return f"data: {data}\n\n"


def _build_research_response(final_state: Dict[str, Any]) -> ResearchResponse:
    articles: List[Dict[str, Any]] = final_state.get("articles") or []
    retry_count = int(final_state.get("retry_count", 0) or 0)

    return ResearchResponse(
        interests=final_state.get("interests") or [],
        plan=final_state.get("plan") or "",
        sections=_build_sections(articles),
        digest_markdown=final_state.get("draft") or "",
        verification=VerificationOut(
            score=float(final_state.get("verification_score") or 0.0),
            issues=list(final_state.get("verification_issues") or []),
        ),
        stats=StatsOut(
            articles_fetched=len(articles),
            retries=max(0, retry_count - 1),
        ),
    )


def _build_sections(articles: List[Dict[str, Any]]) -> List[SectionOut]:
    grouped: Dict[str, List[ArticleOut]] = defaultdict(list)

    for article in articles:
        topic = str(article.get("topic", "general"))
        grouped[topic].append(
            ArticleOut(
                title=str(article.get("title", "")),
                url=str(article.get("url", "")),
                snippet=str(article.get("snippet", "")),
            )
        )

    return [SectionOut(topic=topic, articles=articles) for topic, articles in grouped.items()]
