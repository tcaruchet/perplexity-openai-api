#!/usr/bin/env python3
"""
Perplexity OpenAI-compatible API Server.

A production-ready OpenAI-compatible REST API server that proxies requests
to Perplexity AI using the perplexity-webui-scraper library.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
from typing import TYPE_CHECKING, Any, Literal, NamedTuple
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from perplexity_webui_scraper import (  # noqa: E402
    CitationMode,
    Conversation,
    ConversationConfig,
    Models,
    Perplexity,
    PerplexityError,
    PerplexityModelsFetcher,
)
from perplexity_webui_scraper.models import Model  # noqa: E402


if TYPE_CHECKING:
    from perplexity_webui_scraper.fetch_models import ModelInfo as FetchedModelInfo


LOGGER = logging.getLogger(__name__)
TOOL_CALL_RETRY_ATTEMPTS = 2
MODEL_REFRESH_INTERVAL_SECONDS = 3600
CONVERSATION_CLEANUP_INTERVAL_SECONDS = 300
MAX_UPSTREAM_QUERY_CHARS = 12000
MESSAGE_HISTORY_BUDGET_RATIO = 0.55


# =============================================================================
# Configuration
# =============================================================================


@dataclass(slots=True)
class ServerConfig:
    """Server configuration loaded from environment variables."""

    session_token: str
    api_key: str | None = None
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    requests_per_minute: int = 60
    enable_rate_limiting: bool = True
    conversation_timeout: int = 3600
    max_conversations_per_user: int = 100
    default_model: str = "perplexity-auto"
    default_citation_mode: CitationMode = CitationMode.CLEAN

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Load configuration from environment variables."""
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        session_token = os.getenv("PERPLEXITY_SESSION_TOKEN")
        if not session_token:
            raise RuntimeError(
                "PERPLEXITY_SESSION_TOKEN environment variable is required. "
                "Get it from Perplexity cookies: __Secure-next-auth.session-token."
            )

        return cls(
            session_token=session_token,
            api_key=os.getenv("OPENAI_API_KEY"),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            requests_per_minute=int(os.getenv("REQUESTS_PER_MINUTE", "60")),
            enable_rate_limiting=os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true",
            conversation_timeout=int(os.getenv("CONVERSATION_TIMEOUT", "3600")),
            max_conversations_per_user=int(os.getenv("MAX_CONVERSATIONS_PER_USER", "100")),
            default_model=os.getenv("DEFAULT_MODEL", "perplexity-auto"),
            default_citation_mode=CitationMode[os.getenv("DEFAULT_CITATION_MODE", "CLEAN").upper()],
        )


# =============================================================================
# Dynamic Model Registry
# =============================================================================


class ModelRegistry:
    """Manage available models fetched from Perplexity."""

    def __init__(self) -> None:
        self._models: list[FetchedModelInfo] = []
        self._mapping: dict[str, Model] = {}
        self._available: list[dict[str, str]] = []
        self._last_fetch: datetime | None = None

    def fetch(self, session_token: str) -> None:
        """Fetch available models from Perplexity."""
        LOGGER.info("Fetching models from Perplexity")

        try:
            with PerplexityModelsFetcher(session_token) as fetcher:
                self._models = fetcher.fetch_models()

            self._build_mappings()
            self._last_fetch = datetime.now()
            LOGGER.info("Loaded %s models", len(self._models))
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Failed to fetch models: %s", exc)
            self._use_defaults()

    def _build_mappings(self) -> None:
        self._mapping = {
            "gpt-4": Models.BEST,
            "gpt-4-turbo": Models.BEST,
            "gpt-4o": Models.BEST,
            "perplexity": Models.BEST,
            "perplexity-auto": Models.BEST,
            "auto": Models.BEST,
            "perplexity-sonar": Models.SONAR,
            "perplexity-research": Models.RESEARCH,
            "perplexity-labs": Models.LABS,
            "sonar": Models.SONAR,
            "research": Models.RESEARCH,
            "labs": Models.LABS,
        }

        self._available = [
            {"id": "perplexity-auto", "name": "Perplexity Auto", "owned_by": "perplexity"},
            {"id": "perplexity-sonar", "name": "Perplexity Sonar", "owned_by": "perplexity"},
            {"id": "perplexity-research", "name": "Perplexity Research", "owned_by": "perplexity"},
            {"id": "perplexity-labs", "name": "Perplexity Labs", "owned_by": "perplexity"},
        ]

        for model in self._models:
            model_obj = Model(identifier=model.identifier, mode=model.mode)
            self._mapping[model.identifier.lower()] = model_obj

            for alias in self._generate_aliases(model.identifier):
                self._mapping[alias.lower()] = model_obj

            if not any(item["id"] == model.identifier for item in self._available):
                self._available.append(
                    {
                        "id": model.identifier,
                        "name": model.name,
                        "owned_by": model.provider.lower(),
                    }
                )

    def _generate_aliases(self, identifier: str) -> list[str]:
        aliases: list[str] = []
        id_lower = identifier.lower()

        if id_lower.startswith("gpt"):
            match = re.match(r"gpt(\d)(\d)", id_lower)
            if match:
                aliases.extend(
                    [
                        f"gpt-{match.group(1)}.{match.group(2)}",
                        f"gpt-{match.group(1)}{match.group(2)}",
                    ]
                )
        elif id_lower.startswith("claude"):
            if "opus" in id_lower:
                match = re.search(r"opus(\d+)", id_lower)
                if match:
                    version = match.group(1)
                    aliases.append(
                        f"claude-opus-{version[0]}.{version[1:]}" if len(version) > 1 else f"claude-opus-{version}"
                    )
            elif "sonnet" in id_lower:
                match = re.search(r"(\d+)sonnet", id_lower)
                if match:
                    version = match.group(1)
                    aliases.append(
                        f"claude-{version[0]}.{version[1:]}-sonnet"
                        if len(version) > 1
                        else f"claude-{version}-sonnet"
                    )
        elif id_lower.startswith("gemini"):
            match = re.search(r"gemini(\d+)pro", id_lower)
            if match:
                version = match.group(1)
                aliases.extend([f"gemini-{version[0]}-pro", f"gemini-{version}-pro"])
        elif id_lower.startswith("grok"):
            match = re.search(r"grok(\d+)", id_lower)
            if match:
                version = match.group(1)
                aliases.append(f"grok-{version[0]}.{version[1:]}" if len(version) > 1 else f"grok-{version}")

        if "thinking" in id_lower:
            aliases.extend([f"{alias}-thinking" for alias in aliases])

        return aliases

    def _use_defaults(self) -> None:
        self._models = []
        self._mapping = {
            "perplexity-auto": Models.BEST,
            "perplexity-sonar": Models.SONAR,
            "perplexity-research": Models.RESEARCH,
            "perplexity-labs": Models.LABS,
            "auto": Models.BEST,
        }
        self._available = [
            {"id": "perplexity-auto", "name": "Perplexity Auto", "owned_by": "perplexity"},
            {"id": "perplexity-sonar", "name": "Perplexity Sonar", "owned_by": "perplexity"},
            {"id": "perplexity-research", "name": "Perplexity Research", "owned_by": "perplexity"},
            {"id": "perplexity-labs", "name": "Perplexity Labs", "owned_by": "perplexity"},
        ]

    def get(self, name: str) -> Model:
        key = name.lower().strip()
        if key in self._mapping:
            return self._mapping[key]
        LOGGER.warning("Unknown model '%s', using default", name)
        return Models.BEST

    def list_available(self) -> list[dict[str, str]]:
        return self._available

    def needs_refresh(self) -> bool:
        if not self._last_fetch:
            return True
        return (datetime.now() - self._last_fetch).total_seconds() > MODEL_REFRESH_INTERVAL_SECONDS


