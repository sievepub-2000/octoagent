# Settings and configuration refactor — 20260714

## Outcome

OctoAgent now uses one conventional Settings panel for user configuration.
Runtime execution concepts remain internal; users configure models and reusable
capabilities without managing implementation-level workflows or role packs.

## Public settings

| Group | Sections | Purpose |
| --- | --- | --- |
| General | General, Appearance | Runtime health and local presentation |
| AI & capabilities | Models, Skills, MCP servers, Plugins, Hooks | Model providers and reusable capabilities |
| System | Memory, Permissions, Notifications, Update, About | Runtime policy and maintenance |

## Model contract

- Supports OpenAI-compatible, Anthropic Messages, Google GenAI, DeepSeek
  Reasoner, local no-auth, and custom LangChain adapters.
- Stores only environment-variable references such as `$OPENAI_API_KEY`.
- Supports create, edit, delete, default selection, capability metadata, and a
  real 60-second-bounded connection test with measured latency.
- Default production configuration contains only the working Ornith model.

## Extension contract

- Skills retain create/edit/delete/enable controls.
- MCP supports stdio, HTTP, and SSE; HTTP headers and environment entries use
  one `KEY=value` item per line.
- Plugins and hooks remain available as reusable capability mechanisms.
- No MCP server is enabled by default; users explicitly grant each integration.

## Removed debt

- 57 repository system-agent profiles.
- Six overlapping built-in subagent roles and implicit Agency role injection.
- Four unavailable example cloud models, embedded bootstrap fallback, and
  automatic OpenRouter/NVIDIA fallback pools.
- Model-provider OAuth/import subsystem and 16 template cards.
- Evolution and Tools Hub configuration pages.
- Six default high-privilege MCP connections and a machine-specific preset.

## Verification evidence

- Backend: 623 tests passed; focused Ruff checks passed.
- Frontend: ESLint, TypeScript, and production build passed locally and on the
  production host.
- Runtime: gateway and PostgreSQL health passed; model API returned one default
  Ornith model; MCP API returned an empty map.
- Browser: settings button and section navigation passed; Models, Skills, and
  MCP rendered successfully; browser console contained no warnings or errors.
- Live model test: Ornith returned `OK` through the configured adapter.
