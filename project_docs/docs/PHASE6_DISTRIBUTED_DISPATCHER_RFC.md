# Phase 6 — Distributed Dispatcher: Design RFC

| Field      | Value                                                              |
|------------|--------------------------------------------------------------------|
| Status     | **Draft** — design only, no code yet                               |
| Phase      | 6 (of the 2026-05-26 stability roadmap)                            |
| Author     | OctoAgent stability program                                        |
| Date       | 2026-05-26                                                         |
| Depends on | Phase 0 (topology freeze, commit `86003f7`)                        |
| Blocked by | Phase 7 (physical 47→8 domain merge) for clean dispatcher seam     |

> **Scope of this document**: this is the design RFC. It does **not**
> contain executable code. Its purpose is to lock in the architectural
> choice and the staged-rollout plan **before** any code changes, so that
> the actual implementation work is small, contained, and reversible.

---

## 1. Why Phase 6 exists

Today OctoAgent runs as a **single-host monolith** with cooperating
sub-processes on one machine (currently `192.168.110.2`):

| Component         | Process model                                       | Concurrency |
|-------------------|-----------------------------------------------------|-------------|
| Gateway (FastAPI) | Single `uvicorn` worker                             | asyncio     |
| LangGraph runtime | `langgraph dev --n-jobs-per-worker 4` (in-process)  | 4 async slots |
| Channel manager   | In-process `asyncio.Queue` (`MessageBus`)           | asyncio     |
| Checkpointer      | AsyncPostgresSaver against single Postgres          | per-run     |
| OOM guard         | `runtime_oom_guard.py`, host-local                  | local       |
| Orphan sweeper    | `harness/lifecycle.py::OrphanRunSweeper`, host-local| local       |

Specific single-host failure modes observed in production:

1. **No horizontal capacity headroom**. When the host saturates, the only
   knob is `OCTO_LANGGRAPH_N_JOBS_PER_WORKER`, which is bounded by host
   RAM (each agent run is multi-GB peak). The OOM guard then *cancels
   runs* to recover memory — a graceful-degradation last resort, not a
   capacity strategy.
2. **No durable inbound queue**. `channels/message_bus.py` is an
   in-memory `asyncio.Queue`. A process restart drops any message that
   was enqueued but not yet dispatched. We have repeatedly papered over
   this with the QQ bridge's own retry, but it's fragile.
3. **Restart-time race window**. On `systemctl restart`, the gateway is
   down for ~30 s during `next build` while LangGraph and channel
   bridges have already exited. External callers see HTTP 502.
4. **No coordinated cancellation across replicas**. There can only ever
   be one replica today; the moment we want two, we need a leader to
   own the OOM-guard cancel decision and the orphan sweep.

Phase 6 exists to fix #1 and #2 first (durable inbound + horizontal
worker capacity), then #3 (zero-downtime rolling restart) and #4
(leader-coordinated guards) as natural follow-ons.

## 2. Goals & non-goals

### In scope (the deliverables Phase 6 is allowed to ship)

* **G1 — Durable inbound queue**. Channel messages enqueued by any QQ /
  webhook / API bridge must survive process restart. Acceptable loss
  window: at most one message in flight per bridge instance, and only
  if the bridge crashes mid-acknowledge.
* **G2 — Worker registry**. Every running runtime worker (gateway +
  LangGraph process group, or future standalone dispatcher) registers
  itself with a heartbeat. Stale entries are reaped automatically.
* **G3 — Leader election**. Exactly one worker holds the "coordinator"
  role at a time. The coordinator owns: orphan-run sweeping, OOM-guard
  global decisions, and scheduled-task dispatch.
* **G4 — At-least-once dispatch with idempotency keys**. Every job has
  a stable `dispatch_id`; re-delivering the same `dispatch_id` is a
  no-op for any worker that already processed it.
* **G5 — Drain & graceful rolling restart**. A worker can be marked
  "draining"; the coordinator stops sending it new work and lets
  in-flight runs finish (bounded by `OCTO_GRACEFUL_DRAIN_TIMEOUT`,
  default 600 s) before SIGTERM.

