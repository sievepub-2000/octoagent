#!/usr/bin/env python3
import json
import base64
import hashlib
import hmac
import os
import socket
import time
import urllib.error
import urllib.request
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http import cookies
from urllib.parse import parse_qs, quote, unquote, urlparse
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("AI_WORKFLOW_HUB_CONFIG", BASE_DIR / "config.json"))
AUTH_CONFIG_PATH = Path(os.environ.get("AI_WORKFLOW_AUTH_CONFIG", "/etc/ai-workflow-hub/auth.json"))
AUDIT_LOG_PATH = Path(os.environ.get("AI_WORKFLOW_AUDIT_LOG", "/var/log/ai-workflow-hub/audit.jsonl"))
SESSION_COOKIE = os.environ.get("AI_WORKFLOW_SESSION_COOKIE", "aiops_session")
COOKIE_DOMAIN = os.environ.get("AI_WORKFLOW_COOKIE_DOMAIN", ".inarbit.work")
ALLOWED_NEXT_HOSTS = {"inarbit.work", "gateway.inarbit.work", "chat.inarbit.work", "admin.inarbit.work"}
STARTED_AT = time.time()


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_auth_config() -> dict[str, Any]:
    with AUTH_CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def sign_payload(payload: dict[str, Any], secret: str) -> str:
    body = b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{b64url_encode(sig)}"


def verify_session(token: str) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    try:
        body, sig = token.rsplit(".", 1)
        secret = load_auth_config()["session_secret"]
        expected = b64url_encode(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(b64url_decode(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def hash_password(password: str, salt_b64: str, iterations: int) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), b64url_decode(salt_b64), iterations)
    return b64url_encode(digest)


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    auth = load_auth_config()
    user = auth.get("users", {}).get(username)
    if not user or user.get("disabled"):
        return None
    expected = user.get("password_hash", "")
    actual = hash_password(password, user["salt"], int(user.get("iterations", 200000)))
    if not hmac.compare_digest(expected, actual):
        return None
    return {
        "username": username,
        "roles": user.get("roles", []),
        "display_name": user.get("display_name", username),
    }


def role_allowed(user_roles: list[str], required: str) -> bool:
    hierarchy = {"viewer": 1, "operator": 2, "admin": 3}
    required_level = hierarchy.get(required, 2)
    return max((hierarchy.get(role, 0) for role in user_roles), default=0) >= required_level


def audit_event(event: dict[str, Any]) -> None:
    event.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    event.setdefault("service", "ai-workflow-hub")
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception as exc:
        print(f"audit write failed: {exc}", flush=True)


def session_from_headers(headers: Any) -> dict[str, Any] | None:
    raw_cookie = headers.get("Cookie", "")
    parsed = cookies.SimpleCookie(raw_cookie)
    morsel = parsed.get(SESSION_COOKIE)
    if not morsel:
        return None
    return verify_session(morsel.value)


def normalize_next_url(value: str) -> str:
    if not value:
        return "/ai-ops/"
    if value.startswith("/") and not value.startswith("//"):
        return value
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc in ALLOWED_NEXT_HOSTS:
        return value
    return "/ai-ops/"


def check_http(url: str, timeout: float = 8.0) -> dict[str, Any]:
    started = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "inarbit-ai-workflow-hub/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {
                "ok": 200 <= resp.status < 500,
                "status": resp.status,
                "latency_ms": round((time.time() - started) * 1000, 1),
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": exc.code < 500,
            "status": exc.code,
            "latency_ms": round((time.time() - started) * 1000, 1),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": exc.__class__.__name__,
            "latency_ms": round((time.time() - started) * 1000, 1),
        }


def check_tcp(host: str, port: int, timeout: float = 2.0) -> dict[str, Any]:
    started = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"ok": True, "latency_ms": round((time.time() - started) * 1000, 1)}
    except Exception as exc:
        return {
            "ok": False,
            "error": exc.__class__.__name__,
            "latency_ms": round((time.time() - started) * 1000, 1),
        }


