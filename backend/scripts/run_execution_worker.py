"""Run an independent distributed execution worker daemon."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class WorkerDispatchRequest(BaseModel):
    dispatch_id: str
    lease_id: str = ""
    task_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    callback_url: str | None = None
    callback_token: str | None = None


class WorkerDispatchResponse(BaseModel):
    accepted: bool = True
    worker_node_id: str
    dispatch_id: str
    lease_id: str = ""
    task_id: str
    result: dict[str, Any] = Field(default_factory=dict)


def create_app(*, node_id: str, token: str, capacity: int, callback_retries: int) -> FastAPI:
    app = FastAPI(title=f"OctoAgent Execution Worker {node_id}")
    active_leases: set[str] = set()
    lock = asyncio.Lock()

    async def _post_callback(request: WorkerDispatchRequest, result: dict[str, Any]) -> None:
        if not request.callback_url:
            return
        headers = {}
        if request.callback_token:
            headers["X-Execution-Node-Token"] = request.callback_token
        payload = {
            "dispatch_id": request.dispatch_id,
            "lease_id": request.lease_id,
            "node_id": node_id,
            "status": "completed",
            "result": result,
        }
        for attempt in range(1, max(1, callback_retries) + 1):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.post(request.callback_url, json=payload, headers=headers)
                response.raise_for_status()
                return
            except Exception:
                if attempt >= callback_retries:
                    return
                await asyncio.sleep(min(5, attempt))

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "healthy",
            "node_id": node_id,
            "capacity": capacity,
            "active_leases": len(active_leases),
            "available_capacity": max(0, capacity - len(active_leases)),
        }

    @app.post("/api/execution-nodes/worker/dispatch", response_model=WorkerDispatchResponse)
    async def dispatch(
        request: WorkerDispatchRequest,
        x_execution_node_token: str | None = Header(default=None, alias="X-Execution-Node-Token"),
    ) -> WorkerDispatchResponse:
        if token and x_execution_node_token != token:
            raise HTTPException(status_code=403, detail="Invalid execution node token")
        async with lock:
            if len(active_leases) >= capacity:
                raise HTTPException(status_code=429, detail="Worker capacity exhausted")
            lease = request.lease_id or request.dispatch_id
            active_leases.add(lease)
        try:
            started = time.time()
            result = {
                "status": "completed",
                "worker_node_id": node_id,
                "task_id": request.task_id,
                "lease_id": request.lease_id,
                "echo": request.payload,
                "elapsed_ms": round((time.time() - started) * 1000, 3),
            }
            await _post_callback(request, result)
            return WorkerDispatchResponse(
                worker_node_id=node_id,
                dispatch_id=request.dispatch_id,
                lease_id=request.lease_id,
                task_id=request.task_id,
                result=result,
            )
        finally:
            async with lock:
                active_leases.discard(request.lease_id or request.dispatch_id)

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19982)
    parser.add_argument("--node-id", default=os.getenv("OCTO_EXECUTION_WORKER_NODE_ID", "worker-local"))
    parser.add_argument("--token", default=os.getenv("OCTO_EXECUTION_WORKER_TOKEN", ""))
    parser.add_argument("--capacity", type=int, default=int(os.getenv("OCTO_EXECUTION_WORKER_CAPACITY", "4")))
    parser.add_argument("--callback-retries", type=int, default=int(os.getenv("OCTO_EXECUTION_WORKER_CALLBACK_RETRIES", "3")))
    args = parser.parse_args()
    app = create_app(
        node_id=args.node_id,
        token=args.token,
        capacity=max(1, args.capacity),
        callback_retries=max(1, args.callback_retries),
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