### Out of scope (NOT Phase 6 — explicit non-goals)

* **N1**. Geo-distributed deployment. Single data-centre / single
  Postgres primary only.
* **N2**. Replacing LangGraph's in-process worker model. We keep
  `langgraph dev` and its async-job concurrency; Phase 6 routes *which
  worker pool* picks up a run, not *how* that worker pool internally
  schedules.
* **N3**. Replacing Postgres as the system of record. Checkpoints,
  run-journal, and the new dispatch tables all live in the same
  Postgres instance.
* **N4**. New API surface. The dispatcher is internal infrastructure;
  externally observable behaviour does not change.
* **N5**. Migrating existing channel bridges (`channels/manager.py`,
  `channels/message_bus.py`) en bloc. We will add a durable backend
  *behind* the existing `MessageBus` interface as an optional plug-in,
  selectable via env flag — see §6 staged rollout.

## 3. What we already have that's reusable

Phase 6 deliberately stands on what already works:

* **Postgres is already the system of record**. The async checkpointer
  (`backend/src/agents/checkpointer/async_provider.py`) and the run
  journal (`backend/src/harness/run_journal.py`) both use the same
  `DATABASE_URL`. We inherit:
  * The `psycopg_pool.AsyncConnectionPool` pattern (`run_journal.py`
    lines 102–122).
  * The `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`
    bootstrap pattern (`run_journal.py` lines 39–52). New dispatcher
    tables follow the same convention; no migrations framework needed.
* **Stale-run detection logic**. `OrphanRunSweeper` already polls
  `/threads/search` for busy threads and reconciles. The Phase 6
  coordinator role can subsume this loop unchanged.
* **OOM guard primitives**. `runtime_oom_guard.py` knows how to release
  process memory and cancel busy runs. Phase 6 wraps it with a
  coordinator check so only the leader issues `RUNTIME_STOP` decisions
  when multiple replicas exist.
* **`run_journal` heartbeat semantics**. The journal already records
  `heartbeat_at` per run with a stale-after threshold. The same column
  semantics apply to the new `dispatcher_workers` table.

## 4. Architectural-choice comparison

Three candidate backends were evaluated for the durable queue + worker
registry + leader election triad:

### Option A — Postgres-native (RECOMMENDED)

* **Mechanism**: `SELECT … FOR UPDATE SKIP LOCKED` for queue claim,
  `LISTEN`/`NOTIFY` for low-latency wake-ups, advisory locks
  (`pg_try_advisory_lock`) for leader election.
* **New tables** (in the existing `DATABASE_URL` database):
  * `octo_dispatch_queue` — `(dispatch_id pk, kind, payload jsonb,
    available_at timestamptz, claimed_by, claimed_at, attempts,
    last_error)`.
  * `octo_dispatch_workers` — `(worker_id pk, host, pid, started_at,
    heartbeat_at, role enum('worker','leader'), draining bool)`.
  * `octo_dispatch_leader_lock` — single-row table holding the
    advisory-lock key (purely informational; the lock itself lives in
    `pg_locks`).
* **Pros**:
  * Zero new infrastructure. Same Postgres we already operate, back
    up, and monitor.
  * Transactional dispatch ⇄ checkpoint ⇄ journal — all three updates
    can sit in one `BEGIN; … COMMIT;` block, eliminating dual-write
    inconsistency.
  * `SKIP LOCKED` is the canonical Postgres queue pattern (used by
    `pgmq`, `River`, Sidekiq Pro). Well-understood failure modes.
  * Already-pinned `psycopg`/`psycopg_pool` is sufficient — no new
    deps.
* **Cons**:
  * Throughput ceiling ~10 k jobs/s on a single primary. Acceptable;
    real agent-run throughput is ≤ 100/s even under aggressive
    autoscaling.
  * `LISTEN`/`NOTIFY` payload is capped at 8000 B; we use it only for
    wake-up signals, never to carry the job body.
  * Postgres becomes the SPoF. Already true today for checkpointer.

### Option B — Redis Streams (Stream + consumer groups)

