# Channel Bridge Deployment Guide

This guide documents the production-facing contract for OctoAgent channel integrations and the deployment pattern for bridge-backed messaging platforms.

## 1. Scope

OctoAgent currently supports two channel integration modes:

| Mode | Channels | Transport | Notes |
| --- | --- | --- | --- |
| Native | Feishu/Lark, Slack, Telegram | websocket, socket mode, long polling | Implemented directly in the backend |
| External bridge | QQ, WeChat, LINE, KakaoTalk, WhatsApp, Zalo, Facebook Messenger | webhook bridge | OctoAgent receives normalized events from an external bridge process |

Telegram remains natively supported. If you need a uniform connector fleet, you can still put Telegram behind the same bridge contract.

## 2. Runtime topology

The bridge-backed topology is:

upstream platform SDK or bot process -> bridge process -> OctoAgent ingest API -> ChannelManager -> LangGraph runtime

Outbound replies flow back as:

LangGraph runtime -> ChannelManager -> ExternalBridgeChannel -> bridge outbound webhook -> upstream platform SDK

## 3. OctoAgent ingress contract

Bridge-backed channels send normalized inbound payloads to:

- `POST /api/channels/<channel_name>/ingest`

Required header:

- `X-OctoAgent-Bridge-Token: <shared_secret>`

Normalized request body:

```json
{
  "chat_id": "room-001",
  "user_id": "user-123",
  "text": "hello from mobile",
  "msg_type": "chat",
  "thread_ts": "thread-optional",
  "topic_id": "topic-optional",
  "metadata": {
    "platform_user_name": "demo-user",
    "raw_event_id": "evt-001"
  },
  "files": []
}
```

Field rules:

- `chat_id`: platform conversation identifier. Required.
- `user_id`: platform sender identifier. Required.
- `text`: message body. May be empty only when `files` is present.
- `msg_type`: `chat`, `command`, or `event`.
- `thread_ts`: optional thread or reply identifier.
- `topic_id`: optional topic identifier. If omitted, OctoAgent falls back to `thread_ts` or `chat_id`.
- `metadata`: arbitrary JSON object copied into the inbound message metadata.
- `files`: optional list of platform-side file descriptors. OctoAgent accepts the list structurally but does not ingest binary data through this contract.

Success response:

```json
{
  "accepted": true,
  "message": "Inbound bridge payload accepted for wechat"
}
```

## 4. Outbound contract

Bridge-backed channels optionally receive outbound replies at the configured `outbound_url`.

Required header:

- `X-OctoAgent-Bridge-Token: <shared_secret>`

Outbound message payload:

```json
{
  "event": "outbound_message",
  "platform": "wechat",
  "platform_label": "WeChat",
  "chat_id": "room-001",
  "thread_ts": null,
  "thread_id": "7a5c7d31-...",
  "text": "assistant reply",
  "is_final": true,
  "metadata": {
    "source": "langgraph"
  }
}
```

Outbound attachment payload:

```json
{
  "event": "outbound_attachment",
  "platform": "wechat",
  "platform_label": "WeChat",
  "chat_id": "room-001",
  "thread_ts": null,
  "thread_id": "7a5c7d31-...",
  "filename": "report.md",
  "mime_type": "text/markdown",
  "size": 1024,
  "is_image": false,
  "virtual_path": "/mnt/user-data/outputs/report.md"
}
```

Current boundary:

- attachments are metadata-only notifications.
- the bridge must decide whether to fetch, transform, upload, or ignore the referenced file.
- OctoAgent does not stream binary file content to the bridge yet.

## 5. OctoAgent configuration

Example `config.yaml` fragment:

```yaml
channels:
  langgraph_url: http://127.0.0.1:19884
  gateway_url: http://127.0.0.1:19882

  session:
    assistant_id: lead_agent
    config:
      recursion_limit: 100
    context:
      thinking_enabled: true
      is_plan_mode: false
      subagent_enabled: false

  wechat:
    enabled: true
    shared_secret: $WECHAT_BRIDGE_SHARED_SECRET
    outbound_url: http://127.0.0.1:30102/outbound

  whatsapp:
    enabled: true
    shared_secret: $WHATSAPP_BRIDGE_SHARED_SECRET
    outbound_url: http://127.0.0.1:30105/outbound

  facebook_messenger:
    enabled: true
    shared_secret: $FACEBOOK_MESSENGER_BRIDGE_SHARED_SECRET
    outbound_url: http://127.0.0.1:30107/outbound
    session:
      assistant_id: mobile_agent
      context:
        thinking_enabled: false
      users:
        "vip-user":
          assistant_id: vip_agent
          config:
            recursion_limit: 150
          context:
            thinking_enabled: true
            subagent_enabled: true
```

## 6. Recommended upstream projects

| Channel | Upstream project | URL | Expected bridge role |
| --- | --- | --- | --- |
| QQ | mamoe/mirai | https://github.com/mamoe/mirai | Bot event consumer and outbound sender |
| WeChat | wechaty/wechaty | https://github.com/wechaty/wechaty | Personal or enterprise WeChat event bridge |
| LINE | line/line-bot-sdk-python | https://github.com/line/line-bot-sdk-python | Webhook receiver and reply client |
| KakaoTalk | storycraft/node-kakao | https://github.com/storycraft/node-kakao | Kakao chat event session |
| WhatsApp | open-wa/wa-automate-nodejs | https://github.com/open-wa/wa-automate-nodejs | WhatsApp event and outbound bridge |
| Zalo | zaloplatform/zalo-php-sdk | https://github.com/zaloplatform/zalo-php-sdk | Official account webhook bridge |
| Facebook Messenger | fbsamples/messenger-platform-samples | https://github.com/fbsamples/messenger-platform-samples | Messenger webhook and sender |
| Telegram | Native backend support | built-in | Use native config unless uniform bridge ops is required |

## 7. Minimal deployment flow

1. Enable the target channel in `config.yaml` with `shared_secret` and `outbound_url`.
2. Start OctoAgent and confirm `GET /api/channels` reports the channel as `configured`.
3. Deploy a bridge process close to the upstream platform SDK.
4. Normalize upstream events into the OctoAgent ingress payload.
5. Verify the bridge sends `X-OctoAgent-Bridge-Token` on both inbound and outbound webhook calls.
6. Confirm the bridge listens on the `outbound_url` you configured.
7. Send a test message and verify:
   - ingest returns `accepted: true`
   - the platform user gets an outbound reply
   - `GET /api/channels` shows `outbound_configured: true`

## 8. Security checklist

- Use a distinct `shared_secret` per channel.
- Keep bridge listeners on localhost or behind a private ingress whenever possible.
- Reject inbound requests with invalid `X-OctoAgent-Bridge-Token`.
- If a bridge exposes public webhooks, terminate TLS before forwarding to the local relay.
- Do not blindly mirror raw platform payloads into OctoAgent metadata if they contain tokens or PII.
- Restrict `allowed_users` when running a channel for a bounded operator group.

## 9. Verification checklist

- `GET /api/channels` shows the channel enabled, configured, and running.
- Posting a normalized payload to `/api/channels/<name>/ingest` returns HTTP 200.
- An end-to-end platform message creates a LangGraph thread and produces an outbound reply.
- The bridge logs outbound `outbound_message` events.
- If attachments are produced, the bridge sees `outbound_attachment` metadata and handles it explicitly.

## 10. Sample assets

Use the repository sample assets here:

- guide index: [project_docs/examples/channel_bridges/README.md](../examples/channel_bridges/README.md)
- generic relay: [project_docs/examples/channel_bridges/generic_webhook_bridge.py](../examples/channel_bridges/generic_webhook_bridge.py)
- platform examples: [project_docs/examples/channel_bridges/MINIMAL_PLATFORM_EXAMPLES.md](../examples/channel_bridges/MINIMAL_PLATFORM_EXAMPLES.md)