# =============================================================================
# Conversation Manager
# =============================================================================


@dataclass(slots=True)
class ConversationSession:
    """Active conversation session."""

    conversation: Conversation
    created_at: datetime
    last_used: datetime
    user_id: str | None = None
    model: str = "perplexity-auto"
    message_count: int = 0


class ConversationManager:
    """Manage persistent conversations with automatic cleanup."""

    def __init__(self, client: Perplexity, timeout: int, max_per_user: int) -> None:
        self._client = client
        self._timeout = timeout
        self._max_per_user = max_per_user
        self._sessions: dict[str, ConversationSession] = {}
        self._cleanup_task: asyncio.Task[None] | None = None

    def start_cleanup(self) -> None:
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._cleanup_task

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(CONVERSATION_CLEANUP_INTERVAL_SECONDS)
            now = datetime.now()
            expired = [
                cid
                for cid, sess in self._sessions.items()
                if (now - sess.last_used).total_seconds() > self._timeout
            ]
            for cid in expired:
                del self._sessions[cid]
            if expired:
                LOGGER.info("Cleaned up %s expired conversations", len(expired))

    def get_or_create(
        self,
        conversation_id: str | None,
        user_id: str | None,
        model: str,
        citation_mode: CitationMode,
    ) -> tuple[str, ConversationSession]:
        if conversation_id and conversation_id in self._sessions:
            session = self._sessions[conversation_id]
            session.last_used = datetime.now()
            session.message_count += 1
            return conversation_id, session

        if user_id:
            user_sessions = [session for session in self._sessions.values() if session.user_id == user_id]
            if len(user_sessions) >= self._max_per_user:
                oldest = min(user_sessions, key=lambda item: item.last_used)
                for cid, session in list(self._sessions.items()):
                    if session is oldest:
                        del self._sessions[cid]
                        break

        config = ConversationConfig(citation_mode=citation_mode)
        conversation = self._client.create_conversation(config)
        new_id = conversation_id or str(uuid.uuid4())

        session = ConversationSession(
            conversation=conversation,
            created_at=datetime.now(),
            last_used=datetime.now(),
            user_id=user_id,
            model=model,
        )
        self._sessions[new_id] = session
        return new_id, session

    def list_sessions(self, user_id: str | None) -> list[dict[str, Any]]:
        result = []
        for cid, session in self._sessions.items():
            if not user_id or session.user_id == user_id:
                result.append(
                    {
                        "id": cid,
                        "created_at": session.created_at.isoformat(),
                        "last_used": session.last_used.isoformat(),
                        "message_count": session.message_count,
                        "model": session.model,
                    }
                )
        return sorted(result, key=lambda item: item["last_used"], reverse=True)

    def delete(self, conversation_id: str, user_id: str | None) -> bool:
        if conversation_id not in self._sessions:
            return False

        session = self._sessions[conversation_id]
        if user_id and session.user_id and session.user_id != user_id:
            return False

        del self._sessions[conversation_id]
        return True

    def get_stats(self) -> dict[str, int]:
        return {
            "total": len(self._sessions),
            "users": len({session.user_id for session in self._sessions.values() if session.user_id}),
            "messages": sum(session.message_count for session in self._sessions.values()),
        }

    def close(self) -> None:
        self._client.close()


# =============================================================================
# Pydantic Models
# =============================================================================


class FunctionDefinition(BaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, Any] | None = None


class ToolDefinition(BaseModel):
    type: Literal["function"] = "function"
    function: FunctionDefinition


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: dict[str, Any]


class ChatMessage(BaseModel):
    role: str
    content: str | None = None
    name: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None


class ResponseFormat(BaseModel):
    type: Literal["text", "json_object", "json_schema"] = "text"
    json_schema: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    model: str = "perplexity-auto"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    user: str | None = None
    conversation_id: str | None = None
    citation_mode: str | None = None
    tools: list[ToolDefinition] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: ResponseFormat | None = None
    strict: bool | None = None


class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None = "stop"


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: Usage


class ChunkChoice(BaseModel):
    index: int
    delta: dict[str, Any]
    finish_reason: str | None = None


class ChatChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChunkChoice]


