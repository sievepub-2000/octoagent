"""Render an nginx config template using OctoAgent runtime port variables."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render an nginx config template.")
    parser.add_argument("template", help="Path to the input template")
    parser.add_argument("output", help="Path to the rendered output")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    template_path = Path(args.template)
    output_path = Path(args.output)

    content = template_path.read_text(encoding="utf-8")
    nginx_port = os.getenv("OCTO_NGINX_PORT", "19800")
    replacements = {
        "${OCTO_GATEWAY_PORT}": os.getenv("OCTO_GATEWAY_PORT", "19802"),
        "${OCTO_LANGGRAPH_PORT}": os.getenv("OCTO_LANGGRAPH_PORT", "19804"),
        "${OCTO_FRONTEND_PORT}": os.getenv("OCTO_FRONTEND_PORT", "19806"),
        "${OCTO_PROVISIONER_PORT}": os.getenv("OCTO_PROVISIONER_PORT", "19808"),
        "${OCTO_NGINX_PORT}": nginx_port,
        "${OCTO_NGINX_BIND_HOST}": os.getenv("OCTO_NGINX_BIND_HOST", "127.0.0.1"),
        "${OCTO_NGINX_TEMP_ROOT}": os.getenv("OCTO_NGINX_TEMP_ROOT", f"/tmp/octoagent-nginx-{nginx_port}"),
    }
    for token, value in replacements.items():
        content = content.replace(token, value)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