* **Mechanism**: `XADD` for enqueue, `XREADGROUP` for consumer-group
  claim, `XACK` for finalize, `XPENDING` + `XCLAIM` for re-delivery
  on stale consumer.
* **Pros**:
  * Higher throughput (100 k+ msg/s).
  * Native consumer-group + pending-entry-list (PEL) semantics map
    closely to Phase 6 G4 (at-least-once + idempotent re-delivery).
* **Cons**:
  * New runtime dependency. We do not run Redis today.
  * Dual write: dispatch updates must commit in *both* Redis and
    Postgres (checkpointer state) — eventual inconsistency risk.
  * Backup/HA story is a separate ops project (Sentinel / Cluster).
* **Verdict**: Pay this cost only if Option A's 10 k/s ceiling
  measurably blocks us. Today's load is < 1 % of that.

### Option C — NATS JetStream

* **Mechanism**: Subject-based pub/sub with persistent streams,
  KV store for worker registry, consumer ack/redelivery.
* **Pros**:
  * Best multi-region story. Mirror streams, leaf nodes.
  * KV + Object Store + Streams in one daemon.
* **Cons**:
  * Brand-new operational surface. Cluster sizing, monitoring,
    backup all need to be re-learned by ops.
  * Same dual-write problem as Redis vs Postgres checkpointer.
* **Verdict**: Reconsider only if/when geo-distributed deployment
  enters scope (which §2 N1 says it does not, this phase).

### Decision

**Option A (Postgres-native)** is selected. Rationale: it satisfies all
five goals (G1–G5) with zero new operational surface and zero new code
dependencies. Throughput headroom is sufficient by 2 orders of
magnitude. If we ever exceed it, the Option-A code surface is small
enough (~600 LoC estimated) that migrating to Option B/C later is a
contained refactor.

## 5. Data model

```sql
-- Durable inbound + scheduled job queue.
CREATE TABLE IF NOT EXISTS octo_dispatch_queue (
    dispatch_id    text        PRIMARY KEY,
    kind           text        NOT NULL,                     -- 'channel_inbound' | 'scheduled_run' | 'sweep' | ...
    payload        jsonb       NOT NULL,                     -- channel message envelope or run request
    priority       smallint    NOT NULL DEFAULT 0,
    available_at   timestamptz NOT NULL DEFAULT now(),
    enqueued_at    timestamptz NOT NULL DEFAULT now(),
    claimed_by     text        NULL,                         -- worker_id or NULL
    claimed_at     timestamptz NULL,
    attempts       smallint    NOT NULL DEFAULT 0,
    max_attempts   smallint    NOT NULL DEFAULT 5,
    last_error     text        NULL,
    finished_at    timestamptz NULL,
    finished_state text        NULL                          -- 'ok' | 'failed' | 'cancelled'
);

CREATE INDEX IF NOT EXISTS octo_dispatch_queue_claim_idx
    ON octo_dispatch_queue (available_at, priority DESC)
    WHERE finished_at IS NULL;

CREATE INDEX IF NOT EXISTS octo_dispatch_queue_kind_idx
    ON octo_dispatch_queue (kind, finished_at);

-- Live worker registry.
CREATE TABLE IF NOT EXISTS octo_dispatch_workers (
    worker_id     text        PRIMARY KEY,                   -- host:pid:bootid
    host          text        NOT NULL,
    pid           integer     NOT NULL,
    started_at    timestamptz NOT NULL DEFAULT now(),
    heartbeat_at  timestamptz NOT NULL DEFAULT now(),
    role          text        NOT NULL DEFAULT 'worker',     -- 'worker' | 'leader'
    draining      boolean     NOT NULL DEFAULT false,
    capabilities  jsonb       NOT NULL DEFAULT '{}'::jsonb   -- e.g. {"gpu":true,"max_recursion":48}
);

CREATE INDEX IF NOT EXISTS octo_dispatch_workers_heartbeat_idx
    ON octo_dispatch_workers (heartbeat_at);
```

Leader election uses Postgres advisory locks, **not** a table row:

```sql
-- key 1 = leader role, key 2 = sweeper, key 3 = ... (reserved)
SELECT pg_try_advisory_lock(0x6F63746F, 1);   -- 'octo' magic, role 1
```