class ModelItem(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelsResponse(BaseModel):
    object: str = "list"
    data: list[ModelItem]


# =============================================================================
# Global State
# =============================================================================


config: ServerConfig
models: ModelRegistry
manager: ConversationManager
start_time: datetime
request_count = 0


# =============================================================================
# Application
# =============================================================================


config = ServerConfig.from_env()

logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    global manager, models, start_time

    start_time = datetime.now()

    models = ModelRegistry()
    models.fetch(config.session_token)

    client = Perplexity(session_token=config.session_token)
    manager = ConversationManager(client, config.conversation_timeout, config.max_conversations_per_user)
    manager.start_cleanup()

    if config.enable_rate_limiting:
        limiter = Limiter(
            key_func=get_remote_address,
            default_limits=[f"{config.requests_per_minute}/minute"],
        )
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    LOGGER.info("Server starting on http://%s:%s", config.host, config.port)
    LOGGER.info("Models loaded: %s", len(models._models))
    LOGGER.info("Rate limiting: %s", "Enabled" if config.enable_rate_limiting else "Disabled")
    LOGGER.info("Auth required: %s", "Yes" if config.api_key else "No")

    yield

    await manager.stop_cleanup()
    manager.close()


app = FastAPI(
    title="Perplexity OpenAI API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if config.enable_rate_limiting:
    app.add_middleware(SlowAPIMiddleware)


# =============================================================================
# Helpers
# =============================================================================


def build_startup_error_message() -> str:
    return (
        "PERPLEXITY_SESSION_TOKEN environment variable is required.\n\n"
        "To get your session token:\n"
        "1. Log in at https://www.perplexity.ai\n"
        "2. Open DevTools (F12) → Application → Cookies\n"
        "3. Copy the '__Secure-next-auth.session-token' value\n"
        "4. Set it: export PERPLEXITY_SESSION_TOKEN='your_token'"
    )


def verify_auth(request: Request) -> str | None:
    """Verify API key and return user ID hash."""
    if not config.api_key:
        return None

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and auth[7:] == config.api_key:
        return hashlib.sha256(auth[7:].encode()).hexdigest()[:16]

    raise HTTPException(status_code=401, detail="Invalid API key")


def get_user(request: Request) -> str | None:
    """Get user identifier from request."""
    try:
        return verify_auth(request)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        return request.headers.get("X-User-ID")


def append_tool_prompt(parts: list[str], tools: list[ToolDefinition], tool_choice: str | dict[str, Any] | None) -> None:
    """Append tool instructions to the prompt."""
    sections = [
        "# AVAILABLE TOOLS",
        "",
        (
            "You are an AI assistant with access to the following tools. "
            "When you need to use a tool, you MUST respond with ONLY a JSON object "
            "in this exact format (no other text):"
        ),
        "",
        '```json\n{\n  "function_call": {\n    "name": "function_name",\n    "arguments": {"param1": "value1", "param2": "value2"}\n  }\n}\n```',
        "",
        "## Available Tools:",
        "",
    ]

    for tool in tools:
        func = tool.function
        sections.append(f"### {func.name}")
        if func.description:
            sections.append(f"Description: {func.description}")
        if func.parameters:
            sections.append("Parameters:")
            sections.append(f"```json\n{json.dumps(func.parameters, indent=2)}\n```")
        sections.append("")

    sections.append("## Critical Instructions:")
    sections.append("")

    if tool_choice in {"required", "any"}:
        sections.extend(
            [
                "You MUST call a tool. This is mandatory.",
                "Return ONLY the JSON function_call object and nothing else.",
                "Do not explain, do not answer normally, do not add markdown.",
            ]
        )
    elif isinstance(tool_choice, dict) and "function" in tool_choice:
        required_func = tool_choice["function"]["name"]
        sections.extend(
            [
                f"You MUST call the tool '{required_func}'.",
                "Return ONLY the JSON function_call object and nothing else.",
            ]
        )
    else:
        sections.extend(
            [
                "Use tools when the request requires current, computed, or external data.",
                "When using a tool, return ONLY the JSON function_call object.",
            ]
        )

    parts.append("\n".join(sections))


def append_response_format_prompt(parts: list[str], response_format: ResponseFormat) -> None:
    """Append structured output instructions to the prompt."""
    if response_format.type == "json_object":
        parts.append(
            "IMPORTANT: You must respond with a valid JSON object. "
            "Do not include any text outside the JSON structure."
        )
        return

    if response_format.type == "json_schema" and response_format.json_schema:
        schema_info = response_format.json_schema
        schema_obj = schema_info.get("schema", {}) if isinstance(schema_info, dict) else {}
        properties = schema_obj.get("properties", {})

        prompt_parts = [
            "CRITICAL INSTRUCTION:",
            "You MUST respond with ACTUAL DATA matching the schema below.",
            "DO NOT return the schema definition itself.",
            "ONLY return the data object.",
            "",
            f"Schema:\n{json.dumps(response_format.json_schema, indent=2)}",
            "",
            "Correct response example:",
        ]

        example_data: dict[str, Any] = {}
        for prop_name, prop_info in properties.items():
            prop_type = prop_info.get("type", "string")
            prop_desc = prop_info.get("description", "")
            label = prop_desc or prop_name

            if prop_type == "string":
                example_data[prop_name] = f"<extract {label} here>"
            elif prop_type in {"number", "integer"}:
                example_data[prop_name] = 42
            elif prop_type == "boolean":
                example_data[prop_name] = True
            elif prop_type == "array":
                example_data[prop_name] = ["item1", "item2"]
            else:
                example_data[prop_name] = f"<{prop_name} value>"

        if not example_data:
            example_data = {"field": "value"}

        prompt_parts.append(f"```json\n{json.dumps(example_data, indent=2)}\n```")
        parts.append("\n".join(prompt_parts))


def _truncate_text(value: str, max_chars: int) -> str:
    """Truncate text while preserving both the head and tail when possible."""
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    if max_chars <= 12:
        return value[:max_chars]

    head_budget = max_chars // 2
    tail_budget = max_chars - head_budget - 5
    if tail_budget <= 0:
        return value[: max_chars - 3] + "..."

    return f"{value[:head_budget]} ... {value[-tail_budget:]}"


def _compact_json(value: Any) -> str:
    """Serialize JSON in compact form for upstream prompt budgets."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _compact_tool_parameters(parameters: dict[str, Any] | None, budget: int = 600) -> str:
    """Compact a tool schema while preserving the most important constraints."""
    if not parameters:
        return "{}"

    compacted = {
        "type": parameters.get("type", "object"),
        "required": parameters.get("required", []),
        "properties": {},
    }

    properties = parameters.get("properties", {})
    if isinstance(properties, dict):
        for name, info in properties.items():
            if not isinstance(info, dict):
                continue
            property_payload: dict[str, Any] = {}
            if "type" in info:
                property_payload["type"] = info["type"]
            if "enum" in info:
                property_payload["enum"] = info["enum"]
            if "description" in info and isinstance(info["description"], str):
                property_payload["description"] = _truncate_text(info["description"], 120)
            compacted["properties"][name] = property_payload

    serialized = _compact_json(compacted)
    if len(serialized) <= budget:
        return serialized

    reduced = {
        "type": compacted["type"],
        "required": compacted["required"],
        "properties": {
            name: {key: value for key, value in info.items() if key in {"type", "enum"}}
            for name, info in compacted["properties"].items()
        },
    }
    serialized = _compact_json(reduced)
    if len(serialized) <= budget:
        return serialized

    minimal = {
        "required": compacted["required"],
        "properties": list(compacted["properties"].keys()),
    }
    return _truncate_text(_compact_json(minimal), budget)


def _build_tool_prompt_section(
    tools: list[ToolDefinition],
    tool_choice: str | dict[str, Any] | None,
    max_chars: int,
) -> str:
    """Build a compact tool instruction section for long upstream prompts."""
    sections = [
        "# AVAILABLE TOOLS",
        "When a tool is needed, respond only with JSON.",
        'Preferred formats: {"function_call":{"name":"tool_name","arguments":{...}}} or {"name":"tool_name","arguments":{...}}.',
        "Available tools:",
    ]

    per_tool_budget = max(180, min(700, max_chars // max(1, len(tools))))
    for tool in tools:
        func = tool.function
        description = _truncate_text(func.description or "", 160)
        parameters = _compact_tool_parameters(func.parameters, budget=per_tool_budget)
        line = f"- {func.name}"
        if description:
            line += f": {description}"
        line += f" | schema={parameters}"
        sections.append(_truncate_text(line, per_tool_budget + 80))

    if tool_choice in {"required", "any"}:
        sections.append("Tool use is mandatory.")
    elif isinstance(tool_choice, dict) and "function" in tool_choice:
        required_func = tool_choice["function"]["name"]
        sections.append(f"Tool use is mandatory. Required tool: {required_func}.")
    else:
        sections.append("Use tools only when necessary.")

    return _truncate_text("\n".join(sections), max_chars)


def _build_response_format_section(response_format: ResponseFormat, max_chars: int) -> str:
    """Build a compact structured-output section for upstream prompts."""
    if response_format.type == "json_object":
        return "Return only a valid JSON object with no extra text."

    if response_format.type == "json_schema" and response_format.json_schema:
        schema_info = response_format.json_schema
        schema_obj = schema_info.get("schema", {}) if isinstance(schema_info, dict) else {}
        properties = schema_obj.get("properties", {}) if isinstance(schema_obj, dict) else {}
        required = schema_obj.get("required", []) if isinstance(schema_obj, dict) else []

        compact_schema = {
            "name": schema_info.get("name") if isinstance(schema_info, dict) else None,
            "strict": schema_info.get("strict") if isinstance(schema_info, dict) else None,
            "required": required,
            "properties": {},
        }
        if isinstance(properties, dict):
            for name, info in properties.items():
                if not isinstance(info, dict):
                    continue
                compact_schema["properties"][name] = {
                    key: value
                    for key, value in info.items()
                    if key in {"type", "enum", "description"}
                }

        return _truncate_text(
            "Return only data matching this schema: " + _compact_json(compact_schema),
            max_chars,
        )

    return ""


def _message_to_query_fragment(message: ChatMessage, max_chars: int) -> list[str]:
    """Convert a message into compact upstream prompt fragments."""
    fragments: list[str] = []

    if message.role == "user":
        fragments.append(f"User: {_truncate_text(message.content or '', max_chars)}")
    elif message.role == "assistant":
        if message.tool_calls:
            for tool_call in message.tool_calls:
                fragments.append(
                    _truncate_text(
                        f"Assistant called tool: {tool_call.function.get('name', 'unknown')}",
                        max_chars,
                    )
                )
                fragments.append(
                    _truncate_text(
                        f"Arguments: {tool_call.function.get('arguments', '{}')}",
                        max_chars,
                    )
                )
        elif message.content:
            fragments.append(f"Assistant: {_truncate_text(message.content, max_chars)}")
    elif message.role == "tool":
        tool_result = _truncate_text(message.content or "", max_chars)
        fragments.append(f"Tool result ({message.tool_call_id}): {tool_result}")

    return fragments


def _append_recent_history_with_budget(
    parts: list[str],
    messages: list[ChatMessage],
    budget: int,
) -> None:
    """Append recent, higher.content}")

    return "\n\n".join(parts)


def estimate_tokens(text: str) -> int:
    """Estimate token count."""
    return len(text) // 4


def is_required_tool_choice(tool_choice: str | dict[str, Any] | None) -> bool:
    """Check whether the request requires a tool call."""
    return tool_choice in {"required", "any"} or (isinstance(tool_choice, dict) and "function" in tool_choice)


def is_strict_response_format(body: ChatRequest) -> bool:
    """Check whether structured output should be enforced strictly."""
    if body.strict is not None:
        return body.strict

    if not body.response_format:
        return False

    if body.response_format.type == "json_object":
        return True

    if body.response_format.type == "json_schema" and body.response_format.json_schema:
        strict = body.response_format.json_schema.get("strict")
        return bool(strict)

    return False


def build_openai_error(
    message: str,
    error_type: str,
    param: str | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    """Build an OpenAI-style error payload."""
    return {
        "error": {
            "message": message,
            "type": error_type,
            "param": param,
            "code": code,
        }
    }


def parse_citation_mode(mode: str | None) -> CitationMode:
    """Parse citation mode string."""
    if not mode:
        return config.default_citation_mode
    try:
        return CitationMode[mode.upper()]
    except KeyError:
        return config.default_citation_mode


def decide_tool_usage(messages: list[ChatMessage], tools: list[ToolDefinition]) -> str:
    """Create a decision prompt for optional tool use."""
    user_messages = [message for message in messages if message.role == "user"]
    if not user_messages:
        return "Should tools be used? Answer yes or no."

    last_message = user_messages[-1].content or ""
    tool_descriptions = [f"- {tool.function.name}: {tool.function.description}" for tool in tools]

    return (
        "You have access to these tools:\n"
        f"{chr(10).join(tool_descriptions)}\n\n"
        f'User request: "{last_message}"\n\n'
        "Does this request require one of the tools to provide accurate, current, or computed information?\n\n"
        'Answer ONLY with one word: "yes" or "no"\n'
    )


def should_use_tool(decision: str, tools: list[ToolDefinition]) -> bool:
    """Decide if a tool should be used based on model analysis."""
    normalized = decision.lower().strip()

    if normalized.startswith("yes"):
        return True
    if normalized.startswith("no"):
        return False

    for tool in tools:
        if tool.function.name.lower() in normalized:
            return True

    positive_words = ["should", "need", "require", "use", "call", "invoke"]
    return any(word in normalized for word in positive_words) and "not" not in normalized and "no" not in normalized


def _extract_json_candidates(text: str) -> list[str]:
    """Extract possible JSON substrings from a text response."""
    candidates: list[str] = []
    stripped = text.strip()
    if stripped:
        candidates.append(stripped)

    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text):
        block = match.group(1).strip()
        if block:
            candidates.append(block)

    brace_count = 0
    start_idx = -1
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue

        if char == "\\" and in_string:
            escaped = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            if brace_count == 0:
                start_idx = index
            brace_count += 1
        elif char == "}" and brace_count > 0:
            brace_count -= 1
            if brace_count == 0 and start_idx != -1:
                candidate = text[start_idx : index + 1].strip()
                if candidate:
                    candidates.append(candidate)
                start_idx = -1

    unique_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)

    return unique_candidates


