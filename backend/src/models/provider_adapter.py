"""Provider adapter metadata and wrapper models for normalized proxy-style access."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from pydantic import BaseModel, ConfigDict, Field

from .error_contracts import normalize_model_exception
from .interfaces import resolve_model_interface_profile
from .semantics import SemanticChatModel

AdapterType = Literal[
    "cli_proxy_api",
    "anthropic_native",
    "google_native",
    "generic",
]


class ProviderAdapterProfile(BaseModel):
    """Serializable provider-adapter metadata."""

    adapter_type: AdapterType
    interface_type: str
    provider_family: str
    request_contract: str
    response_contract: str
    streaming_contract: str
    auth_mode: str
    proxy_compatible: bool = False

    model_config = ConfigDict(frozen=True)


def resolve_provider_adapter_profile(model_config: Any) -> ProviderAdapterProfile:
    """Infer the adapter contract for a configured model."""

    interface_profile = resolve_model_interface_profile(
        interface_type=getattr(model_config, "interface_type", None),
        provider_name=getattr(model_config, "provider_name", None),
        provider_family=getattr(model_config, "provider_family", None),
        use_path=getattr(model_config, "use", None),
    )

    interface_type = interface_profile.name
    provider_family = interface_profile.provider_family

    if interface_type in {"openai_compatible", "deepseek_reasoner"}:
        return ProviderAdapterProfile(
            adapter_type="cli_proxy_api",
            interface_type=interface_type,
            provider_family=provider_family,
            request_contract="chat.completions",
            response_contract="chat.completions",
            streaming_contract="chat.completions.chunk",
            auth_mode="bearer_header",
            proxy_compatible=True,
        )
    if interface_type == "anthropic_messages":
        return ProviderAdapterProfile(
            adapter_type="anthropic_native",
            interface_type=interface_type,
            provider_family=provider_family,
            request_contract="anthropic.messages",
            response_contract="anthropic.messages",
            streaming_contract="anthropic.messages.stream",
            auth_mode="x_api_key_header",
            proxy_compatible=False,
        )
    if interface_type == "google_genai":
        return ProviderAdapterProfile(
            adapter_type="google_native",
            interface_type=interface_type,
            provider_family=provider_family,
            request_contract="google.generate_content",
            response_contract="google.generate_content",
            streaming_contract="google.generate_content.stream",
            auth_mode="api_key_query_or_header",
            proxy_compatible=False,
        )
    return ProviderAdapterProfile(
        adapter_type="generic",
        interface_type=interface_type,
        provider_family=provider_family,
        request_contract="generic.invoke",
        response_contract="generic.invoke",
        streaming_contract="generic.stream",
        auth_mode="provider_native",
        proxy_compatible=False,
    )


class ProviderAdapterChatModel(SemanticChatModel):
    """Semantic model wrapper with provider-adapter metadata and error normalization."""

    model_name: str
    provider_name: str | None = None
    adapter_profile: ProviderAdapterProfile = Field(
        default_factory=lambda: ProviderAdapterProfile(
            adapter_type="generic",
            interface_type="generic",
            provider_family="generic",
            request_contract="generic.invoke",
            response_contract="generic.invoke",
            streaming_contract="generic.stream",
            auth_mode="provider_native",
            proxy_compatible=False,
        )
    )

    @property
    def _llm_type(self) -> str:
        return f"adapter-{self.adapter_profile.adapter_type}-{super()._llm_type}"

    def adapter_metadata(self) -> dict[str, Any]:
        return self.adapter_profile.model_dump()

    def _normalize_error(self, exc: Exception) -> Exception:
        return normalize_model_exception(
            exc,
            model_name=self.model_name,
            provider_name=self.provider_name,
            interface_type=self.adapter_profile.interface_type,
            adapter_type=self.adapter_profile.adapter_type,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        except Exception as exc:
            raise self._normalize_error(exc) from exc

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        except Exception as exc:
            raise self._normalize_error(exc) from exc

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ):
        try:
            yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)
        except Exception as exc:
            raise self._normalize_error(exc) from exc

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ):
        try:
            async for chunk in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
                yield chunk
        except Exception as exc:
            raise self._normalize_error(exc) from exc