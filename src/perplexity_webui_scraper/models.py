"""AI model definitions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """AI model configuration with metadata."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    tool_name: str
    identifier: str
    subscription_tier: str
    mode: str = "copilot"


MODELS: dict[str, Model] = {
    "best": Model(
        identifier="default",
        name="Pro",
        description="Automatically selects the most responsive model based on the query",
        mode="search",
        subscription_tier="pro",
        tool_name="pplx_ask",
    ),
    "deep-research": Model(
        identifier="pplx_alpha",
        name="Deep research",
        description="Fast and thorough for routine research",
        mode="research",
        subscription_tier="pro",
        tool_name="pplx_deep_research",
    ),
    "sonar": Model(
        identifier="experimental",
        name="Sonar",
        description="Perplexity's latest model",
        subscription_tier="pro",
        tool_name="pplx_sonar",
    ),
    "gemini-3-flash": Model(
        identifier="gemini30flash",
        name="Gemini 3 Flash",
        description="Google's fast model",
        subscription_tier="pro",
        tool_name="pplx_gemini_flash",
    ),
    "gemini-3-flash-thinking": Model(
        identifier="gemini30flash_high",
        name="Gemini 3 Flash Thinking",
        description="Google's fast model with thinking",
        subscription_tier="pro",
        tool_name="pplx_gemini_flash_think",
    ),
    "gemini-3.1-pro": Model(
        identifier="gemini31pro_low",
        name="Gemini 3.1 Pro",
        description="Google's latest model",
        subscription_tier="pro",
        tool_name="pplx_gemini31_pro",
    ),
    "gemini-3.1-pro-thinking": Model(
        identifier="gemini31pro_high",
        name="Gemini 3.1 Pro Thinking",
        description="Google's latest model with thinking",
        subscription_tier="pro",
        tool_name="pplx_gemini31_pro_think",
    ),
    "gpt-5.4": Model(
        identifier="gpt54",
        name="GPT-5.4",
        description="OpenAI's latest model",
        subscription_tier="pro",
        tool_name="pplx_gpt54",
    ),
    "gpt-5.4-thinking": Model(
        identifier="gpt54_thinking",
        name="GPT-5.4 Thinking",
        description="OpenAI's latest model with thinking",
        subscription_tier="pro",
        tool_name="pplx_gpt54_thinking",
    ),
    "claude-sonnet-4.6": Model(
        identifier="claude46sonnet",
        name="Claude Sonnet 4.6",
        description="Anthropic's fast model",
        subscription_tier="pro",
        tool_name="pplx_claude_s46",
    ),
    "claude-sonnet-4.6-thinking": Model(
        identifier="claude46sonnetthinking",
        name="Claude Sonnet 4.6 Thinking",
        description="Anthropic's newest reasoning model",
        subscription_tier="pro",
        tool_name="pplx_claude_s46_think",
    ),
    "claude-opus-4.6": Model(
        identifier="claude46opus",
        name="Claude Opus 4.6",
        description="Anthropic's most advanced model",
        subscription_tier="max",
        tool_name="pplx_claude_o46",
    ),
    "claude-opus-4.6-thinking": Model(
        identifier="claude46opusthinking",
        name="Claude Opus 4.6 Thinking",
        description="Anthropic's Opus reasoning model with thinking",
        subscription_tier="max",
        tool_name="pplx_claude_o46_think",
    ),
    "grok-4.1": Model(
        identifier="grok41nonreasoning",
        name="Grok 4.1",
        description="xAI's latest model",
        subscription_tier="pro",
        tool_name="pplx_grok41",
    ),
    "grok-4.1-thinking": Model(
        identifier="grok41reasoning",
        name="Grok 4.1 Thinking",
        description="xAI's latest model with thinking",
        subscription_tier="pro",
        tool_name="pplx_grok41_think",
    ),
    "kimi-k2.5-thinking": Model(
        identifier="kimik25thinking",
        name="Kimi K2.5 Thinking",
        description="Moonshot AI's latest model with thinking",
        subscription_tier="pro",
        tool_name="pplx_kimi_k25_think",
    ),
}


def _resolve_model(model_id: str) -> Model:
    """Resolve a model string ID to a Model instance.

    Raises:
        ValueError: If the model ID is not recognized.
    """

    model = MODELS.get(model_id)

    if model is None:
        available = ", ".join(f'"{k}"' for k in MODELS)
        msg = f"Unknown model {model_id!r}. Available models: {available}"

        raise ValueError(msg)

    return model