def _parse_json_candidate(candidate: str) -> Any | None:
    """Parse JSON candidate safely."""
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _validate_tool_arguments_shape(value: Any) -> Any:
    """Normalize tool arguments to JSON-safe structures."""
    if isinstance(value, dict):
        return {str(key): _validate_tool_arguments_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_validate_tool_arguments_shape(item) for item in value]
    if isinstance(value, tuple):
        return [_validate_tool_arguments_shape(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _coerce_schema_value(value: Any, schema: dict[str, Any]) -> Any:
    """Best-effort coercion of value to schema."""
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), schema_type[0] if schema_type else None)

    if value is None:
        return None

    if schema_type == "object":
        if not isinstance(value, dict):
            return None
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        result: dict[str, Any] = {}
        for key, prop_schema in properties.items():
            if key in value:
                coerced = _coerce_schema_value(value[key], prop_schema)
                if coerced is not None:
                    result[key] = coerced
        for key in required:
            if key not in result and key in value:
                result[key] = value[key]
        return result or value

    if schema_type == "array":
        if not isinstance(value, list):
            return None
        item_schema = schema.get("items", {})
        return [_coerce_schema_value(item, item_schema) for item in value]

    if schema_type == "string":
        return value if isinstance(value, str) else str(value)

    if schema_type == "integer":
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            with suppress(ValueError):
                return int(value.strip())
        return None

    if schema_type == "number":
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            with suppress(ValueError):
                return float(value.strip())
        return None

    if schema_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1"}:
                return True
            if lowered in {"false", "no", "0"}:
                return False
        return None

    return value


