# P24 Autonomous Agent Capability Enhancement (2026-05-16)

## Scope

This pass turns the self-evaluation recommendations into a practical OctoAgent
runtime enhancement without adding another daemon or duplicating existing
platform surfaces. The implementation focuses on capabilities that improve
long-running autonomous work immediately:

- host/runtime health inspection
- masked security and secret scanning
- configuration drift snapshots and checks
- local media metadata probing for image/audio/video/3D entry points
- documentation and tests that keep these tools stable for all model providers

## Existing Capability Baseline

OctoAgent already has several core agent-platform features:

- code and shell execution through `bash`, sandbox file tools, and `codex_cli`
- image processing through `process_image`
- document conversion through `convert_document`
- web acquisition through search/fetch/read-page/Scrapling tools
- scheduled and event-driven work through cron and hook/channel infrastructure
- memory, self-evolution, subagent, team, task, and workflow tools
- router contracts, runtime permissions, context compaction, and continuation
  middleware covered by tests

The gap was not a lack of individual tools, but the absence of a single compact
operations layer that an agent can call during autonomous work to understand
host state, detect unsafe output, and compare configuration drift before and
after long tasks.

## New Built-In Tools

`backend/src/tools/builtins/system_ops_tools.py` adds five tools:

| Tool | Purpose | Permission scope |
| --- | --- | --- |
| `runtime_health_report` | Reports Python/runtime version, CPU, memory, disk, git status, systemd state, and matching OctoAgent processes. | `system` |
| `security_audit_scan` | Scans OctoAgent-managed files for common secret/token/private-key patterns and only returns masked samples. | `directory` |
| `config_drift_snapshot` | Creates SHA-256 snapshots for config and documentation files. | `directory` |
| `config_drift_check` | Compares a previous snapshot with current files and reports added/removed/changed paths. | `directory` |
| `media_probe` | Reads local media metadata; supports image dimensions through Pillow, optional ffprobe for audio/video, and simple OBJ 3D counts. | `directory` |

The tools are registered in the built-in catalog so they are available to every
model that can call tools, including OpenAI-compatible, Gemini-compatible, and
open-source models after the existing tool-call normalization layer.

## Mapping To The Evaluation Recommendations

### 1. Advanced Code Execution And Sandbox

Existing execution remains centered on the sandbox file tools, `bash`, and
`codex_cli`. The new health tool adds the missing operational visibility:
process list, systemd state, disk pressure, memory pressure, and git cleanliness.
This gives long-running agents a cheap way to self-check progress instead of
blindly retrying commands.

Recommended next step: add a container profile registry that describes allowed
Docker images, resource limits, mount policy, and cleanup policy. Do not wire
arbitrary Docker execution directly into the model path without this policy
layer.

### 2. Advanced Multimodal Tools

OctoAgent already has image processing and document conversion. `media_probe`
adds a low-cost media intake layer:

- image width/height/mode/frame count through Pillow
- optional audio/video stream metadata when `ffprobe` is installed
- 3D file format hints and OBJ vertex/face counts

Recommended next step: add separate heavy workers for STT/TTS/video keyframes
and image inpainting/upscaling so the chat runtime stays light while long media
jobs can run asynchronously.

### 3. Proactive Sensing And Monitoring

Cron and hooks already exist. The new drift and health tools make them useful
for autonomous monitoring workflows:

- scheduled health checks can call `runtime_health_report`
- scheduled repo checks can call `config_drift_snapshot`
- event-triggered repair workflows can compare snapshots with
  `config_drift_check`

Recommended next step: create canned cron workflow templates for daily health,
weekly security scan, and release drift audit.

### 4. Collaboration And Multi-Agent Communication

Task, team, memory, and subagent surfaces already exist. This pass does not add a
new message queue because the current architecture already has workflow state,
runtime memory, hooks, and channel bridges. The new tools improve collaboration
by making shared runtime state inspectable and auditable.

Recommended next step: promote shared memory policies into a versioned contract
so multiple agents can agree on what is task state, what is durable memory, and
what is temporary scratch state.

### 5. Security Audit And Self-Healing

`security_audit_scan` and `config_drift_check` provide the first compact
self-audit primitives:

- common secrets are detected but not printed raw
- private-key headers are detected
- config/documentation drift is measurable
- health reports include service and repository status

Recommended next step: wire these tools into the execution-review middleware so
long-running tasks run a lightweight checkpoint after compaction, after timeout,
and before final completion.

## Verification

Added backend tests:

- `test_security_audit_scan_masks_secret_values`
- `test_config_drift_check_detects_changed_file`
- `test_media_probe_reads_image_metadata`
- `test_runtime_health_report_returns_expected_sections`

These tests verify the new tools are callable through LangChain tool invocation,
mask secrets correctly, detect drift, inspect media, and return operational
health sections.

## System Recommendation

The current best path is to keep OctoAgent's runtime small and policy-driven:

- keep heavyweight execution/media workers behind explicit tool contracts
- keep safety checks as observable reports rather than hard stops except for
  system-level corruption
- run compaction-time review with health, task state, memory, and drift signals
- let models continue long tasks with soft self-review checkpoints rather than
  arbitrary tool-count or token-count stops
- keep local model services outside the OctoAgent repo and integrate them only
  through provider contracts

This keeps the system closer to a high-performance, low-resource autonomous
agent platform while preserving a clear boundary between OctoAgent code,
runtime state, and optional local infrastructure.
