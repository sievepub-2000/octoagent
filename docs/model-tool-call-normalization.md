# Model Tool Call Normalization

Updated: 2026-08-02

OctoAgent routes provider model responses through the model semantic layer before LangGraph decides whether to execute tools. This layer is intentionally provider-wide: local llama.cpp models, OpenAI-compatible OpenRouter models, Gemma-family models, Google native models, NVIDIA models, and fallback candidates should all share the same normalization behavior instead of relying on per-model patches.

## Responsibility

`backend/src/models/semantics.py` exposes one `ToolCallProtocolAdapter` boundary. Model providers, Harness, middleware, and LangGraph exchange only the canonical LangChain call shape:

```text
ToolCall = {name: string, args: object, id: string, type: "tool_call"}
```

The adapter negotiates provider-native request binding and normalizes assistant responses before LangGraph decides whether to execute a tool. Native structured output is always preferred. Text parsing is a compatibility fallback for local or older models whose inference server leaks template syntax into `content`.

Supported forms include:

- Provider-native `additional_kwargs.tool_calls` and `function_call` payloads.
- Content blocks such as `tool_use`, `tool_call`, or `function_call`.
- OpenAI Responses `function_call` blocks using `call_id`.
- llama.cpp style `<|tool_call:name{...}<tool_call|>` responses.
- Hermes/Qwen XML-ish `<tool_call><function=...>` responses.
- Tagged or fenced JSON tool payloads.
- Bare JSON tool payloads returned as the final part of assistant text, for example `{"tool":"bash","arguments":{...}}`.
- Tool-code style calls such as `bash(command="...")` when the whole response is tool code or explicitly tagged as tool code.

## Safety Rules

Text fallback is the riskiest form because similar text can appear in normal reports. Every fallback parser now accepts only names present in the currently bound tool schema. This prevents an unbound or hallucinated XML/JSON call from entering the executor. Provider-native structured calls remain authoritative and LangGraph validates them against the same bound registry.

Fallback model paths can receive tools through provider invocation kwargs rather than `SemanticChatModel.bind_tools()`. The semantic layer therefore extracts allowed tool names from both the bound LangChain tools and provider-compatible `tools` schemas.

## Design references

- [llama.cpp function calling](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md): native template handlers first, generic fallback second, with OpenAI-compatible API output.
- [vLLM Hermes parser](https://github.com/vllm-project/vllm/blob/main/vllm/tool_parsers/hermes_tool_parser.py): format-specific parsing is isolated from execution and converted to one server contract.
- [LangChain OpenAI adapter](https://github.com/langchain-ai/langchain/blob/master/libs/partners/openai/langchain_openai/chat_models/base.py): native provider chunks are converted to canonical tool-call chunks.
- [LangChain Anthropic adapter](https://github.com/langchain-ai/langchain/blob/master/libs/partners/anthropic/langchain_anthropic/chat_models.py): Anthropic `tool_use` blocks are exposed through the same LangChain `ToolCall` type.
- [Google Gen AI SDK](https://github.com/googleapis/python-genai): Gemini function-call parts keep provider-native transport while exposing name and argument objects to the caller.

The implementation deliberately does not copy those projects' provider parsers wholesale. OctoAgent delegates native transport to the maintained LangChain provider packages and owns only the small cross-provider compatibility boundary required by local OpenAI-compatible servers.

## Tool surface loading

The protocol adapter is independent from tool discovery. The lead agent binds the seven Harness core tools on every tool-capable turn, then adds only intent-relevant configured groups (`web`, file, shell) and explicitly requested MCP tools. `list_capabilities` remains the discovery entry point. This removes the previous behavior that serialized every configured and MCP schema into every request.

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