def _validate_tool_arguments_against_schema(arguments: Any, schema: dict[str, Any] | None) -> Any:
    """Best-effort validation of tool arguments against tool schema."""
    normalized = _validate_tool_arguments_shape(arguments)
    if schema is None:
        return normalized
    coerced = _coerce_schema_value(normalized, schema)
    return normalized if coerced is None else coerced


def _normalize_tool_arguments(arguments: Any) -> str:
    """Normalize tool arguments to an OpenAI-compatible JSON string."""
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            normalized = _validate_tool_arguments_shape(parsed)
            return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
        except json.JSONDecodeError:
            return json.dumps({"value": arguments}, ensure_ascii=False, separators=(",", ":"))

    if arguments is None:
        return "{}"

    if isinstance(arguments, (dict, list, int, float, bool)):
        normalized = _validate_tool_arguments_shape(arguments)
        return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))

    return json.dumps({"value": arguments}, ensure_ascii=False, separators=(",", ":"))


class ToolCandidate(NamedTuple):
    """Normalized tool-call candidate with confidence score."""

    name: str
    arguments: Any
    confidence: float
    source: str


def _extract_function_call(parsed: Any) -> dict[str, Any] | None:
    """Extract function call payload from parsed JSON."""
    if not isinstance(parsed, dict):
        return None

    if isinstance(parsed.get("function_call"), dict):
        return parsed["function_call"]

    if "name" in parsed and "arguments" in parsed:
        return parsed

    tool_calls = parsed.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        first_call = tool_calls[0]
        if isinstance(first_call, dict):
            function_data = first_call.get("function")
            if isinstance(function_data, dict) and "name" in function_data:
                return {
                    "name": function_data.get("name", ""),
                    "arguments": function_data.get("arguments", {}),
                }

    return None


def _find_tool_schema(tools: list[ToolDefinition] | None, tool_name: str) -> dict[str, Any] | None:
    """Find schema for a tool name."""
    if not tools:
        return None

    normalized_name = tool_name.strip().lower()
    for tool in tools:
        if tool.function.name.strip().lower() == normalized_name:
            return tool.function.parameters
    return None


def _find_tool_definition(tools: list[ToolDefinition] | None, tool_name: str) -> ToolDefinition | None:
    """Find a tool definition by normalized name."""
    if not tools:
        return None

    normalized_name = tool_name.strip().lower()
    for tool in tools:
        if tool.function.name.strip().lower() == normalized_name:
            return tool
    return None


def _candidate_from_function_call_data(
    function_call_data: dict[str, Any],
    confidence: float,
    source: str,
    tools: list[ToolDefinition] | None,
) -> ToolCandidate | None:
    """Convert loosely-structured function call data into a candidate."""
    raw_name = function_call_data.get("name", "")
    if not isinstance(raw_name, str) or not raw_name.strip():
        return None

    tool_definition = _find_tool_definition(tools, raw_name)
    if tool_definition is None:
        return None

    raw_arguments = function_call_data.get("arguments", {})
    if isinstance(raw_arguments, str):
        stripped = raw_arguments.strip()
        if stripped:
            parsed_arguments = _parse_json_candidate(stripped)
            raw_arguments = parsed_arguments if parsed_arguments is not None else raw_arguments
        else:
            raw_arguments = {}

    return ToolCandidate(
        name=tool_definition.function.name,
        arguments=raw_arguments,
        confidence=confidence,
        source=source,
    )


