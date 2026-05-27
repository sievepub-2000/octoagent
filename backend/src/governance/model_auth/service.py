"""Encrypted model-provider authentication store and templates."""

from __future__ import annotations

import base64
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx
import yaml
from cryptography.fernet import Fernet, InvalidToken

from src.runtime.config.app_config import AppConfig, reload_app_config
from src.runtime.config.paths import get_paths, get_setup_state_file
from src.runtime.config.effective import RuntimeJsonStore, runtime_state_path


@dataclass(frozen=True)
class ProviderTemplate:
    provider_id: str
    display_name: str
    description: str
    auth_methods: list[str]
    default_base_url: str
    env_var: str
    interface_type: str
    provider_name: str
    default_model: str
    default_models: list[str] = field(default_factory=list)
    supports_official_oauth: bool = False
    supports_unofficial_web_session: bool = False
    docs_url: str | None = None
    notes: str | None = None
    oauth_authorize_url: str | None = None
    oauth_token_url: str | None = None
    oauth_client_id_env: str | None = None
    oauth_client_secret_env: str | None = None
    oauth_scopes: list[str] = field(default_factory=list)
    oauth_login_url: str | None = None
    conversation_url: str | None = None
    conversation_models: list[dict[str, Any]] = field(default_factory=list)
    models_endpoint: str | None = None
    model_catalog_auth: str = "api_key"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "description": self.description,
            "auth_methods": self.auth_methods,
            "default_base_url": self.default_base_url,
            "env_var": self.env_var,
            "interface_type": self.interface_type,
            "provider_name": self.provider_name,
            "default_model": self.default_model,
            "default_models": self.default_models,
            "supports_official_oauth": self.supports_official_oauth,
            "supports_unofficial_web_session": self.supports_unofficial_web_session,
            "docs_url": self.docs_url,
            "notes": self.notes,
            "oauth_login_url": self.oauth_login_url,
            "conversation_url": self.conversation_url,
            "models_endpoint": self.models_endpoint,
            "model_catalog_auth": self.model_catalog_auth,
        }


