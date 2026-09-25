# V16: bounded checking and database egress

## Deployment

- Use one Uvicorn process/instance. The checker queue and websocket registry
  are in memory; horizontal scaling requires an external queue/pubsub first.
- Build the frontend with the existing render-build.sh; no new dependencies
  or required schema migration are introduced.
- Company/group checks and company-wide scheduling are temporarily disabled.
  Deploying marks interrupted RUNNING/QUEUED runs FAILED, with a visible message.
- Video JSON remains stored and is fetched through the authorized account detail
  endpoint. Lists load at most 100 rows (UI: 50), with server-side sorting,
  filtering and full-owner summary counts.
- Optional: execute each statement in database/009_checker_performance.sql
  separately in Supabase SQL Editor. These indexes do not remove any data.

## Checking and recovery

- At most five external checks, at most three per Boss/Manager job and two per
  ordinary job. One active job per requester, including across sessions.
- Priority applies to queued requests. Aging prevents ordinary jobs from
  starving; in-progress network requests are not interrupted.
- Overlapping jobs share the request until all consumers have applied its result.
- A transient result-save failure requeues that account once. A persistent
  failure produces FAILED and a missing-account message, never COMPLETED.
- Stop drains requests already submitted and saves their results.
- CheckRun.selected_account_ids records the exact requested snapshot for every
  scope. Compare that snapshot with last_checked_at after an interrupted run.
- HTTP retries apply to timeouts/parse/network errors and retryable HTTP codes;
  permanent 403/404 responses are not retried repeatedly. Retry delay is bounded
  exponential backoff with jitter; video data is preserved on errors.

## Realtime and web responsiveness

- Changed account summaries are delivered only to authorized viewers and patched
  into their cached rows. Other users do not receive another person's progress.
- Summary/dashboard invalidations are coalesced for 8–12 seconds. Account lists
  are marked stale without an immediate refetch after a check. Use “Làm mới” to
  reapply page ordering/filter membership after changes.
- Reconnect reloads the active scope once, to recover missed websocket events.
- Blocking SQL, password hashing, avatar processing/upload and heartbeat checks
  run off the event loop. Argon2 runs at most twice concurrently to bound RAM.
- Database connection/pool failures return a retryable 503 response. They are
  not proof the process crashed. Check Render restart/OOM logs separately.
- HTTP gzip was already enabled. It reduces Render-to-browser traffic, not
  Supabase-to-Render Shared Pool Egress. SQL projection/deferred video loading,
  aggregation and fewer repeated reads address that quota.

## Verification and follow-up

Automated tests use isolated fixtures/mocked network requests; no production
database writes or live TikTok load tests are required. Run:

    python -m pytest -q
    npm run build --prefix frontend

After deploying, verify a 20-channel run, then 100–200 channels for one owner,
including a stopped run and concurrent viewers. Compare processed/total counts,
timestamps, retained video details and role permissions. Check Render slow_api
and checker logs (status, HTTP code, attempts, elapsed seconds) and Supabase
Shared Pool Egress daily for 2–3 days. The code cannot guarantee a specific
latency or quota reduction without those production measurements.
