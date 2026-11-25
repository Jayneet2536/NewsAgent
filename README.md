# NewsAgent

NewsAgent turns a plain-text query into a Markdown news digest using a four-stage LangGraph workflow. It searches news articles through Tavily and news videos through YouTube Data API v3, retrieves article text and video transcripts, drafts summaries with source links, and checks claims against the collected evidence.

The FastAPI backend streams workflow events and the final result to a vanilla HTML/CSS/JavaScript frontend using Server-Sent Events (SSE). Docker Compose runs the frontend and backend together, with Nginx serving the UI and proxying API requests through one origin. Completed feeds are saved in SQLite with their UTC storage time.

## How it works

1. **Planner:** Converts the user's interests into separate, Pydantic-validated `web_queries` and `youtube_queries`. Publication windows are applied by fetchers rather than added to search text.
2. **Researcher:** Runs article and YouTube collection concurrently. Articles supply extracted page text; videos supply transcripts. Both become a shared `NewsSource` model containing the title, URL, source type, content, topic, publication time, and available publisher/thumbnail metadata. The researcher filters relevance, removes duplicate URLs and identical substantial content, and limits the final source set.
3. **Writer:** Selects relevant passages and writes the digest in bounded evidence batches, retaining supporting article and video links. Full source content remains available in research state and storage.
4. **Verifier:** Checks individual digest items against their cited evidence and returns a score and issues. Low scores trigger a bounded rewrite loop. Provider errors stop the run rather than becoming a digest or a factual score of zero.

A final persistence node saves the completed digest, sources, search plan, interests, verification result, research window, and storage timestamp. A feed that exhausts its rewrite attempts can still be saved with a low score and its issues; the score is not a guarantee of accuracy.

### Source window and YouTube behavior

