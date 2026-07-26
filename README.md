# NewsAgent

A starter FastAPI + LangGraph backend for an AI-powered news agent.

## Structure

- backend/src: application entrypoint, configuration, workflow graph, nodes, tools, and prompts
- backend/requirements.txt: Python dependencies
- backend/Dockerfile: container build for the API service
- docker-compose.yml: local orchestration for the backend

## Run locally

```bash
cd backend
pip install -r requirements.txt
uvicorn src.main:app --reload
```

## Run with Docker

```bash
docker compose up --build
```
