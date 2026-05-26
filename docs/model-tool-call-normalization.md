# Model Tool Call Normalization

Updated: 2026-05-20

OctoAgent routes provider model responses through the model semantic layer before LangGraph decides whether to execute tools. This layer is intentionally provider-wide: local llama.cpp models, OpenAI-compatible OpenRouter models, Gemma-family models, Google native models, NVIDIA models, and fallback candidates should all share the same normalization behavior instead of relying on per-model patches.

## Responsibility

`backend/src/models/semantics.py` normalizes assistant responses into LangChain `AIMessage.tool_calls` when a model returns a tool request in a non-native format.

Supported forms include:

- Provider-native `additional_kwargs.tool_calls` and `function_call` payloads.
- Content blocks such as `tool_use`, `tool_call`, or `function_call`.
- llama.cpp style `<|tool_call:name{...}<tool_call|>` responses.
- XML-ish `<tool_call><function=...>` responses.
- Tagged or fenced JSON tool payloads.
- Bare JSON tool payloads returned as the final part of assistant text, for example `{"tool":"bash","arguments":{...}}`.
- Tool-code style calls such as `bash(command="...")` when the whole response is tool code or explicitly tagged as tool code.

## Safety Rules

Bare trailing JSON is the riskiest form because it can also appear in normal reports. For that form, OctoAgent only converts the payload when it has a tool-call shape and the requested tool name is present in the currently bound tool schema. This prevents a report like `{"tool":"bash","status":"passed"}` from becoming an accidental tool execution.

Fallback model paths can receive tools through provider invocation kwargs rather than `SemanticChatModel.bind_tools()`. The semantic layer therefore extracts allowed tool names from both the bound LangChain tools and provider-compatible `tools` schemas.

## Regression Coverage

The semantic tests in `backend/tests/models/test_semantics_system_messages.py` cover:

- Runtime system-message ordering for models that require the system message first.
- Trailing bare JSON tool requests with text before the payload.
- Whole-message JSON tool requests.
- Unknown tool names being rejected during trailing JSON normalization.
- Report JSON that lacks argument shape staying as normal text.
- Provider `tools` schemas being used for fallback-path tool-name filtering.

When changing model adapters, fallback handling, streaming, or tool schemas, run at least:

```bash
backend/.venv/bin/python -m pytest backend/tests/models/test_semantics_system_messages.py
```

For runtime changes, also run a live WebUI smoke test that asks the agent to call a simple system tool and confirms the resulting history contains an `AIMessage.tool_calls` entry followed by a `ToolMessage`.