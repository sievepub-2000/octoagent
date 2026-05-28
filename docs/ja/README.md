# OctoAgent 日本語ガイド

OctoAgent は、業務運用、システム管理、調査、オフィス自動化、コード作業を対象にしたホワイトボックス型のマルチエージェント基盤です。推論の流れ、ツール呼び出し、生成物、ログを WebUI で確認できるため、ブラックボックスではなく監査可能な形で AI エージェントを運用できます。

## できること

- Web 調査、文書処理、RAG、コード修正、DB 操作、Docker/SSH/Git などのツール実行。
- LangGraph ベースのエージェント実行と、Next.js WebUI による可視化。
- MCP サーバー、システムツール、サブエージェント、評価スイートを組み合わせた拡張。
- 自分の PC、社内サーバー、クラウド VM 上でのローカル優先運用。

## 推奨インストール方式

Linux、Windows、macOS のすべてで Docker Compose 方式を推奨します。ホスト側に Python、Node.js、pnpm、nginx、PostgreSQL、Redis を個別に入れる必要はありません。

### Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.sh | bash
```

インストール先を指定する場合:

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.sh | bash -s -- --prefix "$HOME/octoagent"
```

### Windows PowerShell

```powershell
iwr https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.ps1 -UseBasicParsing | iex
```

インストール先を指定する場合:

```powershell
$env:OCTOAGENT_HOME="$HOME\octoagent"
iwr https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.ps1 -UseBasicParsing | iex
```

起動後、ブラウザで以下を開きます。

```text
http://127.0.0.1:19800
```

## 手動操作

既存のチェックアウトから起動する場合:

```bash
git clone https://github.com/sievepub-2000/octoagent.git
cd octoagent
./scripts/install-docker.sh --prefix "$PWD"
```

再起動または更新:

```bash
docker compose --env-file .env.docker -f compose.yaml up -d --build --remove-orphans
```

ログ確認:

```bash
docker compose --env-file .env.docker -f compose.yaml logs -f nginx gateway langgraph frontend
```

停止:

```bash
docker compose --env-file .env.docker -f compose.yaml down
```

## ベースイメージのミラー

Docker Hub に接続しにくい環境では、`compose.yaml` を変更せず `.env.docker` でイメージ名を上書きできます。

```dotenv
OCTOAGENT_POSTGRES_IMAGE=mirror.example.com/library/postgres:16-alpine
OCTOAGENT_REDIS_IMAGE=mirror.example.com/library/redis:7-alpine
OCTOAGENT_NGINX_IMAGE=mirror.example.com/library/nginx:1.27-alpine
OCTOAGENT_PYTHON_BASE_IMAGE=mirror.example.com/library/python:3.12-slim
OCTOAGENT_NODE_RUNTIME_IMAGE=mirror.example.com/library/node:22-bookworm-slim
OCTOAGENT_NODE_FRONTEND_IMAGE=mirror.example.com/library/node:22-alpine
```

## 設定

`.env.docker` でポート、モデル API キー、検索 API キー、運用トークンを設定します。

```dotenv
OCTO_NGINX_PORT=19800
OCTOAGENT_MODEL_AUTH_OPENROUTER=sk-or-v1-...
TAVILY_API_KEY=...
POSTGRES_PASSWORD=change-this-before-shared-use

# OpenRouter の帰属情報と usage accounting opt-in。
OCTOAGENT_OPENROUTER_APP_URL=https://github.com/sievepub-2000/octoagent
OCTOAGENT_OPENROUTER_APP_TITLE=OctoAgent
OCTOAGENT_OPENROUTER_USAGE_INCLUDE=true
```

`config.yaml` ではモデルカードやエージェント挙動を調整できます。Docker 版では `/app/config.yaml` としてコンテナに読み取り専用でマウントされます。

## 動作確認

```bash
curl -fsS http://127.0.0.1:19800/health
curl -fsS http://127.0.0.1:19800/api/tools/registry
curl -fsS http://127.0.0.1:19800/api/mcp/smoke
```

ツール状態は WebUI の Tools Hub で確認できます。

```text
http://127.0.0.1:19800/workspace/config/tools
```

より詳しい英語版の Docker 手順は `docs/docker-install.md` を参照してください。