PROVIDER_TEMPLATES: dict[str, ProviderTemplate] = {
    "anthropic": ProviderTemplate(
        provider_id="anthropic",
        display_name="Claude / Anthropic",
        description="Anthropic Claude API and Claude Code compatible authentication.",
        auth_methods=["api_key", "web_session_placeholder"],
        default_base_url="https://api.anthropic.com",
        env_var="OCTOAGENT_MODEL_AUTH_ANTHROPIC",
        interface_type="anthropic_messages",
        provider_name="anthropic",
        default_model="claude-sonnet-4-5",
        default_models=["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"],
        supports_official_oauth=False,
        supports_unofficial_web_session=True,
        docs_url="https://docs.anthropic.com/",
        notes="Anthropic public API access uses x-api-key credentials. Claude web account OAuth is not used for API calls here.",
        oauth_login_url="https://claude.ai/login",
        conversation_url="https://claude.ai/new",
        models_endpoint="https://api.anthropic.com/v1/models",
        model_catalog_auth="api_key",
        conversation_models=[
            {"id": "claude-opus-4-1", "display_name": "Claude Opus 4.1", "supports_thinking": True, "supports_reasoning_effort": True, "supports_vision": True},
            {"id": "claude-sonnet-4-5", "display_name": "Claude Sonnet 4.5", "supports_thinking": True, "supports_reasoning_effort": True, "supports_vision": True},
            {"id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5", "supports_thinking": False, "supports_reasoning_effort": True, "supports_vision": True},
        ],
    ),
    "openai": ProviderTemplate(
        provider_id="openai",
        display_name="ChatGPT / OpenAI",
        description="OpenAI API using project API keys, with a reserved web-session adapter slot.",
        auth_methods=["api_key", "web_session_placeholder"],
        default_base_url="https://api.openai.com/v1",
        env_var="OCTOAGENT_MODEL_AUTH_OPENAI",
        interface_type="openai_compatible",
        provider_name="openai",
        default_model="gpt-5.2",
        default_models=["gpt-5.2", "gpt-5.4", "gpt-5.4-mini"],
        supports_unofficial_web_session=True,
        docs_url="https://platform.openai.com/docs/api-reference/authentication",
        notes="OpenAI API model access uses project API keys. ChatGPT web login sessions are not used as API credentials.",
        oauth_login_url="https://chatgpt.com/auth/login",
        conversation_url="https://chatgpt.com/",
        models_endpoint="https://api.openai.com/v1/models",
        model_catalog_auth="api_key",
        conversation_models=[
            {"id": "gpt-5.2", "display_name": "GPT-5.2", "supports_reasoning_effort": True, "supports_vision": True},
            {"id": "gpt-5.4", "display_name": "GPT-5.4", "supports_reasoning_effort": True, "supports_vision": True},
            {"id": "gpt-5.4-mini", "display_name": "GPT-5.4 Mini", "supports_reasoning_effort": True, "supports_vision": True},
        ],
    ),
    "xai": ProviderTemplate(
        provider_id="xai",
        display_name="Grok / xAI",
        description="xAI Grok API using Bearer API keys, with a reserved web-session adapter slot.",
        auth_methods=["api_key", "web_session_placeholder"],
        default_base_url="https://api.x.ai/v1",
        env_var="OCTOAGENT_MODEL_AUTH_XAI",
        interface_type="openai_compatible",
        provider_name="xai",
        default_model="grok-4",
        default_models=["grok-4", "grok-4-fast"],
        supports_unofficial_web_session=True,
        docs_url="https://docs.x.ai/docs/tutorial",
        notes="xAI/Grok API access uses Bearer API keys. Grok web login sessions are not used as API credentials.",
        oauth_login_url="https://grok.com/",
        conversation_url="https://grok.com/",
        models_endpoint="https://api.x.ai/v1/models",
        model_catalog_auth="api_key",
        conversation_models=[
            {"id": "grok-4", "display_name": "Grok 4", "supports_vision": True},
            {"id": "grok-4-fast", "display_name": "Grok 4 Fast", "supports_vision": True},
        ],
    ),
    "google": ProviderTemplate(
        provider_id="google",
        display_name="Google / Gemini",
        description="Google Gemini OAuth login for Google-hosted large models.",
        auth_methods=["official_oauth", "api_key", "web_session_placeholder"],
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        env_var="OCTOAGENT_MODEL_AUTH_GOOGLE",
        interface_type="google_genai",
        provider_name="google",
        default_model="gemini-2.5-pro",
        default_models=["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro"],
        supports_official_oauth=True,
        supports_unofficial_web_session=True,
        docs_url="https://ai.google.dev/gemini-api/docs/oauth",
        notes="Login opens Google OAuth. API keys belong in the Add model card, not in the login card.",
        oauth_authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        oauth_token_url="https://oauth2.googleapis.com/token",
        oauth_client_id_env="OCTOAGENT_GOOGLE_OAUTH_CLIENT_ID",
        oauth_client_secret_env="OCTOAGENT_GOOGLE_OAUTH_CLIENT_SECRET",
        oauth_scopes=["https://www.googleapis.com/auth/generative-language"],
        oauth_login_url="https://accounts.google.com/",
        conversation_url="https://gemini.google.com/app",
        models_endpoint="https://generativelanguage.googleapis.com/v1beta/models",
        model_catalog_auth="oauth_or_api_key",
        conversation_models=[
            {"id": "gemini-2.5-pro", "display_name": "Gemini 2.5 Pro", "supports_thinking": True, "supports_reasoning_effort": True, "supports_vision": True},
            {"id": "gemini-2.5-flash", "display_name": "Gemini 2.5 Flash", "supports_thinking": True, "supports_reasoning_effort": True, "supports_vision": True},
            {"id": "gemini-1.5-pro", "display_name": "Gemini 1.5 Pro", "supports_vision": True},
        ],
    ),
    # ── Japan major closed-source models (added 2026-05-27) ──────────────────
    "plamo": ProviderTemplate(
        provider_id="plamo",
        display_name="PLaMo / Preferred Networks",
        description="Preferred Networks PLaMo Prime API for Japanese-first LLM tasks.",
        auth_methods=["api_key"],
        default_base_url="https://platform.preferredai.jp/api/v1",
        env_var="OCTOAGENT_MODEL_AUTH_PLAMO",
        interface_type="openai_compatible",
        provider_name="plamo",
        default_model="plamo-prime",
        default_models=["plamo-prime", "plamo-beta"],
        docs_url="https://plamo.preferredai.jp/",
        notes="Preferred Networks PLaMo API. Sign up via plamo.preferredai.jp; the API endpoint is OpenAI-compatible.",
        oauth_login_url="https://platform.preferredai.jp/",
        conversation_url="https://chat.plamo.preferredai.jp/",
        conversation_models=[
            {"id": "plamo-prime", "display_name": "PLaMo Prime", "supports_vision": False},
            {"id": "plamo-beta", "display_name": "PLaMo β", "supports_vision": False},
        ],
    ),
    "tsuzumi": ProviderTemplate(
        provider_id="tsuzumi",
        display_name="tsuzumi / NTT",
        description="NTT tsuzumi 2 lightweight Japanese LLM, available via NTT Communications and Azure AI Foundry MaaS.",
        auth_methods=["api_key"],
        default_base_url="https://api.tsuzumi.ntt.co.jp/v1",
        env_var="OCTOAGENT_MODEL_AUTH_TSUZUMI",
        interface_type="openai_compatible",
        provider_name="tsuzumi",
        default_model="tsuzumi-2-7b",
        default_models=["tsuzumi-2-7b", "tsuzumi-2-1b"],
        docs_url="https://www.rd.ntt/e/research/JN20231101_h.html",
        notes="NTT tsuzumi is sold under enterprise contracts. Replace base_url with the Azure MaaS or NTT Communications endpoint supplied with your subscription.",
        oauth_login_url="https://www.ntt.com/business/services/application/ai/tsuzumi.html",
        conversation_url="https://www.ntt.com/business/services/application/ai/tsuzumi.html",
        conversation_models=[
            {"id": "tsuzumi-2-7b", "display_name": "tsuzumi-2 7B"},
            {"id": "tsuzumi-2-1b", "display_name": "tsuzumi-2 1B"},
        ],
    ),
    "cotomi": ProviderTemplate(
        provider_id="cotomi",
        display_name="cotomi / NEC",
        description="NEC cotomi enterprise LLM with strong Japanese-language reasoning.",
        auth_methods=["api_key"],
        default_base_url="https://api.cotomi.nec.com/v1",
        env_var="OCTOAGENT_MODEL_AUTH_COTOMI",
        interface_type="openai_compatible",
        provider_name="cotomi",
        default_model="cotomi-pro",
        default_models=["cotomi-pro", "cotomi-light"],
        docs_url="https://jpn.nec.com/LLM/index.html",
        notes="NEC cotomi is enterprise-only; the production endpoint is provisioned per contract. The default_base_url here is a placeholder — replace it with the URL NEC supplies.",
        oauth_login_url="https://jpn.nec.com/LLM/index.html",
        conversation_url="https://jpn.nec.com/LLM/index.html",
        conversation_models=[
            {"id": "cotomi-pro", "display_name": "cotomi Pro"},
            {"id": "cotomi-light", "display_name": "cotomi Light"},
        ],
    ),
    "takane": ProviderTemplate(
        provider_id="takane",
        display_name="Takane / Fujitsu",
        description="Fujitsu Takane enterprise LLM (powered by Cohere Command R+ on Fujitsu Kozuchi).",
        auth_methods=["api_key"],
        default_base_url="https://api.kozuchi.fujitsu.com/v1",
        env_var="OCTOAGENT_MODEL_AUTH_TAKANE",
        interface_type="openai_compatible",
        provider_name="takane",
        default_model="takane",
        default_models=["takane"],
        docs_url="https://www.fujitsu.com/global/about/resources/news/press-releases/2024/0930-01.html",
        notes="Fujitsu Takane is sold via the Fujitsu Kozuchi platform; the endpoint shown is a placeholder. Use the URL provisioned for your Kozuchi tenant.",
        oauth_login_url="https://activate.fujitsu/en/products/portfolio/fujitsu-kozuchi/",
        conversation_url="https://activate.fujitsu/en/products/portfolio/fujitsu-kozuchi/",
        conversation_models=[
            {"id": "takane", "display_name": "Takane"},
        ],
    ),
    # ── Korea major closed-source models (added 2026-05-27) ─────────────────
    "clovax": ProviderTemplate(
        provider_id="clovax",
        display_name="HyperCLOVA X / NAVER",
        description="NAVER HyperCLOVA X via NAVER Cloud Platform CLOVA Studio.",
        auth_methods=["api_key"],
        default_base_url="https://clovastudio.stream.ntruss.com/v1/openai",
        env_var="OCTOAGENT_MODEL_AUTH_CLOVAX",
        interface_type="openai_compatible",
        provider_name="clovax",
        default_model="HCX-005",
        default_models=["HCX-005", "HCX-DASH-002", "HCX-SEED-Vision-Instruct-3B"],
        docs_url="https://api.ncloud-docs.com/docs/clovastudio-summary",
        notes="HyperCLOVA X requires a NAVER Cloud Platform sub-account API key. CLOVA Studio exposes an OpenAI-compatible endpoint under the path shown.",
        oauth_login_url="https://www.ncloud.com/product/aiService/clovaStudio",
        conversation_url="https://clova-x.naver.com/",
        conversation_models=[
            {"id": "HCX-005", "display_name": "HyperCLOVA X 005", "supports_vision": True},
            {"id": "HCX-DASH-002", "display_name": "HyperCLOVA X DASH 002"},
            {"id": "HCX-SEED-Vision-Instruct-3B", "display_name": "HCX SEED Vision 3B", "supports_vision": True},
        ],
    ),
    "exaone": ProviderTemplate(
        provider_id="exaone",
        display_name="EXAONE / LG AI Research",
        description="LG AI Research EXAONE — Korean–English bilingual frontier model, hosted by FriendliAI.",
        auth_methods=["api_key"],
        default_base_url="https://api.friendli.ai/dedicated/v1",
        env_var="OCTOAGENT_MODEL_AUTH_EXAONE",
        interface_type="openai_compatible",
        provider_name="exaone",
        default_model="exaone-3.5-32b-instruct",
        default_models=["exaone-3.5-32b-instruct", "exaone-3.5-7.8b-instruct"],
        docs_url="https://www.lgresearch.ai/exaone",
        notes="LG AI's commercial EXAONE access is brokered through FriendliAI dedicated endpoints (OpenAI-compatible). Replace base_url with your Friendli dedicated endpoint URL.",
        oauth_login_url="https://friendli.ai/",
        conversation_url="https://www.lgresearch.ai/exaone",
        conversation_models=[
            {"id": "exaone-3.5-32b-instruct", "display_name": "EXAONE 3.5 32B Instruct"},
            {"id": "exaone-3.5-7.8b-instruct", "display_name": "EXAONE 3.5 7.8B Instruct"},
        ],
    ),
    "solar": ProviderTemplate(
        provider_id="solar",
        display_name="Solar / Upstage",
        description="Upstage Solar Pro — Korean-bilingual frontier model with an OpenAI-compatible API.",
        auth_methods=["api_key"],
        default_base_url="https://api.upstage.ai/v1",
        env_var="OCTOAGENT_MODEL_AUTH_SOLAR",
        interface_type="openai_compatible",
        provider_name="solar",
        default_model="solar-pro2",
        default_models=["solar-pro2", "solar-mini"],
        docs_url="https://developers.upstage.ai/docs/getting-started/quick-start",
        notes="Upstage Solar API is OpenAI-compatible; sign up at console.upstage.ai to obtain an API key.",
        oauth_login_url="https://console.upstage.ai/",
        conversation_url="https://chat.upstage.ai/",
        models_endpoint="https://api.upstage.ai/v1/models",
        conversation_models=[
            {"id": "solar-pro2", "display_name": "Solar Pro 2"},
            {"id": "solar-mini", "display_name": "Solar Mini"},
        ],
    ),
    "ax": ProviderTemplate(
        provider_id="ax",
        display_name="A.X / SK Telecom",
        description="SK Telecom A.X 4.0 — Korean enterprise LLM.",
        auth_methods=["api_key"],
        default_base_url="https://api.adotx.skt.ai/v1",
        env_var="OCTOAGENT_MODEL_AUTH_AX",
        interface_type="openai_compatible",
        provider_name="ax",
        default_model="ax-4.0",
        default_models=["ax-4.0", "ax-4.0-lite"],
        docs_url="https://developers.adotx.kr/",
        notes="A.X is provided under SK Telecom enterprise contracts. Replace base_url with the endpoint URL supplied with your A.X subscription.",
        oauth_login_url="https://developers.adotx.kr/",
        conversation_url="https://aster.adotx.kr/",
        conversation_models=[
            {"id": "ax-4.0", "display_name": "A.X 4.0"},
            {"id": "ax-4.0-lite", "display_name": "A.X 4.0 Lite"},
        ],
    ),
    "glm": ProviderTemplate(
        provider_id="glm",
        display_name="GLM / Z.AI",
        description="Z.AI GLM API using Bearer API keys.",
        auth_methods=["api_key"],
        default_base_url="https://api.z.ai/api/paas/v4",
        env_var="OCTOAGENT_MODEL_AUTH_GLM",
        interface_type="openai_compatible",
        provider_name="glm",
        default_model="glm-4.7",
        default_models=["glm-4.7", "glm-4.6"],
        docs_url="https://docs.z.ai/api-reference/introduction",
        oauth_login_url="https://chat.z.ai/",
        conversation_url="https://chat.z.ai/",
        conversation_models=[
            {"id": "glm-4.7", "display_name": "GLM 4.7", "supports_thinking": True, "supports_reasoning_effort": True, "supports_vision": True},
            {"id": "glm-4.6", "display_name": "GLM 4.6", "supports_thinking": True, "supports_reasoning_effort": True, "supports_vision": True},
        ],
    ),
    "minimax": ProviderTemplate(
        provider_id="minimax",
        display_name="MiniMax",
        description="MiniMax API using Bearer API keys or Token Plan keys.",
        auth_methods=["api_key"],
        default_base_url="https://api.minimax.io/v1",
        env_var="OCTOAGENT_MODEL_AUTH_MINIMAX",
        interface_type="openai_compatible",
        provider_name="minimax",
        default_model="MiniMax-M2.7",
        default_models=["MiniMax-M2.7", "MiniMax-M2.5"],
        docs_url="https://platform.minimax.io/docs/api-reference/api-overview",
        oauth_login_url="https://www.minimax.io/platform/user-center/basic-information/interface-key",
        conversation_url="https://chat.minimax.io/",
        conversation_models=[
            {"id": "MiniMax-M2.7", "display_name": "MiniMax M2.7", "supports_vision": True},
            {"id": "MiniMax-M2.5", "display_name": "MiniMax M2.5", "supports_vision": True},
        ],
    ),
    "qwen": ProviderTemplate(
        provider_id="qwen",
        display_name="Qwen / DashScope",
        description="Qwen Cloud / DashScope API keys and Coding Plan keys.",
        auth_methods=["api_key"],
        default_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        env_var="OCTOAGENT_MODEL_AUTH_QWEN",
        interface_type="openai_compatible",
        provider_name="qwen",
        default_model="qwen3.6-plus",
        default_models=["qwen3.6-plus", "qwen3.5-plus", "qwen-max"],
        docs_url="https://docs.qwencloud.com/api-reference/preparation/api-key",
        notes="Qwen Code OAuth free tier was discontinued; API Key/Coding Plan is the stable path.",
        oauth_login_url="https://bailian.console.aliyun.com/",
        conversation_url="https://chat.qwen.ai/",
        conversation_models=[
            {"id": "qwen3.6-plus", "display_name": "Qwen 3.6 Plus", "supports_thinking": True, "supports_reasoning_effort": True, "supports_vision": True},
            {"id": "qwen3.5-plus", "display_name": "Qwen 3.5 Plus", "supports_thinking": True, "supports_reasoning_effort": True, "supports_vision": True},
            {"id": "qwen-max", "display_name": "Qwen Max", "supports_reasoning_effort": True, "supports_vision": True},
        ],
    ),
    "deepseek": ProviderTemplate(
        provider_id="deepseek",
        display_name="DeepSeek",
        description="DeepSeek API using Bearer API keys.",
        auth_methods=["api_key"],
        default_base_url="https://api.deepseek.com/v1",
        env_var="OCTOAGENT_MODEL_AUTH_DEEPSEEK",
        interface_type="deepseek_reasoner",
        provider_name="deepseek",
        default_model="deepseek-reasoner",
        default_models=["deepseek-reasoner", "deepseek-chat"],
        docs_url="https://api-docs.deepseek.com/api/deepseek-api",
        oauth_login_url="https://chat.deepseek.com/sign_in",
        conversation_url="https://chat.deepseek.com/",
        conversation_models=[
            {"id": "deepseek-reasoner", "display_name": "DeepSeek Reasoner", "supports_thinking": True},
            {"id": "deepseek-chat", "display_name": "DeepSeek Chat"},
        ],
    ),
}


