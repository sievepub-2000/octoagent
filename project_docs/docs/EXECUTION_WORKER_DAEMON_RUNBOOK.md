# Execution Worker Daemon Runbook

> Last updated: 2026-04-29

This runbook starts an independent OctoAgent execution worker outside the gateway process. The gateway keeps the local inline worker as a fallback, but healthy independent workers are preferred for distributed dispatch.

## Files

- systemd unit: `deploy/octoagent-execution-worker.service`
- environment template: `deploy/system/execution-worker.env.example`
- worker entrypoint: `backend/scripts/run_execution_worker.py`

## Install

```bash
sudo install -o root -g root -m 0644 deploy/octoagent-execution-worker.service /etc/systemd/system/octoagent-execution-worker.service
sudo install -o root -g root -m 0750 -d /etc/octoagent
sudo install -o root -g root -m 0600 deploy/system/execution-worker.env.example /etc/octoagent/execution-worker.env
sudoedit /etc/octoagent/execution-worker.env
sudo systemctl daemon-reload
sudo systemctl enable --now octoagent-execution-worker
```

Generate `OCTO_EXECUTION_WORKER_TOKEN` with a long random value:

```bash
openssl rand -hex 32
```

## Health Check

```bash
curl -fsS http://127.0.0.1:19982/health
```

Expected response includes:

```json
{
  "status": "healthy",
  "node_id": "worker-local-1",
  "available_capacity": 4
}
```

## Register With Gateway

Register the worker node through the gateway. `dispatch_token` is sent by the gateway to the worker. `callback_token` is sent by the worker when posting results back to the gateway.

```bash
TOKEN="$(sudo awk -F= '/^OCTO_EXECUTION_WORKER_TOKEN=/{print $2}' /etc/octoagent/execution-worker.env)"
curl -fsS -X POST http://127.0.0.1:19880/api/execution-nodes \
  -H 'Content-Type: application/json' \
  -d "{
    \"node_id\": \"worker-local-1\",
    \"address\": \"http://127.0.0.1:19982\",
    \"capacity\": 4,
    \"tags\": [\"independent-worker\", \"systemd\"],
    \"metadata\": {
      \"dispatch_token\": \"${TOKEN}\",
      \"callback_token\": \"${TOKEN}\"
    }
  }"
```

For production, set `OCTO_OPERATOR_TOKEN` on the gateway and include `X-OctoAgent-Operator-Token` in the registration request.

## Dispatch Smoke

```bash
cd /home/sieve-pub/public-workspace/octoagent/backend
.venv/bin/python scripts/run_distributed_dispatch_smoke.py --gateway-url http://127.0.0.1:19880 --json
```

The dispatch result should target the independent worker node. If the worker is unavailable, the gateway falls back to the local inline worker.

## Operations

```bash
sudo systemctl status octoagent-execution-worker
sudo journalctl -u octoagent-execution-worker -f
sudo systemctl restart octoagent-execution-worker
```

To remove the node from the gateway registry:

```bash
curl -fsS -X DELETE http://127.0.0.1:19880/api/execution-nodes/worker-local-1 \
  -H 'X-OctoAgent-Confirmation: CONFIRM REMOVE NODE'
```

If `OCTO_OPERATOR_TOKEN` is configured on the gateway, also pass `X-OctoAgent-Operator-Token`.

## Security Notes

- Keep `/etc/octoagent/execution-worker.env` mode `0600`.
- Rotate `OCTO_EXECUTION_WORKER_TOKEN` if it appears in logs, shell history, or chat transcripts.
- Bind the worker to `127.0.0.1` unless it must be reached from another host.
- If using a remote host, put the worker behind host firewall rules and TLS-capable ingress.
- The provided systemd unit uses `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=full`, and a narrow `ReadWritePaths` list.
