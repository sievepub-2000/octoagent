from __future__ import annotations

import socketserver
import threading

from src.utils import proxy_env


class _DeadTunnelHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.recv(4096)
        self.request.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")


def test_open_proxy_port_with_dead_upstream_is_rejected(monkeypatch) -> None:
    for key in proxy_env._PROXY_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OCTOAGENT_PROXY_HEALTH_TIMEOUT", "0.5")
    proxy_env._HEALTH_CACHE.clear()

    with socketserver.TCPServer(("127.0.0.1", 0), _DeadTunnelHandler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{server.server_address[1]}")

        assert proxy_env.should_trust_proxy_env() is False

        server.shutdown()
        thread.join(timeout=2)