`pg_try_advisory_lock` is **session-scoped**: when the leader's
connection drops (process crash, network partition, normal shutdown),
Postgres automatically releases the lock; any other waiting worker can
then claim it. This sidesteps the lease-renewal complexity of
TTL-based election (etcd/Consul/ZK-style) entirely.

## 6. Staged rollout (the order in which Phase 6 code actually lands)

Each stage is a **separate PR**. Each leaves the system fully operational
even if the next stage never lands.

### Stage 6.1 — Schema & worker registry only (read-only deliverable)

* Add the three tables above behind a new module
  `backend/src/runtime/dispatcher/schema.py` and a bootstrap call from
  `harness/lifecycle.py` startup.
* Every process registers itself + heartbeats every 5 s. The
  gateway already has a startup hook; LangGraph workers and channel
  bridges each get a thin wrapper.
* **No behaviour change**. The registry is observable
  (`SELECT * FROM octo_dispatch_workers` and a `/api/runtime/workers`
  endpoint exposing the read view), but nothing dispatches off it
  yet.
* **Rollback**: drop the tables and the endpoint.

### Stage 6.2 — Leader election (read-mostly)

* Introduce `runtime/dispatcher/leader.py` holding the advisory-lock
  loop.
* Move `OrphanRunSweeper.run()` and `runtime_oom_guard`'s stop
  decision under an `if is_leader():` guard.
* **No queue yet**. Behaviour is identical on a single-host deployment
  (the only running process is always the leader); on multi-host it
  prevents double-sweep / double-cancel.
* **Rollback**: revert the `is_leader()` guards (the leader module
  itself is dormant if no one calls it).

### Stage 6.3 — Durable inbound queue (writes + reads)