- Both fetchers share a rolling 24-hour UTC window. Tavily uses a one-day news search, and reliable publication timestamps are checked against the exact window. Articles without reliable timestamps remain eligible and have `published_at: null`.
- YouTube searches use publication boundaries and both `medium` and `long` duration categories. Only videos with usable transcripts become research sources; descriptions are metadata, not substitute evidence.
- The current transcript fetcher requests English captions. Videos with only other-language captions can be skipped with `NoTranscriptFound`. Disabled captions, blocked requests, and other transcript failures do not stop article research. See the [transcript library documentation](https://github.com/jdepoix/youtube-transcript-api#retrieve-the-available-transcripts).
- Workflow events and keepalive heartbeats are streamed over SSE. The completed digest arrives in the final event; individual generated tokens are not streamed to the browser.

## Run the frontend and backend with Docker

### 1. Prerequisites

- Docker Engine with Docker Compose, or Docker Desktop running Linux containers on Windows.
- A Groq API key for planning, writing, and verification.
- A Tavily API key for article search.
- A Google API key with **YouTube Data API v3** enabled for video search. Without it, video research is skipped and article research can continue.

The frontend is static HTML/CSS/JavaScript; it does not require Node.js or `npm install`.

### 2. Configure the backend

Run commands from the repository root, the directory containing `docker-compose.yml`.

Copy the example configuration if you do not already have `backend/.env`:

```powershell
# Windows PowerShell
Copy-Item backend/.env.example backend/.env
```

```bash
# Linux / WSL / macOS
cp backend/.env.example backend/.env
```

Keep an existing `.env` rather than replacing its keys. Set these values in **`backend/.env`**, not a root-level `.env`:

```dotenv
GROQ_API_KEY=your_groq_key
TAVILY_API_KEY=your_tavily_key
YOUTUBE_API_KEY=your_youtube_key

GROQ_MODEL=openai/gpt-oss-120b
GROQ_TPM_LIMIT=8000
LLM_INPUT_BUDGET=5000
LLM_OUTPUT_BUDGET=1200
RESEARCH_MAX_QUERIES=6
RESEARCH_MAX_SOURCES=12
DATABASE_PATH=data/newsagent.sqlite3
```

To obtain the YouTube key, create or select a project in [Google Cloud Console](https://console.cloud.google.com/), enable **YouTube Data API v3** in **APIs & Services → Library**, and choose **Credentials → Create credentials → API key**. Public video search uses an API key; this backend does not require an OAuth sign-in flow. [Google's setup guide](https://developers.google.com/youtube/data/guides/authentication)

Keep API keys out of version control. Use the supplied `.env.example` to share configuration names without credentials.

### 3. Build and start

```bash
docker compose up --build -d
docker compose ps
```

If a local backend is already using port `8000`, stop it first. The frontend also needs port `80` available.

| Service | Address |
| --- | --- |
| Frontend | http://localhost |
| Interactive API documentation | http://localhost:8000/docs |
| Backend health | http://localhost:8000/api/health |

Open the frontend through Nginx at `http://localhost`. Its `/api/` requests are proxied to the backend, including SSE requests with buffering disabled. Compose sets `FRONTEND_ORIGIN=http://localhost` for the backend.

Enter a query such as `Nvidia announcements and Indian technology industry news`. Requests can take several minutes while sources are retrieved, evidence batches are processed, and token allowances reset.

### 4. Logs, updates, and shutdown

```bash
# Follow backend logs
docker compose logs -f backend

# Rebuild after source-code or dependency changes
docker compose up --build -d

# Reload backend/.env after changing keys or settings
docker compose up -d --force-recreate backend

# Stop services while retaining their containers
docker compose stop
```

Environment changes require container recreation; `docker compose restart` alone does not apply new environment values. [Docker documentation](https://docs.docker.com/reference/cli/docker/compose/restart/)

`docker compose down` removes the containers and network. Read the storage section before removing or recreating a backend that contains saved feeds.

## Feed storage

SQLite is built in; no separate database server is required. The database is created on the first completed run at:

- **Local backend:** `backend/data/newsagent.sqlite3` when started from `backend/`.
- **Docker backend:** `/app/data/newsagent.sqlite3` inside the container.

The `news_feeds` table stores the Markdown digest, full collected sources, interests, plan, verification score/issues, window boundaries, and an ISO 8601 UTC `stored_at` timestamp. API results include `feed_id` and `stored_at`. Generation or verification API failures do not save a completed feed.

**The checked-in Compose file does not mount a database volume.** Restarting the same container retains its database, but replacing or removing that container can lose it. Back up existing feeds before rebuilding or adding a new volume.

For a persistent database, create an optional `compose.storage.yml` beside `docker-compose.yml`:

```yaml
services:
  backend:
    volumes:
      - newsagent-data:/app/data

volumes:
  newsagent-data:
```

For a fresh volume, build the backend and give its non-root application user write access before starting both services:

```bash
docker compose -f docker-compose.yml -f compose.storage.yml build backend
docker compose -f docker-compose.yml -f compose.storage.yml run --rm --no-deps --user root backend sh -c "mkdir -p /app/data && chown appuser:appgroup /app/data"
docker compose -f docker-compose.yml -f compose.storage.yml up --build -d
```

Use both `-f` arguments for subsequent Compose commands when using this optional file. A new volume does not automatically import a database from an older container. Named volumes survive `docker compose down`; `down -v` deletes them.

## Run only the backend locally

Use **Python 3.12**, matching the project metadata and Docker image. From `backend/`:

```powershell
# Windows PowerShell; create venv only if it does not already exist
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe run.py
```

```bash
# Linux / WSL / macOS; use a Linux venv rather than the Windows venv in WSL
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

The backend loads `backend/.env` and starts on port `8000` with development reload enabled. Visit http://localhost:8000/docs to try it without the frontend. This command starts only the API; use Docker Compose for the supplied frontend and Nginx proxy.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Shared model for the three LLM agents. |
| `PLANNER_MODEL`, `WRITER_MODEL`, `VERIFIER_MODEL` | Shared model | Optional per-agent overrides. Legacy `MODEL_NAME` does not select these agents. |
| `GROQ_TPM_LIMIT` | `8000` | Token-per-minute allowance allocated to this backend process. Match your account limits. |
| `LLM_INPUT_BUDGET` | `5000` | Conservative UTF-8 byte bound for input tokens, including prompt overhead. |
| `LLM_OUTPUT_BUDGET` | `1200` | Maximum generated tokens per request, including reasoning tokens. |
| `RESEARCH_MAX_QUERIES` | `6` | Maximum queries in each web/video list. |
| `RESEARCH_MAX_SOURCES` | `12` | Maximum final sources, selected across topics and source types. |
| `VERIFICATION_THRESHOLD` | `80` | Score below which another writing attempt is requested. |
| `MAX_RETRIES` | `2` | Existing attempt cap: normally at most two Writer/Verifier passes. |
| `DATABASE_PATH` | `data/newsagent.sqlite3` | SQLite file path relative to the backend working directory. |
| `FRONTEND_ORIGIN` | Unset locally; `http://localhost` in Compose | Allowed browser origin. |

Input and output budgets plus 256 safety tokens must fit `GROQ_TPM_LIMIT`. Requests share a process-wide sliding-minute token budget. Waiting for that budget is expected; increasing it without a matching account allowance can cause provider errors. Multiple backend workers or replicas need coordinated rate limiting.

See [backend/CONFIGURATION.md](backend/CONFIGURATION.md) for additional behavior and settings.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Server liveness; returns `{"status":"ok"}`. Does not validate external API keys. |
| `POST /api/research` | Runs research and returns the completed JSON result. |
| `GET /api/research/stream?q=...` | Streams workflow events, heartbeats, and a final `done` or `error` event. |

Example request body for `POST /api/research`:

```json
{"query": "Nvidia announcements and Indian technology industry news"}
```

Results include interests, a JSON-encoded `plan` string, topic sections, `digest_markdown`, verification, statistics, `feed_id`, and `stored_at`. Section items expose `source_type` (`article` or `youtube`) and available publication, publisher, and thumbnail metadata without the full source text. For compatibility, the `sections[].articles` field and `stats.articles_fetched` count include both source types.

Expected provider/generation failures return HTTP `502` for REST or an `error` event for SSE. An SSE connection can start with HTTP `200` and later report a pipeline error; that status alone does not establish research success.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Groq `401` | Correct `GROQ_API_KEY` in `backend/.env` and recreate the backend container. |
| Groq `404 model_not_found` | Choose a model available to your account using `GROQ_MODEL` or a role override. |
| Groq `413` or repeated `429` | Match token budgets to your account limits; reduce request size or wait for quota reset. Retrying an unchanged oversized prompt is insufficient. |
| `Waiting ... for the Groq token budget` | Normal pacing. Follow the logs while the request remains connected. |
| No YouTube sources | Look for `configured=`, candidate counts, accepted transcripts, and skip reasons. Check API enablement/quota and the English-caption requirement. Strict 24-hour/duration filters can return no candidates. |
| Article `403`, empty text, or a paywall | That source may be skipped; other collected sources can still be used. |
| Docker `failed to xattr ... .test-tmp-newsagent` | Confirm `backend/.dockerignore` excludes temporary test directories and remove only obsolete test artifacts whose permissions you control. |
| WSL `/usr/bin/docker: Input/output error` | Save WSL work, quit Docker Desktop, run `wsl --shutdown` from Windows PowerShell, then reopen Docker Desktop. |

## Tests

From `backend/`, after installing requirements:

```powershell
# Windows: keep temporary test files outside the Docker build context
$env:PYTHONDONTWRITEBYTECODE = "1"
$testTemp = Join-Path $env:TEMP ("newsagent-tests-" + [guid]::NewGuid().ToString("N"))
.\venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp $testTemp
```

```bash
# Linux / WSL / macOS
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests -q -p no:cacheprovider --basetemp "$(mktemp -d)/pytest"
```

The test suite mocks external services, so it does not require live API calls.

## Repository structure

```text
NewsAgent/
|-- docker-compose.yml
|-- backend/
|   |-- .env.example
|   |-- CONFIGURATION.md
|   |-- Dockerfile
|   |-- requirements.txt
|   |-- run.py
|   |-- src/
|   |   |-- api/          # REST responses and SSE events
|   |   |-- graph/        # LangGraph state and workflow
|   |   |-- nodes/        # Planner, Researcher, Writer, Verifier
|   |   |-- tools/        # Tavily, article extraction, YouTube transcripts
|   |   |-- prompts/
|   |   |-- models.py    # Shared search plan and source schemas
|   |   |-- evidence.py  # Passage selection and batching
|   |   |-- llm.py       # Groq requests and token pacing
|   |   `-- database.py  # Timestamped feed persistence
|   `-- tests/
`-- frontend/
    |-- Dockerfile
    |-- index.html
    `-- nginx/default.conf
```