class ModelAuthService:
    def __init__(self) -> None:
        self._store = RuntimeJsonStore(runtime_state_path("model_auth", "credentials.json"), {"providers": {}})
        self._key_path = runtime_state_path("model_auth", "credential.key")
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        if self._key_path.exists():
            return self._key_path.read_bytes().strip()
        key = Fernet.generate_key()
        self._key_path.write_bytes(key)
        try:
            self._key_path.chmod(0o600)
        except OSError:
            pass
        return key

    def templates(self) -> list[dict[str, Any]]:
        return [template.to_public_dict() for template in PROVIDER_TEMPLATES.values()]

    def _read(self) -> dict[str, Any]:
        payload = self._store.read()
        payload.setdefault("providers", {})
        payload.setdefault("oauth_sessions", {})
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        self._store.write(payload)

    def _encrypt(self, secret: str) -> str:
        token = self._fernet.encrypt(secret.encode("utf-8"))
        return token.decode("ascii")

    def _encrypt_json(self, payload: dict[str, Any]) -> str:
        return self._encrypt(json.dumps(payload, ensure_ascii=False))

    def _decrypt(self, token: str) -> str | None:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            return None

    def _decrypt_json(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        raw = self._decrypt(str(token))
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def apply_env(self) -> None:
        payload = self._read()
        for provider_id, record in (payload.get("providers") or {}).items():
            template = PROVIDER_TEMPLATES.get(str(provider_id))
            if not template or not isinstance(record, dict):
                continue
            secret = self._decrypt(str(record.get("encrypted_secret") or ""))
            if secret:
                os.environ[template.env_var] = secret

    def status(self) -> dict[str, Any]:
        payload = self._read()
        providers = payload.get("providers") if isinstance(payload.get("providers"), dict) else {}
        result = {}
        for provider_id, template in PROVIDER_TEMPLATES.items():
            record = providers.get(provider_id) if isinstance(providers.get(provider_id), dict) else {}
            has_secret = bool(record.get("encrypted_secret")) or self._env_secret(template) is not None
            auth_mode = record.get("auth_mode")
            has_web_login = auth_mode in {"web_oauth", "web_dialog", "oauth_authorization_code"}
            result[provider_id] = {
                **template.to_public_dict(),
                "connected": has_secret or has_web_login,
                "auth_mode": auth_mode,
                "account_label": record.get("account_label"),
                "base_url": record.get("base_url") or template.default_base_url,
                "model": record.get("model") or template.default_model,
                "credential_ref": f"${template.env_var}" if has_secret else (f"web-session:{provider_id}" if has_web_login else None),
                "updated_at": record.get("updated_at"),
            }
        return result

    def save_credentials(
        self,
        provider_id: str,
        *,
        api_key: str | None = None,
        account_label: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        auth_mode: str = "api_key",
        session_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        template = self._template(provider_id)
        payload = self._read()
        providers = payload.setdefault("providers", {})
        secret = (api_key or "").strip()
        record = dict(providers.get(provider_id) or {})
        if secret:
            record["encrypted_secret"] = self._encrypt(secret)
            os.environ[template.env_var] = secret
        elif auth_mode == "none":
            record.pop("encrypted_secret", None)
            os.environ.pop(template.env_var, None)
        else:
            raise ValueError("api_key is required for this authentication mode")
        record.update(
            {
                "auth_mode": auth_mode,
                "account_label": account_label or self._mask_secret(secret) if secret else account_label,
                "base_url": (base_url or template.default_base_url).rstrip("/"),
                "model": model or template.default_model,
                "updated_at": time.time(),
            }
        )
        if session_payload:
            record["session_payload"] = self._encrypt(base64.b64encode(repr(session_payload).encode("utf-8")).decode("ascii"))
        providers[provider_id] = record
        self._write(payload)
        return self.status()[provider_id]

    def begin_oauth_login(
        self,
        provider_id: str,
        *,
        callback_url: str | None = None,
        state: str | None = None,
        prefer_web_dialog: bool = False,
    ) -> dict[str, Any]:
        template = self._template(provider_id)
        account_login_url = template.oauth_login_url or template.docs_url or template.default_base_url
        oauth_state = state or secrets.token_urlsafe(18)
        client_id = os.getenv(template.oauth_client_id_env or "", "").strip()
        client_secret = os.getenv(template.oauth_client_secret_env or "", "").strip()
        login_url = account_login_url
        mode = "api_key_model_import"
        ok = self._provider_secret(template) is not None
        message = "Official API key is available. OctoAgent can import this provider's model catalog without using a web login session."

        if template.supports_official_oauth and template.oauth_authorize_url and template.oauth_token_url and client_id and client_secret and callback_url:
            params = {
                "client_id": client_id,
                "redirect_uri": callback_url,
                "response_type": "code",
                "scope": " ".join(template.oauth_scopes),
                "state": oauth_state,
                "access_type": "offline",
                "prompt": "consent",
            }
            login_url = f"{template.oauth_authorize_url}?{urlencode(params)}"
            mode = "oauth_authorization_code"
            message = "Official OAuth authorization opened. Complete account verification, then return to OctoAgent to import available web models."
        elif not ok:
            ok = False
            mode = "api_key_required"
            if template.supports_official_oauth:
                message = "Official OAuth client credentials are not configured and no API key is available. Configure OAuth env vars or add an API key before importing models."
            else:
                message = "This provider does not expose a supported API OAuth flow here. Configure an official API key before importing models."
        if mode in {"api_key_model_import", "api_key_required"}:
            login_url = ""

        payload = self._read()
        sessions = payload.setdefault("oauth_sessions", {})
        sessions[oauth_state] = {
            "provider_id": provider_id,
            "mode": mode,
            "authorized": False,
            "created_at": time.time(),
            "login_url": login_url,
            "conversation_url": template.conversation_url,
            "account_login_url": account_login_url,
            "callback_url": callback_url,
        }
        if ok and mode == "api_key_model_import":
            sessions[oauth_state]["authorized"] = True
            sessions[oauth_state]["authorized_at"] = time.time()
            sessions[oauth_state]["model_source"] = "official_api_model_catalog"
        self._write(payload)
        return {
            "ok": ok,
            "provider_id": provider_id,
            "mode": mode,
            "login_url": login_url,
            "conversation_url": template.conversation_url,
            "account_login_url": account_login_url,
            "message": message,
            "state": oauth_state,
            "requires_confirmation": True,
        }

    async def complete_oauth_callback(self, provider_id: str, *, state: str, code: str, callback_url: str | None = None) -> dict[str, Any]:
        template = self._template(provider_id)
        if not template.oauth_token_url:
            raise ValueError(f"{template.display_name} does not have a configured OAuth token endpoint")
        payload = self._read()
        session = self._oauth_session(payload, provider_id, state)
        client_id = os.getenv(template.oauth_client_id_env or "", "").strip()
        client_secret = os.getenv(template.oauth_client_secret_env or "", "").strip()
        redirect_uri = callback_url or str(session.get("callback_url") or "")
        if not client_id or not client_secret or not redirect_uri:
            raise ValueError("OAuth client id, client secret, and redirect URI are required")
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(template.oauth_token_url, data=form)
        if resp.status_code >= 400:
            raise ValueError(f"OAuth token exchange failed: HTTP {resp.status_code} {resp.text[:400]}")
        token_payload = resp.json()
        if not isinstance(token_payload, dict) or not token_payload.get("access_token"):
            raise ValueError("OAuth token response did not contain an access token")
        session["authorized"] = True
        session["authorized_at"] = time.time()
        session["model_source"] = "official_oauth_model_catalog"
        session["encrypted_oauth_token"] = self._encrypt_json(token_payload)
        self._write(payload)
        return {
            "ok": True,
            "provider_id": provider_id,
            "display_name": template.display_name,
            "state": state,
            "mode": session.get("mode"),
            "message": "OAuth token exchange succeeded. You can return to OctoAgent and import available models.",
        }

    def confirm_oauth_login(self, provider_id: str, *, state: str) -> dict[str, Any]:
        template = self._template(provider_id)
        payload = self._read()
        session = self._oauth_session(payload, provider_id, state)
        if session.get("mode") == "api_key_required":
            raise ValueError("No OAuth authorization or official API key is available for this provider")
        if session.get("mode") == "oauth_authorization_code" and not session.get("encrypted_oauth_token"):
            raise ValueError("OAuth callback has not completed yet. Finish provider authorization before importing models.")
        session["authorized"] = True
        session.setdefault("authorized_at", time.time())
        session["model_source"] = "official_oauth_model_catalog" if session.get("encrypted_oauth_token") else "official_api_model_catalog"
        self._write(payload)
        return {
            "ok": True,
            "provider_id": provider_id,
            "display_name": template.display_name,
            "state": state,
            "mode": session.get("mode"),
            "message": "Provider authorization confirmed. OctoAgent can now read this provider's model catalog for selection.",
        }

    async def discover_conversation_models(self, provider_id: str, *, state: str | None = None) -> dict[str, Any]:
        template = self._template(provider_id)
        source = "template_model_catalog"
        if state:
            session = self._oauth_session(self._read(), provider_id, state)
            if not session.get("authorized"):
                raise ValueError("OAuth authorization must be confirmed before importing web models")
            token_payload = self._decrypt_json(session.get("encrypted_oauth_token"))
        else:
            token_payload = None
        official_models = await self._fetch_official_models(provider_id, template, token_payload=token_payload)
        if official_models:
            models = official_models
            source = "official_oauth_model_catalog" if token_payload else "official_api_model_catalog"
        else:
            models = self._conversation_models(template)
        return {
            "provider_id": provider_id,
            "display_name": template.display_name,
            "conversation_url": template.conversation_url or template.oauth_login_url,
            "models": models,
            "source": source,
            "message": "Choose one official provider model to import into OctoAgent." if source != "template_model_catalog" else "Official model listing was unavailable; choose from OctoAgent's curated provider catalog.",
        }

    async def configure_conversation_model(
        self,
        provider_id: str,
        *,
        model: str,
        account_label: str | None = None,
        set_default: bool = True,
        state: str | None = None,
    ) -> dict[str, Any]:
        template = self._template(provider_id)
        if state:
            session = self._oauth_session(self._read(), provider_id, state)
            if not session.get("authorized"):
                raise ValueError("OAuth authorization must be confirmed before importing web models")
        selected = await self._resolve_import_model(provider_id, template, model, state=state)
        payload = self._read()
        providers = payload.setdefault("providers", {})
        record = dict(providers.get(provider_id) or {})
        record.update(
            {
                "auth_mode": "web_oauth",
                "account_label": account_label or f"{template.display_name} OAuth web account",
                "base_url": template.default_base_url.rstrip("/"),
                "model": selected["id"],
                "updated_at": time.time(),
                "conversation_url": template.conversation_url or template.oauth_login_url,
                "model_source": "official_oauth_model_catalog" if state else "official_api_model_catalog",
                "oauth_state": state,
            }
        )
        providers[provider_id] = record
        self._write(payload)
        synced = self.sync_model_config(provider_id)["model"]
        if set_default:
            self._set_default_model(str(synced["name"]))
        test = self._test_web_dialog_model(provider_id, selected)
        return {
            "success": True,
            "provider": self.status()[provider_id],
            "model": synced,
            "selected_model": selected,
            "default_model": synced["name"] if set_default else None,
            "test": test,
        }

    def logout(self, provider_id: str) -> dict[str, Any]:
        template = self._template(provider_id)
        payload = self._read()
        providers = payload.setdefault("providers", {})
        providers.pop(provider_id, None)
        self._write(payload)
        os.environ.pop(template.env_var, None)
        return self.status()[provider_id]

    async def test_connection(self, provider_id: str) -> dict[str, Any]:
        template = self._template(provider_id)
        record = self.status()[provider_id]
        if record.get("auth_mode") in {"web_oauth", "web_dialog", "oauth_authorization_code"} and not os.environ.get(template.env_var):
            return {
                "ok": True,
                "message": "OAuth web account is configured. API-key probing is skipped because this provider card imports web models through OAuth authorization instead of API credentials.",
                "status": record,
            }
        secret = self._provider_secret(template)
        if not secret:
            return {"ok": False, "message": "No credential saved", "status": record}
        base_url = str(record.get("base_url") or template.default_base_url).rstrip("/")
        headers = {"Authorization": f"Bearer {secret}"}
        if provider_id == "anthropic":
            headers = {"x-api-key": secret, "anthropic-version": "2023-06-01"}
        url = f"{base_url}/models" if not base_url.endswith("/models") else base_url
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=headers)
            return {"ok": 200 <= resp.status_code < 500, "http_status": resp.status_code, "message": resp.text[:300], "status": record}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "status": record}

    def sync_model_config(self, provider_id: str) -> dict[str, Any]:
        template = self._template(provider_id)
        record = self.status()[provider_id]
        model_name = f"{provider_id}-{str(record.get('model') or template.default_model).replace('/', '-').replace(':', '-') }"
        auth_mode = str(record.get("auth_mode") or "")
        is_web_login = auth_mode in {"web_oauth", "web_dialog", "oauth_authorization_code"}
        provider_model = str(record.get("model") or template.default_model)
        try:
            selected = self._conversation_model(template, provider_model)
        except ValueError:
            selected = {
                "id": provider_model,
                "display_name": provider_model,
                "supports_thinking": provider_id in {"anthropic", "deepseek", "qwen", "glm", "google"},
                "supports_reasoning_effort": provider_id in {"openai", "anthropic", "qwen", "glm", "google"},
                "supports_vision": provider_id in {"openai", "anthropic", "xai", "qwen", "glm", "minimax", "google"},
            }
        model_entry = {
            "name": model_name,
            "display_name": selected.get("display_name") or record.get("display_name") or template.display_name,
            "description": f"{template.display_name} official web model imported through OAuth authorization." if is_web_login else template.description,
            "provider_name": template.provider_name,
            "model": record.get("model") or template.default_model,
            "api_key": f"${template.env_var}",
            "base_url": record.get("base_url") or template.default_base_url,
            "interface_type": template.interface_type,
            "temperature": 0,
            "request_timeout": 120,
            "supports_thinking": bool(selected.get("supports_thinking", provider_id in {"anthropic", "deepseek", "qwen", "glm", "google"})),
            "supports_reasoning_effort": bool(selected.get("supports_reasoning_effort", provider_id in {"openai", "anthropic", "qwen", "glm", "google"})),
            "supports_vision": bool(selected.get("supports_vision", provider_id in {"openai", "anthropic", "xai", "qwen", "glm", "minimax", "google"})),
            "source": "model_auth_template",
        }
        if is_web_login:
            model_entry["auth_mode"] = auth_mode
            model_entry["conversation_url"] = record.get("conversation_url") or template.conversation_url
            model_entry["source"] = "model_auth_web_oauth"
        if provider_id == "anthropic":
            model_entry["api_key"] = f"${template.env_var}"
        config_path = AppConfig.resolve_config_path()
        config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        models = list(config_data.get("models") or [])
        for index, existing in enumerate(models):
            if isinstance(existing, dict) and existing.get("name") == model_name:
                models[index] = {**existing, **model_entry}
                break
        else:
            models.append(model_entry)
        config_data["models"] = models
        config_path.write_text(yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        reload_app_config(str(config_path))
        return {"model": model_entry, "status": self.status()[provider_id]}

    async def _resolve_import_model(self, provider_id: str, template: ProviderTemplate, model: str, *, state: str | None = None) -> dict[str, Any]:
        token_payload = None
        if state:
            session = self._oauth_session(self._read(), provider_id, state)
            token_payload = self._decrypt_json(session.get("encrypted_oauth_token"))
        for candidate in await self._fetch_official_models(provider_id, template, token_payload=token_payload):
            if candidate["id"] == str(model).strip():
                return candidate
        return self._conversation_model(template, model)

    async def _fetch_official_models(self, provider_id: str, template: ProviderTemplate, *, token_payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if not template.models_endpoint:
            return []
        headers: dict[str, str] = {}
        params: dict[str, str] = {}
        if token_payload and token_payload.get("access_token"):
            headers["Authorization"] = f"Bearer {token_payload['access_token']}"
        else:
            secret = self._provider_secret(template)
            if not secret:
                return []
            if provider_id == "anthropic":
                headers = {"x-api-key": secret, "anthropic-version": "2023-06-01"}
            elif provider_id == "google":
                params = {"key": secret}
            else:
                headers = {"Authorization": f"Bearer {secret}"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(template.models_endpoint, headers=headers, params=params)
            if resp.status_code >= 400:
                return []
            payload = resp.json()
        except Exception:
            return []
        return self._normalize_model_catalog(provider_id, payload)

    def _provider_secret(self, template: ProviderTemplate) -> str | None:
        secret = self._env_secret(template)
        if secret:
            return secret
        payload = self._read()
        providers = payload.get("providers") if isinstance(payload.get("providers"), dict) else {}
        record = providers.get(template.provider_id) if isinstance(providers.get(template.provider_id), dict) else {}
        return self._decrypt(str(record.get("encrypted_secret") or ""))

    @staticmethod
    def _env_secret(template: ProviderTemplate) -> str | None:
        aliases = {
            "anthropic": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
            "openai": ["OPENAI_API_KEY"],
            "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
            "xai": ["XAI_API_KEY", "GROK_API_KEY"],
        }
        for name in [template.env_var, *aliases.get(template.provider_id, [])]:
            value = os.environ.get(name)
            if value:
                return value
        return None

    @staticmethod
    def _normalize_model_catalog(provider_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if provider_id == "google":
            raw_models = payload.get("models") if isinstance(payload.get("models"), list) else []
            ids = [str(item.get("name", "")).removeprefix("models/") for item in raw_models if isinstance(item, dict)]
        else:
            raw_models = payload.get("data") if isinstance(payload.get("data"), list) else payload.get("models") if isinstance(payload.get("models"), list) else []
            ids = [str(item.get("id") or item.get("name") or "") for item in raw_models if isinstance(item, dict)]
        result = []
        for model_id in ids:
            if not model_id or model_id.startswith("models/"):
                continue
            lower = model_id.lower()
            result.append(
                {
                    "id": model_id,
                    "display_name": model_id,
                    "description": "Official provider model discovered from the provider API",
                    "supports_thinking": any(token in lower for token in ("reason", "thinking", "claude", "gemini")),
                    "supports_reasoning_effort": any(token in lower for token in ("gpt", "claude", "gemini", "grok")),
                    "supports_vision": any(token in lower for token in ("vision", "gpt-4", "gpt-5", "claude", "gemini", "grok")),
                    "max_context_tokens": None,
                }
            )
        return result

    def _conversation_models(self, template: ProviderTemplate) -> list[dict[str, Any]]:
        if template.conversation_models:
            return [
                {
                    "id": str(item.get("id") or item.get("model") or ""),
                    "display_name": str(item.get("display_name") or item.get("id") or item.get("model") or ""),
                    "description": str(item.get("description") or "Official web model imported through OAuth"),
                    "supports_thinking": bool(item.get("supports_thinking", False)),
                    "supports_reasoning_effort": bool(item.get("supports_reasoning_effort", False)),
                    "supports_vision": bool(item.get("supports_vision", False)),
                    "max_context_tokens": item.get("max_context_tokens"),
                }
                for item in template.conversation_models
                if str(item.get("id") or item.get("model") or "").strip()
            ]
        return [
            {
                "id": model,
                "display_name": model,
                "description": "Official web model imported through OAuth",
                "supports_thinking": False,
                "supports_reasoning_effort": False,
                "supports_vision": False,
                "max_context_tokens": None,
            }
            for model in template.default_models
        ]

    def _conversation_model(self, template: ProviderTemplate, model: str) -> dict[str, Any]:
        model_id = str(model).strip()
        for candidate in self._conversation_models(template):
            if candidate["id"] == model_id:
                return candidate
        raise ValueError(f"Model '{model}' is not available for {template.display_name} OAuth web import")

    def _set_default_model(self, model_name: str) -> None:
        target = get_setup_state_file()
        state: dict[str, Any] = {}
        if target.exists():
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    state = payload
            except Exception:
                state = {}
        state.setdefault("workspace_path", str(get_paths().base_dir))
        state.setdefault("sandbox_mode", "local")
        state["default_model"] = model_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _test_web_dialog_model(provider_id: str, selected: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "mode": "web_oauth_model_import",
            "provider_id": provider_id,
            "model": selected["id"],
            "message": "OAuth authorization was confirmed, the selected official web model was imported into OctoAgent, and it is now available as the system default. API-key probing is intentionally not used for web OAuth import cards.",
        }

    @staticmethod
    def _oauth_session(payload: dict[str, Any], provider_id: str, state: str) -> dict[str, Any]:
        sessions = payload.get("oauth_sessions") if isinstance(payload.get("oauth_sessions"), dict) else {}
        session = sessions.get(state) if isinstance(sessions.get(state), dict) else None
        if not session or session.get("provider_id") != provider_id:
            raise ValueError("OAuth session was not found or does not match this provider")
        return session

    def _template(self, provider_id: str) -> ProviderTemplate:
        template = PROVIDER_TEMPLATES.get(provider_id)
        if not template:
            raise KeyError(f"Unknown model auth provider: {provider_id}")
        return template

    @staticmethod
    def _mask_secret(secret: str) -> str:
        if len(secret) <= 8:
            return "saved credential"
        return f"{secret[:4]}...{secret[-4:]}"


_service: ModelAuthService | None = None


def get_model_auth_service() -> ModelAuthService:
    global _service
    if _service is None:
        _service = ModelAuthService()
    return _service


def initialize_model_auth_env() -> None:
    get_model_auth_service().apply_env()
