from fastapi import FastAPI

from .config import settings
from .graph.workflow import build_workflow

app = FastAPI(title=settings.app_name, version="0.1.0")
workflow = build_workflow()


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.post("/run")
async def run_workflow(payload: dict[str, str]) -> dict[str, object]:
    topic = payload.get("topic", "latest AI news")
    result = workflow.invoke({"topic": topic})
    return result
