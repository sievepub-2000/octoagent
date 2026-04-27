#!/usr/bin/env bash
# OctoAgent WebUI launcher
# Starts local services in production-daemon mode and opens the shared WebUI once
# the real HTTP route is responding.

set -e

export PATH="/snap/bin:/usr/local/bin:/usr/bin:/usr/sbin:$PATH"

OCTOPUSAGENT_PORT=19880
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$REPO_ROOT" || exit 1

make start-daemon > /tmp/octoagent-startup.log 2>&1

echo "正在启动 OctoAgent WebUI..."
for i in $(seq 1 120); do
    if curl -fsS "http://127.0.0.1:$OCTOPUSAGENT_PORT/api/models" >/dev/null 2>&1; then
        echo "✓ OctoAgent 已就绪，正在打开外部浏览器..."
        su - sieve-pub -c "xdg-open http://localhost:$OCTOPUSAGENT_PORT" 2>/dev/null &
        echo "✓ 浏览器已打开: http://localhost:$OCTOPUSAGENT_PORT"
        echo "  停止服务: make stop"
        exit 0
    fi
    sleep 1
done

echo "✗ 启动超时，请查看日志: /tmp/octoagent-startup.log"
exit 1
