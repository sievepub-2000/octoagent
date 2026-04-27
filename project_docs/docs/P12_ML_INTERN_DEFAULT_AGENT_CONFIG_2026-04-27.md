# P12 ML-Intern Default Agent Configuration

Date: 2026-04-27

## Scope

OctoAgent now integrates Hugging Face `ml-intern` as the default configuration profile for all agents without vendoring or executing the upstream runtime. The upstream repository was inspected at `https://github.com/huggingface/ml-intern`, commit `ff8c636fbb905c4e9a4ba230ed599ab130707c61`.

## Mapping

- Dialogue/chat workflows map to `interactive` mode.
- Scheduled/timed/yolo/auto workflows map to `headless` mode.
- The system default agent loads `SOUL.md`, which records the interactive profile as its default behavioral baseline.
- Task workspace cards and agent metadata now carry `ml_intern_profile` and `ml_intern_defaults` for runtime and audit visibility.
- Query-engine sessions append the Hugging Face MCP server summary (`hf-mcp-server`, `https://huggingface.co/mcp?login`) if it is not already configured.

## Default Profile Values

Interactive profile:
- `yolo_mode=false`
- `confirm_cpu_jobs=true`
- `auto_file_upload=true`
- `save_sessions=true`
- `session_dataset_repo=smolagents/ml-intern-sessions`
- `max_iterations=300`
- `reasoning_effort=max`

Headless profile:
- `yolo_mode=true`
- `confirm_cpu_jobs=false`
- `auto_file_upload=true`
- `save_sessions=true`
- `session_dataset_repo=smolagents/ml-intern-sessions`
- `max_iterations=300`
- `reasoning_effort=max`

## Operational Notes

The preferred upstream model name is stored as a hint, not a hard override. OctoAgent still resolves the active model through its configured provider list so production deployments do not break when the upstream model ID is unavailable locally.

Secrets remain governed by OctoAgent policy: never echo `HF_TOKEN` or other credentials into logs, reports, or prompts. Expensive training, publishing, and CPU-heavy work stay confirmation-gated in interactive mode and auditable in headless/yolo mode.
