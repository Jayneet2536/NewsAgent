The pipeline searches articles and YouTube videos in a shared rolling 24-hour UTC window.
Set `YOUTUBE_API_KEY` to a Google API key with YouTube Data API v3 enabled.
Install the updated requirements for `youtube-transcript-api`. Missing YouTube
configuration or unavailable transcripts leave article research operational.
Only videos with usable transcripts and articles with extracted content become evidence.
Reliable publication timestamps are checked against the window; undated articles
remain eligible under Tavily's one-day search filter and have `published_at: null`.

Completed feeds are saved to SQLite after the final verification attempt, including
feeds that exhaust their retries below the verification threshold. The database
retains that verification score and issues, original evidence, plan, interests,
window boundaries, final Markdown and UTC `stored_at` timestamp. Storage errors
fail the run rather than reporting a successful save.

Set `DATABASE_PATH` to choose the file location (default: `data/newsagent.sqlite3`,
relative to the backend working directory). For containers, mount the database's
directory as a persistent volume so feeds survive container replacement.
Both REST and streaming responses include `feed_id` and `stored_at`, and section
items include `source_type`, `publisher`, `published_at` and `thumbnail_url`.
The existing `plan` string contains structured JSON; existing section field names
remain available for frontend compatibility.

Model selection and request limits:

- `GROQ_MODEL` defaults to `openai/gpt-oss-120b` for Planner, Writer and Verifier.
  Optional `PLANNER_MODEL`, `WRITER_MODEL`, and `VERIFIER_MODEL` take precedence.
  The legacy `MODEL_NAME` setting does not override these three roles.
- `GROQ_TPM_LIMIT` defaults to `8000`, matching the observed account allowance.
  Set this to your actual Groq account limit, not the model's context length.
- `LLM_INPUT_BUDGET=5000` uses a conservative UTF-8 byte bound for input tokens,
  including prompt overhead. `LLM_OUTPUT_BUDGET=1200` caps generated tokens,
  including reasoning tokens. The budgets plus 256 safety tokens must fit TPM.
- Evidence is selected into short passages and batched before writing. Each
  digest item is verified against its cited source passages. Full originals
  remain in research state and SQLite; the verifier does not use generated
  summaries as source evidence. Missing support in an excerpt is flagged.
- Requests share a process-wide sliding-minute token budget. Actual Groq usage
  releases unused reservations. Rate-limit responses receive at most one delayed
  retry; authentication, unavailable models, oversized inputs, empty/truncated
  outputs, and invalid verification responses fail the run. API failures are
  never converted to a digest, a factual score of zero, or a stored feed.
- The limiter covers this backend process. Multiple workers, replicas, or other
  apps sharing the Groq account need a shared limiter or smaller allocated quotas.
- `RESEARCH_MAX_QUERIES=6` caps each query list and `RESEARCH_MAX_SOURCES=12` caps
  the final source set. Selection gives each topic and source type a turn.
  Duplicate tracking URLs and identical substantial content are removed.

Article fetching rejects profile/listing pages, short text, and common access
challenges. Permanent HTTP 4xx responses (except 408/429) stop article retries.
YouTube logs candidate counts, accepted transcripts, timestamp skips, transcript
error types and API error reasons such as `quotaExceeded`, without API keys.
Transcript HTTP requests have a timeout; unavailable videos remain optional.

Expected pipeline failures return HTTP 502 for REST or an `error` event for SSE.
The existing frontend displays that error instead of a completed feed. A genuine
low verification score still triggers the existing rewrite loop and is retained
with its issues if attempts are exhausted.

After code changes, rebuild from the `NewsAgent` directory:

```powershell
docker compose up --build -d
docker compose logs -f backend
```

Model and budget defaults work without adding new variables to `.env`.
After changing environment values only, use
`docker compose up -d --force-recreate backend`.
Recreating the current backend container may remove its SQLite file unless you
have mounted a persistent database volume as described above.

Hosted deployments can set `DATABASE_URL` to a PostgreSQL connection string
(for example, the pooled connection URL from Neon, including `sslmode=require`).
When set, it takes precedence over `DATABASE_PATH`; the `news_feeds` table is
created automatically on the first completed run. A failed PostgreSQL save does
not fall back to local disk. Existing SQLite records are not imported automatically.
Keep `DATABASE_URL` only in backend secrets, never in frontend settings.

The Docker image listens on `PORT` when provided by a host, otherwise port `8000`.
For Render, create a Docker Web Service with root directory `backend`, Dockerfile
`./Dockerfile`, Free instance type, and health check `/api/health`. Set backend API
keys, `DATABASE_URL`, and `FRONTEND_ORIGIN` in Render environment settings.

The frontend supports separate static hosting. Create a Render Static Site with
root directory `frontend`, build command `node build.mjs`, and publish directory
`dist`. Set its **public** build variable `PUBLIC_API_BASE` to the backend HTTPS
origin, for example `https://newsagent-api.onrender.com`, without `/api` or a
trailing path. Rebuilding generates `dist/config.js`. Set the backend's
`FRONTEND_ORIGIN` to the actual frontend HTTPS origin. Local Docker continues to
use same-origin Nginx routing with the checked-in default `frontend/config.js`.
Static hosting does not run the frontend Nginx container or Docker Compose.