def status_payload() -> dict[str, Any]:
    config = load_config()
    systems = []
    for system in config["systems"]:
        item = dict(system)
        health = item.get("health", {})
        if health.get("type") == "http":
            item["runtime"] = check_http(health["url"])
        elif health.get("type") == "tcp":
            item["runtime"] = check_tcp(health["host"], int(health["port"]))
        else:
            item["runtime"] = {"ok": None, "status": "manual"}
        systems.append(item)

    return {
        "title": config["title"],
        "environment": config["environment"],
        "policy": config["policy"],
        "uptime_seconds": int(time.time() - STARTED_AT),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "systems": systems,
        "workflow": config["workflow"],
    }


def dashboard_api_payload(path: str) -> dict[str, Any] | None:
    if path.startswith("/dash/api/analyze/"):
        range_name = path.rsplit("/", 1)[-1] or "total"
        return {
            "status": 0,
            "range": range_name,
            "data": {
                "total_users": 1,
                "total_orders": 0,
                "active_plans": 1,
                "plan_status": {"free": 0, "pro": 0, "premium": 1},
                "users": [{"email": "admin", "role": "admin", "plan": "premium"}],
                "orders": [],
            },
        }
    if path == "/dash/api/user":
        return {
            "status": 0,
            "data": [
                {
                    "email": "admin",
                    "role": "admin",
                    "plan": "premium",
                    "resetChances": 999,
                    "createdAt": None,
                    "updatedAt": None,
                }
            ],
        }
    if path == "/dash/api/order":
        return {"status": 0, "data": []}
    if path == "/dash/api/plan":
        return {
            "status": 0,
            "data": [
                {
                    "name": "premium",
                    "description": "Administrator plan",
                    "price": 0,
                    "features": ["admin"],
                }
            ],
        }
    return None


def login_page(next_url: str = "/ai-ops/") -> bytes:
    safe_next = escape(normalize_next_url(next_url), quote=True)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Inarbit Access</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#f6f7f8; --fg:#171a1f; --muted:#606975; --line:#d7dce2; --card:#fff; --brand:#155eef; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1216; --fg:#f3f4f6; --muted:#a0a7b2; --line:#2b313a; --card:#171b22; }} }}
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; font:14px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--fg); }}
    form {{ width:min(380px, calc(100vw - 32px)); background:var(--card); border:1px solid var(--line); border-radius:8px; padding:24px; box-sizing:border-box; }}
    h1 {{ margin:0 0 6px; font-size:20px; }}
    p {{ margin:0 0 18px; color:var(--muted); }}
    label {{ display:block; margin:12px 0 6px; font-weight:600; }}
    input {{ width:100%; box-sizing:border-box; border:1px solid var(--line); border-radius:6px; padding:10px 12px; background:transparent; color:var(--fg); }}
    button {{ width:100%; margin-top:18px; border:0; border-radius:6px; padding:10px 12px; background:var(--brand); color:white; font-weight:700; cursor:pointer; }}
  </style>
</head>
<body>
  <form method="post" action="/ai-ops/auth/login">
    <h1>Inarbit Unified Access</h1>
    <p>gateway / chat / admin / ai-ops 统一认证入口</p>
    <input type="hidden" name="next" value="{safe_next}" />
    <label for="username">Username</label>
    <input id="username" name="username" autocomplete="username" required />
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required />
    <button type="submit">Sign in</button>
  </form>
