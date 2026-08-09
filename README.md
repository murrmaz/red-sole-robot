# Red Sole Robot

A Django app that moderates `/r/LouboutinLife` by pulling recent comments and
posts, scoring them with an AI inference backend, and reporting whatever gets
flagged back to Reddit. Ingestion, context assembly, evaluation, and action
each run as `django_tasks_db`-backed background tasks, chained together as
new content comes in rather than polled on a fixed schedule.

## Setup

1. `cp .env.example .env` and fill in Reddit API credentials and an inference
   backend URL (`INFERENCE_BACKEND` defaults to `openai_compatible`, pointed
   at any server exposing an OpenAI-compatible `/v1/chat/completions`
   endpoint — Ollama, llama.cpp server, vLLM, ...).
2. `python manage.py migrate`

## Runtime topology

The pipeline is: `ingest_batch` fetches new comments/posts → `prepare_item`
assembles conversational context (walking parent comments, fetching live
from Reddit if an ancestor aged out of retention) → `evaluate_item` scores
the item → `handle_flagged` reports anything flagged, back on Reddit.

Three `db_worker` processes are required, one per queue:

```
manage.py db_worker --queue-name=evaluation
manage.py db_worker --queue-name=reddit      # exactly one process — see below
manage.py db_worker --queue-name=dashboard
```

`ingest_batch`, `prepare_item`, and `handle_flagged` all share a single
process-wide `praw.Reddit` client (`ingest/reddit_client.py`), and
`django_tasks_db`'s `db_worker` processes tasks strictly one at a time per
process — so pinning all three to one `reddit` queue/process is what
actually makes "one shared PRAW instance" true. Running a second `reddit`
worker process silently breaks that guarantee (each process builds its own
independent client), so never scale the `reddit` queue beyond one process.
`evaluate_item` gets its own queue so Reddit throttling can't back up
evaluation throughput; dashboard rollups get their own queue so a metrics
backfill can't compete with either. See the comment above `TASKS` in
`red_sole_robot/settings.py` for the full rationale.

## Cron jobs

Three periodic jobs, run via external cron/systemd timer (nothing in this
repo schedules them itself):

| Command | Frequency | What it does |
| --- | --- | --- |
| `manage.py ingest` | hourly | Enqueues `ingest_batch`: fetches recent comments/posts, inserts anything missing, trims `RawItem` to its retention cap. |
| `manage.py rollup_metrics` | hourly | Recomputes `MetricBucket` rows for the dashboard. Run once with `--full --sync` after first migrating, to backfill history. |
| `manage.py prune_db_task_results --queue-name='*'` | daily | Deletes finished `DBTaskResult` rows. `django_tasks_db` never prunes these on its own, so without this the table grows without bound. |

## Retention model

- `RawItem` — rolling window of the most recent `RETAINED_COMMENT_CAP`
  comments / `RETAINED_POST_CAP` posts, trimmed by `ingest_batch`. This is
  the only place raw content (comment bodies, post text) is retained.
- `EvaluationRecord` / `IngestLogEntry` — permanent, but content-free:
  metadata and verdicts only, never the underlying text.
- `DBTaskResult` (from `django_tasks_db`) stores every task's arguments.
  Task arguments here are always plain IDs/attempt counters — `evaluate_item`
  rebuilds its context read-only from `RawItem` immediately before scoring
  rather than receiving it as an argument — so nothing raw-content-related
  ends up in this table. It still accumulates one row per task run
  regardless, which is what `prune_db_task_results` is for.