def _extract_named_tool_json_candidates(answer: str, tools: list[ToolDefinition]) -> list[ToolCandidate]:
    """Extract likely tool calls from JSON fragments and direct tool-name mentions."""
    candidates: list[ToolCandidate] = []

    for candidate_text in _extract_json_candidates(answer):
        parsed = _parse_json_candidate(candidate_text)
        if parsed is None:
            continue

        function_call_data = _extract_function_call(parsed)
        if function_call_data:
            candidate = _candidate_from_function_call_data(
                function_call_data,
                1.0,
                "function_call_json",
                tools,
            )
            if candidate is not None:
                candidates.append(candidate)
                continue

        if isinstance(parsed, dict):
            for tool in tools:
                tool_name = tool.function.name
                arguments = parsed.get(tool_name)
                if arguments is None:
                    continue
                candidates.append(
                    ToolCandidate(
                        name=tool_name,
                        arguments=arguments,
                        confidence=0.82,
                        source="named_tool_json",
                    )
                )

    lowered_answer = answer.lower()
    for tool in tools:
        if tool.function.name.lower() not in lowered_answer:
            continue

        tool_schema = tool.function.parameters or {}
        schema_type = tool_schema.get("type")
        properties = tool_schema.get("properties", {}) if isinstance(tool_schema, dict) else {}
        if schema_type != "object" or not isinstance(properties, dict):
            continue

        inferred_arguments: dict[str, Any] = {}
        if "city" in properties:
            city_match = re.search(r"\b(?:for|in)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)", answer)
            if city_match:
                inferred_arguments["city"] = city_match.group(1).strip()

        if "unit" in properties:
            unit_match = re.search(r"\b(celsius|fahrenheit)\b", lowered_answer)
            if unit_match:
                inferred_arguments["unit"] = unit_match.group(1)

        if inferred_arguments:
            candidates.append(
                ToolCandidate(
                    name=tool.function.name,
                    arguments=inferred_arguments,
                    confidence=0.62,
                    source="tool_name_inference",
                )
            )

    return candidates


def _select_best_tool_candidate(answer: str, tools: list[ToolDefinition]) -> ToolCandidate | None:
    """Choose the best tool-call candidate from a noisy browser-model response."""
    candidates = _extract_named_tool_json_candidates(answer, tools)
    if not candidates:
        return None

    return max(candidates, key=lambda item: item.confidence)


def _build_tool_message(
    candidate: ToolCandidate,
    tools: list[ToolDefinition] | None = None,
) -> tuple[ChatMessage, str] | None:
    """Build OpenAI-compatible tool call response."""
    if candidate.confidence < 0.6:
        return None

    tool_schema = _find_tool_schema(tools, candidate.name)
    validated_arguments = _validate_tool_arguments_against_schema(
        candidate.arguments,
        tool_schema,
    )

    tool_call = ToolCall(
        id=f"call_{uuid.uuid4().hex[:24]}",
        type="function",
        function={
            "name": candidate.name,
            "arguments": _normalize_tool_arguments(validated_arguments),
        },
    )

    return (
        ChatMessage(role="assistant", content=None, tool_calls=[tool_call]),
        "tool_calls",
    )


def _extract_structured_output(answer: str, response_format: ResponseFormat) -> str | None:
    """Extract and normalize structured output."""
    candidates = _extract_json_candidates(answer)

    if response_format.type == "json_object":
        for candidate in candidates:
            parsed = _parse_json_candidate(candidate)
            if isinstance(parsed, dict):
                return json.dumps(parsed, ensure_ascii=False)
        return None

    if response_format.type == "json_schema" and response_format.json_schema:
        schema_info = response_format.json_schema
        schema = schema_info.get("schema", schema_info) if isinstance(schema_info, dict) else {}
        if not isinstance(schema, dict):
            return None

        schema_name = schema_info.get("name") if isinstance(schema_info, dict) else None

        for candidate in candidates:
            parsed = _parse_json_candidate(candidate)
            if not isinstance(parsed, dict):
                continue

            if "schema" in parsed and isinstance(parsed.get("schema"), dict) and "properties" in parsed["schema"]:
                continue

            if schema_name and parsed.get("name") == schema_name and "schema" in parsed:
                continue

            coerced = _coerce_schema_value(parsed, schema)
            if isinstance(coerced, dict):
                return json.dumps(coerced, ensure_ascii=False)

    return None


def parse_response(
    answer: str,
    tools: list[ToolDefinition] | None = None,
    response_format: ResponseFormat | None = None,
) -> tuple[ChatMessage, str, bool, bool]:
    """Parse response to extract tool calls or validate structured output."""
    LOGGER.info("parse_response called with tools=%s answer_length=%s", tools is not None, len(answer))
    LOGGER.debug("Answer content: %s", answer[:200])

    if tools:
        try:
            candidate = _select_best_tool_candidate(answer, tools)
            if candidate is not None:
                tool_result = _build_tool_message(candidate, tools)
                if tool_result:
                    message, finish_reason = tool_result
                    LOGGER.info(
                        "Successfully extracted tool call: %s via %s (confidence=%.2f)",
                        candidate.name,
                        candidate.source,
                        candidate.confidence,
                    )
                    return message, finish_reason, True, False
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Error parsing tool calls: %s", exc, exc_info=True)

    if response_format and response_format.type in {"json_object", "json_schema"}:
        normalized_json = _extract_structured_output(answer, response_format)
        if normalized_json is not None:
            return ChatMessage(role="assistant", content=normalized_json), "stop", False, True

        LOGGER.warning("Requested %s but response is not valid JSON", response_format.type)
        return ChatMessage(role="assistant", content=answer), "stop", False, False

    LOGGER.info("No tool calls or structured output found, returning content as-is")
    return ChatMessage(role="assistant", content=answer), "stop", False, True


def build_stream_chunk(
    response_id: str,
    created: int,
    model_name: str,
    delta: dict[str, Any],
    finish_reason: str | None = None,
) -> str:
    """Build a single SSE chat completion chunk."""
    chunk = ChatChunk(
        id=response_id,
        created=created,
        model=model_name,
        choices=[ChunkChoice(index=0, delta=delta, finish_reason=finish_reason)],
    )
    return f"data: {chunk.model_dump_json()}\n\n"


def split_string_for_streaming(value: str, chunk_size: int = 32) -> list[str]:
    """Split a string into smaller chunks for SSE tool call streaming."""
    if not value:
        return []
    return [value[index : index + chunk_size] for index in range(0, len(value), chunk_size)]


def stream_tool_call_chunks(
    response_id: str,
    created: int,
    model_name: str,
    message: ChatMessage,
) -> list[str]:
    """Build OpenAI-style streaming chunks for tool calls."""
    chunks = [build_stream_chunk(response_id, created, model_name, {"role": "assistant"})]

    if not message.tool_calls:
        return chunks

    for index, tool_call in enumerate(message.tool_calls):
        function_name = str(tool_call.function.get("name", ""))
        arguments = str(tool_call.function.get("arguments", "{}"))

        chunks.append(
            build_stream_chunk(
                response_id,
                created,
                model_name,
                {
                    "tool_calls": [
                        {
                            "index": index,
                            "id": tool_call.id,
                            "type": "function",
                            "function": {"name": function_name, "arguments": ""},
                        }
                    ]
                },
            )
        )

        for argument_chunk in split_string_for_streaming(arguments):
            chunks.append(
                build_stream_chunk(
                    response_id,
                    created,
                    model_name,
                    {
                        "tool_calls": [
                            {
                                "index": index,
                                "function": {"arguments": argument_chunk},
                            }
                        ]
                    },
                )
            )

    chunks.append(build_stream_chunk(response_id, created, model_name, {}, "tool_calls"))
    chunks.append("data: [DONE]\n\n")
    return chunks