</body>
</html>""".encode("utf-8")


def html_page() -> bytes:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Inarbit AI Workflow Hub</title>
  <style>
    :root { color-scheme: light dark; --bg:#f6f7f8; --fg:#171a1f; --muted:#606975; --line:#d7dce2; --card:#fff; --ok:#15803d; --warn:#a16207; --bad:#b91c1c; }
    @media (prefers-color-scheme: dark) { :root { --bg:#0f1216; --fg:#f3f4f6; --muted:#a0a7b2; --line:#2b313a; --card:#171b22; } }
    body { margin:0; font:14px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--fg); }
    header { padding:28px 32px 18px; border-bottom:1px solid var(--line); background:var(--card); }
    h1 { margin:0 0 8px; font-size:24px; letter-spacing:0; }
    main { max-width:1180px; margin:0 auto; padding:24px; }
    .sub { color:var(--muted); max-width:860px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }
    .card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:16px; min-height:142px; }
    .row { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
    .badge { border:1px solid var(--line); border-radius:999px; padding:2px 8px; color:var(--muted); font-size:12px; white-space:nowrap; }
    .ok { color:var(--ok); } .warn { color:var(--warn); } .bad { color:var(--bad); }
    a { color:inherit; text-decoration-thickness:1px; text-underline-offset:3px; }
    section { margin:0 0 22px; }
    h2 { font-size:16px; margin:0 0 12px; }
    ol { margin:0; padding-left:20px; }
    li { margin:7px 0; }
    code { background:rgba(127,127,127,.12); border-radius:4px; padding:1px 4px; }
  </style>
</head>
<body>
  <header>
    <h1>Inarbit AI Workflow Hub</h1>
    <div class="sub">统一展示生产工作流、内部连接器状态和安全边界。批量注册、短信接码、额度池共享和公开多账号反代默认禁用。</div>
  </header>
  <main>
    <section>
      <h2>Runtime Systems</h2>
      <div id="systems" class="grid"></div>
    </section>
    <section>
      <h2>Workflow</h2>
      <ol id="workflow"></ol>
    </section>
  </main>
  <script>
    function stateClass(runtime) {
      if (runtime.ok === true) return "ok";
      if (runtime.ok === false) return "bad";
      return "warn";
    }
    function stateText(runtime) {
      if (runtime.ok === true) return "online";
      if (runtime.ok === false) return "offline";
      return runtime.status || "manual";
    }
    async function load() {
      const res = await fetch("api/status", {cache: "no-store"});
      const data = await res.json();
      document.getElementById("systems").innerHTML = data.systems.map(s => `
        <article class="card">
          <div class="row">
            <strong>${s.name}</strong>
            <span class="badge">${s.kind}</span>
          </div>
          <p>${s.role}</p>
          <p>Status: <span class="${stateClass(s.runtime)}">${stateText(s.runtime)}</span>${s.runtime.latency_ms !== undefined ? ` · ${s.runtime.latency_ms}ms` : ""}</p>
          <p>${s.public_path ? `<a href="${s.public_path}">${s.public_path}</a>` : `<code>${s.status}</code>`}</p>
        </article>
      `).join("");
      document.getElementById("workflow").innerHTML = data.workflow.map(w => `<li><strong>${w.step}</strong> · ${w.owner}: ${w.description}</li>`).join("");
    }
    load();
    setInterval(load, 30000);
  </script>
</body>
</html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def _headers(self, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.end_headers()

    def _redirect(self, location: str, status: int = 302) -> None:
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        self._headers("application/json; charset=utf-8", status)
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _client_ip(self) -> str:
        return self.headers.get("X-Forwarded-For", self.client_address[0]).split(",", 1)[0].strip()

    def _read_request_data(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        content_type = self.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                data = json.loads(raw or "{}")
            except json.JSONDecodeError:
                return {}
            return {str(key): "" if value is None else str(value) for key, value in data.items()}
        parsed = parse_qs(raw)
        return {key: values[0] if values else "" for key, values in parsed.items()}

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/login":
            query = parse_qs(urlparse(self.path).query)
            self._headers("text/html; charset=utf-8")
            self.wfile.write(login_page(query.get("next", ["/ai-ops/"])[0]))
            return
        if path == "/auth/logout":
            self.send_response(302)
            self.send_header("Location", "/ai-ops/login")
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE}=; Path=/; Domain={COOKIE_DOMAIN}; Max-Age=0; HttpOnly; Secure; SameSite=Lax",
            )
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path == "/auth/verify":
            payload = session_from_headers(self.headers)
            required = self.headers.get("X-Required-Role", "operator")
            original_host = self.headers.get("X-Original-Host", "")
            original_uri = self.headers.get("X-Original-URI", "")
            if not payload:
                audit_event({"event": "auth_denied", "reason": "missing_or_invalid_session", "ip": self._client_ip(), "host": original_host, "uri": original_uri})
                self.send_response(401)
                self.send_header("X-Auth-Reason", "missing_or_invalid_session")
                self.end_headers()
                return
            roles = payload.get("roles", [])
            if not role_allowed(roles, required):
                audit_event({"event": "auth_denied", "reason": "insufficient_role", "user": payload.get("sub"), "roles": roles, "required": required, "ip": self._client_ip(), "host": original_host, "uri": original_uri})
                self.send_response(403)
                self.send_header("X-Auth-User", payload.get("sub", ""))
                self.send_header("X-Auth-Role", ",".join(roles))
                self.send_header("X-Auth-Reason", "insufficient_role")
                self.end_headers()
                return
            audit_event({"event": "auth_allowed", "user": payload.get("sub"), "roles": roles, "required": required, "ip": self._client_ip(), "host": original_host, "uri": original_uri})
            self.send_response(204)
            self.send_header("X-Auth-User", payload.get("sub", ""))
            self.send_header("X-Auth-Role", ",".join(roles))
            self.end_headers()
            return
        if path == "/auth/whoami":
            payload = session_from_headers(self.headers)
            if not payload:
                self._headers("application/json; charset=utf-8", 401)
                self.wfile.write(json.dumps({"authenticated": False}).encode("utf-8"))
                return
            self._headers("application/json; charset=utf-8")
            self.wfile.write(json.dumps({"authenticated": True, "user": payload.get("sub"), "roles": payload.get("roles", [])}).encode("utf-8"))
            return
        if path in {"/", "/index.html"}:
            self._headers("text/html; charset=utf-8")
            self.wfile.write(html_page())
            return
        if path == "/api/status":
            self._headers("application/json; charset=utf-8")
            self.wfile.write(json.dumps(status_payload(), ensure_ascii=False).encode("utf-8"))
            return
        dashboard_payload = dashboard_api_payload(path)
        if dashboard_payload is not None:
            audit_event({"event": "dashboard_api_read", "path": path, "ip": self._client_ip()})
            self._json(dashboard_payload)
            return
        if path == "/health":
            self._headers("text/plain; charset=utf-8")
            self.wfile.write(b"OK\n")
            return
        self._headers("text/plain; charset=utf-8", 404)
        self.wfile.write(b"Not found\n")

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/dash/api/login":
            data = self._read_request_data()
            username = (data.get("username") or data.get("email") or "").strip()
            password = data.get("password", "")
            user = authenticate(username, password)
            if not user:
                audit_event({"event": "dashboard_login_failed", "user": username, "ip": self._client_ip()})
                self._json({"status": 1, "message": "Invalid credentials"}, 401)
                return
            auth = load_auth_config()
            now = int(time.time())
            token = sign_payload(
                {
                    "sub": user["username"],
                    "email": user["username"],
                    "roles": user["roles"],
                    "iat": now,
                    "exp": now + int(auth.get("session_ttl_seconds", 43200)),
                },
                auth["session_secret"],
            )
            audit_event({"event": "dashboard_login_success", "user": user["username"], "roles": user["roles"], "ip": self._client_ip()})
            self._json({"sessionToken": token})
            return
        if path != "/auth/login":
            self._headers("text/plain; charset=utf-8", 404)
            self.wfile.write(b"Not found\n")
            return
        data = self._read_request_data()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        next_url = normalize_next_url(unquote(data.get("next", "/ai-ops/") or "/ai-ops/"))
        user = authenticate(username, password)
        if not user:
            audit_event({"event": "login_failed", "user": username, "ip": self._client_ip()})
            self._redirect(f"/ai-ops/login?next={quote(next_url, safe='')}")
            return
        auth = load_auth_config()
        ttl = int(auth.get("session_ttl_seconds", 43200))
        now = int(time.time())
        token = sign_payload({"sub": user["username"], "roles": user["roles"], "iat": now, "exp": now + ttl}, auth["session_secret"])
        audit_event({"event": "login_success", "user": user["username"], "roles": user["roles"], "ip": self._client_ip()})
        self.send_response(302)
        self.send_header("Location", next_url)
        self.send_header(
            "Set-Cookie",
            f"{SESSION_COOKIE}={token}; Path=/; Domain={COOKIE_DOMAIN}; Max-Age={ttl}; HttpOnly; Secure; SameSite=Lax",
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    host = os.environ.get("AI_WORKFLOW_HUB_HOST", "127.0.0.1")
    port = int(os.environ.get("AI_WORKFLOW_HUB_PORT", "8095"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()
