# Channel Bridge Examples

This directory contains runnable and copy-pasteable samples for OctoAgent bridge-backed channels.

Files:

- `generic_webhook_bridge.py`: minimal relay that forwards normalized inbound events to OctoAgent and accepts outbound callbacks.
- `MINIMAL_PLATFORM_EXAMPLES.md`: platform-by-platform minimal wiring examples for QQ, WeChat, LINE, KakaoTalk, WhatsApp, Zalo, Facebook Messenger, Telegram, Slack, and Feishu.

Recommended use:

1. Start with `generic_webhook_bridge.py` on a local port.
2. Pick the relevant platform section from `MINIMAL_PLATFORM_EXAMPLES.md`.
3. Connect the upstream SDK or webhook handler to the relay's `/<platform>/inbound` endpoint.
4. Point OctoAgent channel `outbound_url` back to the relay's `/outbound` endpoint.

These samples are intentionally minimal. They demonstrate the OctoAgent contract and deployment wiring, not full production hardening for any upstream messaging SDK.