def build_nonstream_response(
    body: ChatRequest,
    response_id: str,
    created: int,
    message: ChatMessage,
    finish_reason: str,
    query: str,
    answer: str,
) -> ChatResponse:
    """Build non-streaming response payload."""
    prompt_tokens = estimate_tokens(query)
    completion_tokens = estimate_tokens(answer)
    return ChatResponse(
        id=response_id,
        created=created,
        model=body.model,
        choices=[ChatChoice(index=0, message=message, finish_reason=finish_reason)],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def parse_answer_with_retry(
    session: ConversationSession,
    model_obj: Model,
    query: str,
    tools: list[ToolDefinition] | None,
    response_format: ResponseFormat | None,
    require_tool_call: bool,
) -> tuple[str, ChatMessage, str, bool, bool, str]:
    """Run upstream request and parse answer with optional retries."""
    last_answer = ""
    reinforced_query = query
    message = ChatMessage(role="assistant", content="")
    finish_reason = "stop"
    tool_call_found = False
    structured_output_valid = False

    for attempt in range(1, TOOL_CALL_RETRY_ATTEMPTS + 1):
        session.conversation.ask(reinforced_query, model=model_obj, stream=False)
        last_answer = session.conversation.answer or ""
        message, finish_reason, tool_call_found, structured_output_valid = parse_response(
            last_answer,
            tools,
            response_format,
        )

        if not require_tool_call or tool_call_found:
            return last_answer, message, finish_reason, tool_call_found, structured_output_valid, reinforced_query

        if attempt < TOOL_CALL_RETRY_ATTEMPTS:
            LOGGER.warning("Required tool call missing, retrying request with stronger adapter hint")
            reinforced_query += (
                "\n\nTOOL CALL REPAIR MODE:\n"
                "- You must use one of the available tools.\n"
                "- Do not answer in prose.\n"
                "- If you already know the tool name and arguments, output only JSON.\n"
                "- Valid response shapes are either:\n"
                '  {"function_call":{"name":"tool_name","arguments":{...}}}\n'
                '  or {"name":"tool_name","arguments":{...}}\n'
                "- Arguments must be valid JSON matching the tool schema."
            )

    return last_answer, message, finish_reason, tool_call_found, structured_output_valid, reinforced_query


def perform_nonstream_completion(
    body: ChatRequest,
    session: ConversationSession,
    model_obj: Model,
) -> tuple[str, ChatMessage, str, bool, bool]:
    """Execute a non-streaming completion flow."""
    use_two_step = bool(
        body.tools
        and (
            body.tool_choice is None
            or body.tool_choice == "auto"
            or (isinstance(body.tool_choice, str) and body.tool_choice.lower() == "auto")
        )
    )

    if use_two_step:
        assert body.tools is not None
        decision_query = decide_tool_usage(body.messages, body.tools)
        LOGGER.info("Starting two-step tool decision process")
        session.conversation.ask(decision_query, model=model_obj, stream=False)
        decision = session.conversation.answer or ""
        use_tool = should_use_tool(decision, body.tools)
        LOGGER.info("Tool decision: %s", use_tool)

        if use_tool:
            query = messages_to_query(body.messages, body.tools, "required", body.response_format)
            _answer, message, finish_reason, tool_call_found, structured_output_valid, final_query = parse_answer_with_retry(
                session,
                model_obj,
                query,
                body.tools,
                body.response_format,
                True,
            )
            return final_query, message, finish_reason, tool_call_found, structured_output_valid

        query = messages_to_query(body.messages, None, None, body.response_format)
        _answer, message, finish_reason, tool_call_found, structured_output_valid, final_query = parse_answer_with_retry(
            session,
            model_obj,
            query,
            None,
            body.response_format,
            False,
        )
        return final_query, message, finish_reason, tool_call_found, structured_output_valid

    query = messages_to_query(body.messages, body.tools, body.tool_choice, body.response_format)
    _answer, message, finish_reason, tool_call_found, structured_output_valid, final_query = parse_answer_with_retry(
        session,
        model_obj,
        query,
        body.tools,
        body.response_format,
        bool(body.tools and is_required_tool_choice(body.tool_choice)),
    )
    return final_query, message, finish_reason, tool_call_found, structured_output_valid


# =============================================================================
# Endpoints
# =============================================================================


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "uptime": (datetime.now() - start_time).total_seconds(),
        "models": len(models._models),
    }


@app.get("/stats")
async def stats(request: Request) -> dict[str, Any]:
    """Server statistics."""
    get_user(request)
    return {
        "uptime": (datetime.now() - start_time).total_seconds(),
        "requests": request_count,
        "conversations": manager.get_stats(),
        "models": {
            "count": len(models._models),
            "last_refresh": models._last_fetch.isoformat() if models._last_fetch else None,
        },
    }


@app.get("/v1/models", response_model=ModelsResponse)
async def list_models(request: Request) -> ModelsResponse:
    """List available models."""
    get_user(request)

    if models.needs_refresh():
        models.fetch(config.session_token)

    now = int(time.time())
    return ModelsResponse(
        data=[ModelItem(id=item["id"], created=now, owned_by=item["owned_by"]) for item in models.list_available()]
    )


@app.get("/v1/models/{model_id}", response_model=ModelItem)
async def get_model(model_id: str, request: Request) -> ModelItem:
    """Get model info."""
    get_user(request)

    for item in models.list_available():
        if item["id"] == model_id:
            return ModelItem(id=item["id"], created=int(time.time()), owned_by=item["owned_by"])

    raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")


@app.post("/v1/models/refresh")
async def refresh_models(request: Request) -> dict[str, Any]:
    """Force refresh models."""
    get_user(request)
    models.fetch(config.session_token)
    return {"status": "ok", "count": len(models._models)}


