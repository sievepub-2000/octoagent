# Local open-model evaluation — 2026-07-15

The current primary model is `ornith-1.0-35b-nvfp4`. This note records the
Hugging Face candidates that fit the 100B limit and the existing OpenAI-
compatible/llama.cpp deployment boundary. It is intentionally an evaluation
record, not an automatic production model switch.

## Candidates

| Model | Size | Strength | Deployment fit | Decision |
|---|---:|---|---|---|
| `Qwen/Qwen3.6-27B` | 27B dense | General reasoning, vision, agentic coding, tool use; native 262K context | Official `ggml-org/Qwen3.6-27B-GGUF` exists and the installed llama.cpp tree contains `qwen35` support | Best first A/B candidate |
| `Qwen/Qwen3.6-35B-A3B` | 35B total / 3B active | Agentic coding and multimodal execution | FP8 is official; GGUF is currently community-provided, so provenance and quantization need checking | Second candidate |
| `Qwen/Qwen3-Next-80B-A3B-Thinking` | 80B total / 3B active | Strong reasoning/long-context efficiency; native 262K | Official GGUF and llama.cpp instructions; multi-part Q4 model will use substantially more storage | Quality ceiling candidate |
| `Qwen/Qwen3-Coder-30B-A3B-Instruct` | 30.5B total / 3.3B active | Repository-scale and agentic coding, native 262K, designed function-call format | Official model card supports llama.cpp quantizations, but it is non-thinking only | Execution-specialist fallback |
| `mistralai/Devstral-Small-2-24B-Instruct-2512` | 24B | Coding/agent workflows | GGUF/FP8 availability should be checked before deployment | Alternative coding baseline |
| `mistralai/Magistral-Small-2506` | 24B | Long reasoning, multilingual, Apache-2.0 | Official llama.cpp GGUF; 128K context | Reasoning baseline |

## Recommendation

Run a controlled A/B test in this order:

1. `Qwen3.6-27B` Q4 or Q5 GGUF — best balance of reasoning, vision,
   tool-call support, and local deployment risk.
2. `Qwen3.6-35B-A3B` Q4_K_M — likely the closest drop-in MoE upgrade if the
   chosen GGUF is verified and the model server accepts the chat template.
3. `Qwen3-Next-80B-A3B-Thinking` Q4_K_M — test only after measuring memory and
   latency; it is the strongest reasoning candidate but has a much larger
   total weight footprint.

The existing service must remain on Ornith until each candidate passes the
same prompt suite: Chinese instruction following, multi-step planning,
filesystem/tool calls, error recovery, vision, JSON validity, 128K context,
tokens/sec, first-token latency, and peak GPU/RAM. A model card's benchmark is
not a substitute for this local A/B test.

