"""Project-root uvicorn launcher.

Usage (from the backend/ directory):
    python run.py

Or directly with uvicorn:
    uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

Environment variables (set in .env or shell before running):
    GROQ_API_KEY        — required for planner and verifier LLM calls
    TAVILY_API_KEY      — required for article search
    FRONTEND_ORIGIN     — e.g. http://localhost:3000  (defaults to * in dev)
    DEBUG               — set to "true" for verbose logging
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,           # auto-reload on source changes during development
        log_level="info",
    )
