"""Phase 6 distributed dispatcher.

Postgres-native dispatcher for OctoAgent: durable inbound queue, worker
registry with heartbeats, leader election via ``pg_try_advisory_lock``,
at-least-once dispatch with idempotency keys, drain + graceful rolling
restart.

Disabled by default. Activate by setting ``OCTO_DISPATCHER_ENABLED=1``.
When disabled, every public function is a no-op returning empty results
— exactly the contract of :mod:`src.harness.run_journal`.

See ``project_docs/docs/PHASE6_DISTRIBUTED_DISPATCHER_RFC.md`` for the
full design rationale.
"""

from src.harness.dispatcher.drain import drain_self
from src.harness.dispatcher.leader import is_leader, leader_status
from src.harness.dispatcher.lifespan import (
    init_dispatcher,
    shutdown_dispatcher,
    start_dispatcher_task,
    stop_dispatcher_task,
)
from src.harness.dispatcher.queue import (
    ack_dispatch,
    claim_dispatch,
    dispatch_queue_stats,
    enqueue_dispatch,
    nack_dispatch,
)
from src.harness.dispatcher.schema import dispatcher_enabled, worker_id
from src.harness.dispatcher.workers import (
    list_workers,
    mark_draining,
)

__all__ = [
    "dispatcher_enabled",
    "worker_id",
    "init_dispatcher",
    "shutdown_dispatcher",
    "start_dispatcher_task",
    "stop_dispatcher_task",
    "list_workers",
    "mark_draining",
    "is_leader",
    "leader_status",
    "enqueue_dispatch",
    "claim_dispatch",
    "ack_dispatch",
    "nack_dispatch",
    "dispatch_queue_stats",
    "drain_self",
]
