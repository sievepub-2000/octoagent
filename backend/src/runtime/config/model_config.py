from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    """Config section for a model"""

    name: str = Field(..., description="Unique name for the model")
    display_name: str | None = Field(..., default_factory=lambda: None, description="Display name for the model")
    description: str | None = Field(..., default_factory=lambda: None, description="Description for the model")
    use: str | None = Field(
        default=None,
        description=("Optional class path of the model provider (for example: langchain_openai:ChatOpenAI). If omitted, OctoAgent will infer the default provider class from interface_type or provider_name."),
    )
    model: str = Field(..., description="Model name")
    model_config = ConfigDict(extra="allow")
    interface_type: str | None = Field(
        default=None,
        description=("Normalized provider interface/dialect. Preferred over vendor-specific `use` when using built-in integrations (for example: openai_compatible, anthropic_messages, google_genai, deepseek_reasoner)."),
    )
    provider_name: str | None = Field(
        default=None,
        description=("Optional provider/vendor label used for documentation and interface inference (for example: openai, openrouter, groq, ollama, anthropic, google, deepseek)."),
    )
    supports_thinking: bool = Field(default_factory=lambda: False, description="Whether the model supports thinking")
    supports_reasoning_effort: bool = Field(default_factory=lambda: False, description="Whether the model supports reasoning effort")
    when_thinking_enabled: dict | None = Field(
        default_factory=lambda: None,
        description="Extra settings to be passed to the model when thinking is enabled",
    )
    supports_vision: bool = Field(default_factory=lambda: False, description="Whether the model supports vision/image inputs")
    fallback_models: list[str] = Field(
        default_factory=list,
        description="Ordered backup model names to try when the primary model fails or exceeds its context/runtime limits.",
    )
    max_context_tokens: int | None = Field(
        default=None,
        description="Optional declared max context window for planning and fallback heuristics.",
    )
    provider_family: str | None = Field(
        default=None,
        description="Optional semantic provider family override (for example: openai, anthropic, google, deepseek).",
    )
    semantic_format: str | None = Field(
        default=None,
        description="Optional semantic content format override (for example: openai_chat, anthropic, generic).",
    )
    thinking: dict | None = Field(
        default_factory=lambda: None,
        description=(
            "Thinking settings for the model. If provided, these settings will be passed to the model when thinking is enabled. "
            "This is a shortcut for `when_thinking_enabled` and will be merged with `when_thinking_enabled` if both are provided."
        ),
    )

    def resolved_use(self) -> str:
        from src.models.interfaces import resolve_model_interface_profile

        if self.use:
            return self.use
        interface_profile = resolve_model_interface_profile(
            interface_type=self.interface_type,
            provider_name=self.provider_name,
            provider_family=self.provider_family,
        )
        if interface_profile.default_use:
            return interface_profile.default_use
        raise ValueError(f"Model {self.name} must define `use` or a known `interface_type`/`provider_name` so OctoAgent can resolve the provider class.") from None

    def resolved_interface_type(self) -> str:
        from src.models.interfaces import resolve_model_interface_profile

        return resolve_model_interface_profile(
            interface_type=self.interface_type,
            provider_name=self.provider_name,
            provider_family=self.provider_family,
            use_path=self.use,
        ).name
