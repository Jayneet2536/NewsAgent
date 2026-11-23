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