* Add `MessageBus.PostgresBackend` implementing the existing interface.
* Enabled by `OCTO_DISPATCH_BACKEND=postgres` env flag, default
  `inmemory` (today's behaviour).
* `channels/manager.py::_dispatch_loop` continues to consume from the
  bus; only the bus storage changes.
* **Verification gate**: run the 4-bridge regression (QQ inbound +
  webhook + scheduled run + direct API) under both backends and
  compare metrics. Cut over per-bridge.

### Stage 6.4 — Scheduled-task dispatch + retries

* New tool / hook: `enqueue_dispatch(kind, payload, available_at,
  max_attempts)`.
* Coordinator worker (the elected leader) polls
  `octo_dispatch_queue WHERE available_at <= now() AND finished_at IS
  NULL FOR UPDATE SKIP LOCKED LIMIT 1` and routes to LangGraph runs.
* On failure: `available_at = now() + exponential_backoff(attempts)`
  up to `max_attempts`, then `finished_state='failed'`.
* Exposes `/api/runtime/dispatch` for inspection (read-only).

### Stage 6.5 — Drain & rolling restart

* `octoagent drain WORKER_ID` CLI verb sets `draining=true`, waits up
  to `OCTO_GRACEFUL_DRAIN_TIMEOUT` for in-flight runs, then exits.
* `scripts/start-octoagent.sh restart` becomes a rolling sequence
  when N > 1 replicas are detected.

## 7. Failure-mode matrix

| Failure                                  | Detection                                  | Recovery                                                                                       |
|------------------------------------------|--------------------------------------------|------------------------------------------------------------------------------------------------|
| Worker process crashes                   | `heartbeat_at < now() - 30s`               | Leader sweeper releases claimed jobs (`claimed_by=NULL, available_at=now()+backoff`).          |
| Leader crashes                           | Postgres releases advisory lock on session disconnect | Any other worker's election loop acquires the lock within `OCTO_LEADER_POLL_INTERVAL` (default 5 s). |
| Postgres primary unreachable             | psycopg connection error                   | All workers degrade to "claim what they already hold; reject new work" until reconnect. No silent data loss. |
| Job execution exceeds `max_attempts`     | Update transaction marks `finished_state='failed'` | Leader emits a structured event to the run journal; operator alert.                            |
| Duplicate enqueue (same `dispatch_id`)   | PRIMARY KEY conflict on insert             | Treated as idempotent — second enqueue returns success without re-queuing.                     |
| Worker hangs but heartbeats              | Per-job `claimed_at` aging check (leader)  | Leader marks the job as available again after `OCTO_JOB_STALL_TIMEOUT`; the original worker's eventual commit becomes a no-op via `finished_at IS NULL` guard. |

## 8. Open questions (to resolve before stage 6.3 lands)

1. **`LISTEN`/`NOTIFY` channel naming**. Per-kind, per-queue, or one
   global channel + filter client-side? Recommend per-kind to bound
   wake-up storms (e.g. one consumer pool only listens for
   `channel_inbound`).
2. **Backoff curve**. Fixed exponential (`2^attempts seconds`) vs.
   tuned-per-kind. Start with exponential capped at 5 min; revisit
   when stage 6.4 has live data.
3. **Where does `channels/message_bus.py` live after Phase 7**? The
   physical-merge owners matrix puts it under `channels/` (interfaces
   domain) but the new Postgres backend belongs to `runtime`. Plan:
   keep the interface in `channels/`, add a `runtime/dispatcher/`
   adapter that implements the interface. The two stay loosely coupled.
4. **Multi-tenant fairness**. Today there is one tenant. When tenancy
   lands, the queue needs a `tenant_id` column and a fair-scheduling
   policy. Phase 6 reserves the column (`payload->>'tenant_id'`) but
   does not implement fairness — that's an explicit Phase-6-follow-on.

## 9. What "Phase 6 done" looks like

Phase 6 is **complete** when, on the production host:

* `SELECT count(*) FROM octo_dispatch_workers WHERE heartbeat_at > now() - interval '1 minute'` returns ≥ 1 continuously.
* `SELECT count(*) FROM octo_dispatch_workers WHERE role='leader'` is **exactly 1** continuously.
* Restarting the leader via `systemctl restart octoagent-local.service`
  results in a new leader being elected within 10 s, no orphaned
  runs, and no message loss for any inbound bridge under sustained
  100-msg/min load.
* `octoagent drain --self` exits cleanly with all in-flight runs
  having reached `finished_at IS NOT NULL`.

When (and only when) all four pass continuously for 7 days under the
real workload, Stage 6.5 is considered done and the phase is closed.

## 10. Estimated effort & dependencies

* Stage 6.1: ~1 session (schema + endpoint + tests).
* Stage 6.2: ~1 session (advisory lock loop + sweeper guard).
* Stage 6.3: ~2 sessions (bus backend + per-bridge regression).
* Stage 6.4: ~2 sessions (dispatch loop + retry + backoff tuning).
* Stage 6.5: ~1 session (drain CLI + rolling restart script).

Total: **~7 sessions**. Each session is independently shippable.

> Phase 6 is **blocked** by Phase 7 only at the seam where
> `runtime/dispatcher/` would otherwise have to be inserted into a
> tree that hasn't been merged yet. If we land Stage 6.1 now (just
> the schema + registry observability), no seam conflict exists.

## 11. References

* `backend/src/agents/checkpointer/async_provider.py` — current Postgres
  client pattern (psycopg_pool, async lifecycle).
* `backend/src/harness/run_journal.py` — current `CREATE TABLE IF NOT
  EXISTS` bootstrap convention + heartbeat-stale pattern.
* `backend/src/harness/lifecycle.py::OrphanRunSweeper` — sweeper to be
  promoted to leader-only in stage 6.2.
* `backend/src/channels/message_bus.py` — interface that gets a
  Postgres backend in stage 6.3.
* `backend/src/runtime_oom_guard.py` — coordinator decision to be
  guarded by `is_leader()` in stage 6.2.
* `project_docs/docs/MODULE_OWNERS.md` — domain placement for the new
  `runtime/dispatcher/` subtree (under `runtime` domain).
* `project_docs/docs/TOPOLOGY_FREEZE_2026-05-26.md` — confirms the
  freeze does NOT prevent **subdirectory** addition under existing
  top-level dirs; only new top-level dirs are forbidden.
