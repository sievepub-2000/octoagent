# Frontend i18n Coverage

OctoAgent WebUI ships with five locales: `en-US`, `zh-CN`, `zh-TW`, `ja`, `ko`.
Default locale: `en-US`.

## Translation entry points
- `frontend/src/core/i18n/locales/types.ts` — `Translations` interface (single source of truth for keys).
- `frontend/src/core/i18n/locales/{en-US,zh-CN,zh-TW,ja,ko}.ts` — locale value bundles.
- `useI18n()` from `@/core/i18n/hooks` returns `{ t, locale, setLocale }`.

## Translated panels (commit dd186ca, 2026-05-27)
| Area | Component / Page |
|---|---|
| System Events button + drawer + empty state | `components/workspace/system-events/system-events-button.tsx` |
| System status bar runtime alerts label | `components/workspace/system-status-bar.tsx` |
| pushSystemEvent messages (the actual feed) | `core/threads/hooks.ts` |
| Permission mode selector | `components/workspace/input-box.tsx` |
| Chat thread load fallback + error events | `app/workspace/chats/[thread_id]/page.tsx` |
| Task card graph (primary/sub-agent, edit hint) | `components/workspace/task-card-graph.tsx` |
| Task card details panel | `components/workspace/task-card-details-panel.tsx` |
| RAG settings page (models, reranker, params) | `components/workspace/settings/rag-settings-page.tsx` |
| Auth register / login page | `app/auth/register/page.tsx` |
| "Show earlier messages" | `components/workspace/messages/message-list.tsx` |

## Intentional CJK retained (NOT bugs)
- `core/threads/hooks.ts` L151 (`resumeOnlyPattern`) and L159 (`completionMarkers`)
  contain Chinese regex patterns for matching user input keywords. Must remain CJK.

## Files with internal locale-dispatch dicts (already i18n-capable, untouched)
- `components/workspace/memory-schema-status-card.tsx`
- `app/workspace/evolution/page.tsx`
- `components/workspace/settings/appearance-settings-page.tsx`

## How to add a new locale key
1. Add the key to the `Translations` interface in `types.ts`.
2. Add a value in all five locale files. TypeScript will fail-compile if any are missing.
3. Reference via `const { t } = useI18n(); t.<group>.<key>`.
