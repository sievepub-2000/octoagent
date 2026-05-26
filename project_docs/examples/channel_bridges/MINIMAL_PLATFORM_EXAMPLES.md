# Minimal Platform Examples

All bridge-backed examples assume the generic relay is running locally and OctoAgent is available at `http://127.0.0.1:19800`.

Common relay start command:

```bash
BRIDGE_SHARED_SECRET=replace-me \
LISTEN_PORT=19814 \
python3 project_docs/examples/channel_bridges/generic_webhook_bridge.py
```

Common normalized payload shape:

```json
{
  "chat_id": "conversation-id",
  "user_id": "sender-id",
  "text": "message body",
  "msg_type": "chat",
  "thread_ts": null,
  "topic_id": null,
  "metadata": {
    "platform_user_name": "display name",
    "raw_event_id": "provider-event-id"
  },
  "files": []
}
```

## QQ via mirai

- Upstream: `mamoe/mirai`
- OctoAgent channel: `qq`
- Relay inbound URL: `http://127.0.0.1:19814/qq/inbound`

Minimal normalized event:

```json
{
  "chat_id": "qq-group-9527",
  "user_id": "qq-user-10001",
  "text": "你好，OctoAgent",
  "metadata": {
    "source": "mirai",
    "group_name": "ops-room"
  }
}
```

## WeChat via wechaty

- Upstream: `wechaty/wechaty`
- OctoAgent channel: `wechat`
- Relay inbound URL: `http://127.0.0.1:19814/wechat/inbound`

Minimal normalized event:

```json
{
  "chat_id": "wechat-room-001",
  "user_id": "wechat-user-001",
  "text": "请总结今天的任务状态",
  "metadata": {
    "source": "wechaty",
    "room_topic": "delivery-team"
  }
}
```

## LINE via line-bot-sdk-python

- Upstream: `line/line-bot-sdk-python`
- OctoAgent channel: `line`
- Relay inbound URL: `http://127.0.0.1:19814/line/inbound`

Minimal normalized event:

```json
{
  "chat_id": "line-group-123",
  "user_id": "line-user-456",
  "text": "show current deployment health",
  "metadata": {
    "source": "line-webhook",
    "reply_token": "provider-managed"
  }
}
```

## KakaoTalk via node-kakao

- Upstream: `storycraft/node-kakao`
- OctoAgent channel: `kakaotalk`
- Relay inbound URL: `http://127.0.0.1:19814/kakaotalk/inbound`

Minimal normalized event:

```json
{
  "chat_id": "kakao-room-100",
  "user_id": "kakao-user-200",
  "text": "run a quick release checklist",
  "metadata": {
    "source": "node-kakao",
    "channel_type": "open_chat"
  }
}
```

## WhatsApp via open-wa

- Upstream: `open-wa/wa-automate-nodejs`
- OctoAgent channel: `whatsapp`
- Relay inbound URL: `http://127.0.0.1:19814/whatsapp/inbound`

Minimal normalized event:

```json
{
  "chat_id": "whatsapp-chat-001",
  "user_id": "whatsapp-user-001",
  "text": "send me the latest runtime summary",
  "metadata": {
    "source": "open-wa",
    "device": "mobile"
  }
}
```

## Zalo via zalo-php-sdk

- Upstream: `zaloplatform/zalo-php-sdk`
- OctoAgent channel: `zalo`
- Relay inbound URL: `http://127.0.0.1:19814/zalo/inbound`

Minimal normalized event:

```json
{
  "chat_id": "zalo-conversation-01",
  "user_id": "zalo-user-09",
  "text": "kiểm tra trạng thái workflow hiện tại",
  "metadata": {
    "source": "zalo-oa",
    "oa_id": "official-account"
  }
}
```

## Facebook Messenger via messenger-platform-samples

- Upstream: `fbsamples/messenger-platform-samples`
- OctoAgent channel: `facebook_messenger`
- Relay inbound URL: `http://127.0.0.1:19814/facebook_messenger/inbound`

Minimal normalized event:

```json
{
  "chat_id": "messenger-thread-01",
  "user_id": "messenger-user-08",
  "text": "what changed in the latest deployment",
  "metadata": {
    "source": "messenger-webhook",
    "page_id": "page-001"
  }
}
```

## Telegram native minimal config

Telegram is already supported natively by OctoAgent. Minimal native config:

```yaml
channels:
  telegram:
    enabled: true
    bot_token: $TELEGRAM_BOT_TOKEN
    allowed_users: []
```

If you still want a uniform relay fleet, forward normalized Telegram webhook or polling events to `http://127.0.0.1:19814/telegram/inbound` using the same payload shape.

## Slack native minimal config

```yaml
channels:
  slack:
    enabled: true
    bot_token: $SLACK_BOT_TOKEN
    app_token: $SLACK_APP_TOKEN
    allowed_users: []
```

## Feishu native minimal config

```yaml
channels:
  feishu:
    enabled: true
    app_id: $FEISHU_APP_ID
    app_secret: $FEISHU_APP_SECRET
```

## Outbound callback behavior

All bridge-backed channels should expose:

- `POST /outbound`

OctoAgent sends `outbound_message` and `outbound_attachment` events there. The generic relay prints them to stdout. A production bridge should translate them into the provider-specific send API.

## Quick verification

With the relay running, you can simulate any bridge-backed platform directly:

```bash
curl -X POST http://127.0.0.1:19814/wechat/inbound \
  -H 'Content-Type: application/json' \
  -d '{
    "chat_id": "wechat-room-001",
    "user_id": "wechat-user-001",
    "text": "hello from relay",
    "metadata": {"source": "manual-smoke"}
  }'
```

If the channel is enabled and configured in OctoAgent, the relay should return the `accepted` response from `/api/channels/wechat/ingest`.
