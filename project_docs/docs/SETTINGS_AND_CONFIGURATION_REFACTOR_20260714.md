# Settings and configuration refactor — 20260714

## Outcome

OctoAgent now uses one conventional Settings panel for user configuration.
Runtime execution concepts remain internal; users configure models and reusable
capabilities without managing implementation-level workflows or role packs.

## Public settings

| Group | Sections | Purpose |
| --- | --- | --- |
| General | General, Appearance | Runtime health and local presentation |
| AI & capabilities | Models, Skills, MCP servers, Plugins, Hooks, Tools Hub | Model providers, reusable capabilities, live status, and usage guidance |
| System | Memory, Permissions, Notifications, Update, About | Runtime policy and maintenance |

## Model contract

- Supports OpenAI-compatible, Anthropic Messages, Google GenAI, DeepSeek
  Reasoner, local no-auth, and custom LangChain adapters.
- Accepts a direct API key or an existing reference such as `$OPENAI_API_KEY`.
  Direct keys are stored in the gitignored project environment file with mode
  0600 and only a generated reference is written to model YAML.
- Supports create, edit, delete, default selection, capability metadata, and a
  real 60-second-bounded connection test with measured latency.
- The chat composer reads the same live model API as Settings, so create,
  update, default selection, and removal are reflected in the model picker.
- Production contains three connection-tested models: Ornith 1.0 35B NVFP4,
  Google Gemini 3.5 Flash, and NVIDIA Nemotron 3 Super.

## Extension contract

- Skills retain create/edit/delete/enable controls.
- MCP supports stdio, HTTP, and SSE; HTTP headers and environment entries use
  one `KEY=value` item per line.
- Plugins and hooks remain available as reusable capability mechanisms.
- Tools Hub aggregates the live registries and supplies per-capability usage
  guidance. Frontend mutations refresh the hub and backend mutations regenerate
  `.github/copilot-instructions.md`.
- The six existing operator-managed MCP services and their original permission
  scopes are preserved.

## Removed debt

- 57 repository system-agent profiles.
- Six overlapping built-in subagent roles and implicit Agency role injection.
- Three upstream-unusable model entries (zero quota, removed model ID, or
  region block), embedded bootstrap fallback, and automatic fallback pools.
- Model-provider OAuth/import subsystem and 16 template cards.
- Evolution/workflow-builder configuration pages and a machine-specific preset.

## Verification evidence

- Backend: model-secret and plugin regression tests passed; capability
  create/load/delete lifecycle tests passed and left no temporary records.
- Frontend: ESLint, TypeScript, and production build passed locally and on the
  production host.
- Runtime: gateway health passed; Skills loaded 50 entries, Plugins loaded 16,
  Hooks loaded 2, and MCP smoke passed 6/6.
- Live model tests: Ornith, Gemini 3.5 Flash, and NVIDIA Nemotron returned
  successful responses through their configured adapters.
