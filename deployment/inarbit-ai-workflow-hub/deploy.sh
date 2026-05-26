#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-inarbit}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ssh "$TARGET" 'install -d -o www-data -g www-data -m 0755 /opt/ai-workflow-hub'
scp "$SRC_DIR/server.py" "$SRC_DIR/config.json" "$TARGET:/opt/ai-workflow-hub/"
ssh "$TARGET" 'chown www-data:www-data /opt/ai-workflow-hub/server.py /opt/ai-workflow-hub/config.json && chmod 0644 /opt/ai-workflow-hub/server.py /opt/ai-workflow-hub/config.json'
scp "$SRC_DIR/ai-workflow-hub.service" "$TARGET:/etc/systemd/system/ai-workflow-hub.service"

ssh "$TARGET" 'python3 - <<'"'"'PY'"'"'
from pathlib import Path

path = Path("/etc/nginx/sites-available/inarbit.work")
text = path.read_text()
block = """
    location = /ai-ops {
        return 302 /ai-ops/;
    }

    location /ai-ops/ {
        proxy_pass http://127.0.0.1:8095/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

"""

if "location /ai-ops/" not in text:
    marker = "    location = /openclaw {\n"
    if marker not in text:
        raise SystemExit("Nginx insertion marker not found")
    text = text.replace(marker, block + marker, 1)
    path.write_text(text)
PY'

ssh "$TARGET" 'python3 - <<'"'"'PY'"'"'
from pathlib import Path

path = Path("/etc/nginx/sites-available/ai-admin-panels")
text = path.read_text()
if "proxy_pass http://127.0.0.1:8095/dash/api/login;" not in text:
    admin_marker = "    server_name admin.inarbit.work;"
    admin_pos = text.find(admin_marker)
    if admin_pos < 0:
        raise SystemExit("admin.inarbit.work server block not found")
    location_pos = text.find("    location / {\n", admin_pos)
    if location_pos < 0:
        raise SystemExit("admin.inarbit.work root location not found")
    block = """
    location = /api/login {
        auth_request /_ai_auth/verify;
        auth_request_set $ai_auth_user $upstream_http_x_auth_user;
        auth_request_set $ai_auth_role $upstream_http_x_auth_role;
        error_page 401 = @ai_login_redirect;
        error_page 403 = @ai_forbidden;
        access_log /var/log/nginx/ai_access_audit.log ai_access;

        proxy_pass http://127.0.0.1:8095/dash/api/login;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Authenticated-User $ai_auth_user;
        proxy_set_header X-Authenticated-Role $ai_auth_role;
    }

    location ^~ /api/analyze/ {
        auth_request /_ai_auth/verify;
        auth_request_set $ai_auth_user $upstream_http_x_auth_user;
        auth_request_set $ai_auth_role $upstream_http_x_auth_role;
        error_page 401 = @ai_login_redirect;
        error_page 403 = @ai_forbidden;
        access_log /var/log/nginx/ai_access_audit.log ai_access;

        rewrite ^/api/(.*)$ /dash/api/$1 break;
        proxy_pass http://127.0.0.1:8095;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Authenticated-User $ai_auth_user;
        proxy_set_header X-Authenticated-Role $ai_auth_role;
    }

    location ~ ^/api/(user|order|plan)$ {
        auth_request /_ai_auth/verify;
        auth_request_set $ai_auth_user $upstream_http_x_auth_user;
        auth_request_set $ai_auth_role $upstream_http_x_auth_role;
        error_page 401 = @ai_login_redirect;
        error_page 403 = @ai_forbidden;
        access_log /var/log/nginx/ai_access_audit.log ai_access;

        rewrite ^/api/(.*)$ /dash/api/$1 break;
        proxy_pass http://127.0.0.1:8095;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Authenticated-User $ai_auth_user;
        proxy_set_header X-Authenticated-Role $ai_auth_role;
    }

"""
    text = text[:location_pos] + block + text[location_pos:]
    path.write_text(text)
PY'

ssh "$TARGET" 'systemctl daemon-reload && systemctl enable ai-workflow-hub.service && systemctl restart ai-workflow-hub.service && nginx -t && systemctl reload nginx'
ssh "$TARGET" 'curl -fsS http://127.0.0.1:8095/health && curl -fsS http://127.0.0.1:8095/api/status >/tmp/ai-workflow-hub-status.json && systemctl is-active ai-workflow-hub.service'