@app.get("/conversations")
async def list_conversations(request: Request) -> dict[str, Any]:
    """List conversations."""
    user_id = get_user(request)
    return {"conversations": manager.list_sessions(user_id)}


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request) -> dict[str, str]:
    """Delete conversation."""
    user_id = get_user(request)
    if manager.delete(conversation_id, user_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Conversation not found")


@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(request: Request, body: ChatRequest) -> ChatResponse | StreamingResponse:
    """Chat completions endpoint."""
    global request_count
    request_count += 1

    user_id = get_user(request)

    if not body.messages:
        raise HTTPException(
            status_code=400,
            detail=build_openai_error(
                "Messages required",
                "invalid_request_error",
                "messages",
                "messages_required",
            ),
        )

    model_obj = models.get(body.model)
    citation_mode = parse_citation_mode(body.citation_mode)
    strict_response = is_strict_response_format(body)
    required_tool_choice = is_required_tool_choice(body.tool_choice)

    conv_id, session = manager.get_or_create(body.conversation_id, user_id, body.model, citation_mode)

    response_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    LOGGER.info(
        "Chat completion request: tools=%s tool_choice=%s strict=%s stream=%s",
        body.tools is not None,
        body.tool_choice,
        strict_response,
        body.stream,
    )

    try:
        if body.stream:
            query = messages_to_query(body.messages, body.tools, body.tool_choice, body.response_format)
            return StreamingResponse(
                stream_response(
                    response_id=response_id,
                    created=created,
                    model_name=body.model,
                    model=model_obj,
                    query=query,
                    session=session,
                    tools=body.tools,
                    response_format=body.response_format,
                ),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Conversation-ID": conv_id},
            )

        query, message, finish_reason, tool_call_found, structured_output_valid = perform_nonstream_completion(
            body,
            session,
            model_obj,
        )
        answer = session.conversation.answer or ""

        if body.tools and required_tool_choice and not tool_call_found:
            raise HTTPException(
                status_code=502,
                detail=build_openai_error(
                    "Model failed to produce a required tool call",
                    "invalid_response_error",
                    "tool_choice",
                    "required_tool_call_missing",
                ),
            )

        if strict_response and not structured_output_valid:
            raise HTTPException(
                status_code=502,
                detail=build_openai_error(
                    "Model failed to produce valid structured output",
                    "invalid_response_error",
                    "response_format",
                    "invalid_structured_output",
                ),
            )

        return build_nonstream_response(body, response_id, created, message, finish_reason, query, answer)
    except PerplexityError as exc:
        LOGGER.error("Perplexity error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=build_openai_error(str(exc), "api_error", None, "upstream_error"),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Unhandled error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=build_openai_error(str(exc), "server_error", None, "internal_error"),
        ) from exc


async def stream_response(
    response_id: str,
    created: int,
    model_name: str,
    model: Model,
    query: str,
    session: ConversationSession,
    tools: list[ToolDefinition] | None = None,
    response_format: ResponseFormat | None = None,
) -> AsyncGenerator[str, None]:
    """Stream chat response."""
    last = ""
    full_response = ""

    for response in session.conversation.ask(query, model=model, stream=True):
        current = response.answer or ""
        if len(current) > len(last):
            delta = current[len(last) :]
            last = current
            full_response = current
            yield build_stream_chunk(
                response_id,
                created,
                model_name,
                {"role": "assistant", "content": delta} if not last[:-len(delta)] else {"content": delta},
            )

    message, _, tool_call_found, _ = parse_response(full_response, tools, response_format)

    if tool_call_found and message.tool_calls:
        for chunk in stream_tool_call_chunks(response_id, created, model_name, message):
            yield chunk
        return

    yield build_stream_chunk(response_id, created, model_name, {}, "stop")
    yield "data: [DONE]\n\n"


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":
    try:
        uvicorn.run(
            "openai_server:app",
            host=config.host,
            port=config.port,
            log_level=config.log_level.lower(),
        )
    except RuntimeError as exc:
        raise SystemExit(build_startup_error_message()) from exc


def run_self_test() -> dict[str, Any]:
    """Run basic in-process validation of JSON and tool-call response parsing."""
    json_message, json_finish_reason, json_tool_call_found, json_valid = parse_response(
        '{"name":"FastAPI","category":"framework","summary":"A modern Python web framework."}',
        response_format=ResponseFormat(type="json_object"),
    )

    schema_format = ResponseFormat(
        type="json_schema",
        json_schema={
            "name": "framework_summary",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "language": {"type": "string"},
                    "stars_estimate": {"type": "integer"},
                },
                "required": ["name", "language", "stars_estimate"],
            },
        },
    )
    schema_message, schema_finish_reason, schema_tool_call_found, schema_valid = parse_response(
        'Here is the result: {"name":"FastAPI","language":"Python","stars_estimate":"100000"}',
        response_format=schema_format,
    )

    tools = [
        ToolDefinition(
            function=FunctionDefinition(
                name="get_weather",
                description="Get weather for a city",
                parameters={
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "unit": {"type": "string"},
                    },
                    "required": ["city"],
                },
            )
        )
    ]
    tool_message, tool_finish_reason, tool_call_found, tool_valid = parse_response(
        '{"function_call":{"name":"get_weather","arguments":{"city":"Paris","unit":"celsius"}}}',
        tools=tools,
    )

    return {
        "ok": all(
            [
                json_finish_reason == "stop",
                not json_tool_call_found,
                json_valid,
                json_message.content == '{"name": "FastAPI", "category": "framework", "summary": "A modern Python web framework."}',
                schema_finish_reason == "stop",
                not schema_tool_call_found,
                schema_valid,
                schema_message.content == '{"name": "FastAPI", "language": "Python", "stars_estimate": 100000}',
                tool_finish_reason == "tool_calls",
                tool_call_found,
                not tool_valid,
                tool_message.tool_calls is not None,
                bool(tool_message.tool_calls)
                and tool_message.tool_calls[0].function["name"] == "get_weather",
                bool(tool_message.tool_calls)
                and tool_message.tool_calls[0].function["arguments"] == '{"city":"Paris","unit":"celsius"}',
            ]
        ),
        "checks": {
            "json_object": {
                "finish_reason": json_finish_reason,
                "tool_call_found": json_tool_call_found,
                "structured_output_valid": json_valid,
                "content": json_message.content,
            },
            "json_schema": {
                "finish_reason": schema_finish_reason,
                "tool_call_found": schema_tool_call_found,
                "structured_output_valid": schema_valid,
                "content": schema_message.content,
            },
            "tool_call": {
                "finish_reason": tool_finish_reason,
                "tool_call_found": tool_call_found,
                "structured_output_valid": tool_valid,
                "tool_name": tool_message.tool_calls[0].function["name"] if tool_message.tool_calls else None,
                "arguments": tool_message.tool_calls[0].function["arguments"] if tool_message.tool_calls else None,
            },
        },
    }
