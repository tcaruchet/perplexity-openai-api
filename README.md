<div align="center">

# Perplexity WebUI Scraper

Python scraper to extract AI responses from [Perplexity's](https://www.perplexity.ai) web interface.

[![PyPI](https://img.shields.io/pypi/v/perplexity-webui-scraper?color=blue)](https://pypi.org/project/perplexity-webui-scraper)
[![Python](https://img.shields.io/pypi/pyversions/perplexity-webui-scraper)](https://pypi.org/project/perplexity-webui-scraper)
[![License](https://img.shields.io/github/license/henrique-coder/perplexity-webui-scraper?color=green)](./LICENSE)

</div>

---

## Installation

### As a Library

```bash
# From PyPI (stable)
uv add perplexity-webui-scraper

# From GitHub prod branch (latest fixes)
uv add git+https://github.com/henrique-coder/perplexity-webui-scraper.git@prod
```

### As MCP Server

No installation required — `uvx` handles everything automatically:

```bash
# From PyPI (stable)
uvx --from perplexity-webui-scraper[mcp]@latest perplexity-webui-scraper-mcp

# From GitHub prod branch (latest fixes)
uvx --from "perplexity-webui-scraper[mcp]@git+https://github.com/henrique-coder/perplexity-webui-scraper.git@prod" perplexity-webui-scraper-mcp

# From local directory (for development)
uv --directory /path/to/perplexity-webui-scraper run perplexity-webui-scraper-mcp
```

## Requirements

- **Perplexity Pro or Max account**
- **Session token** (`__Secure-next-auth.session-token` cookie)

### Getting Your Session Token

#### Option 1: Automatic (CLI Tool)

```bash
uv run get-perplexity-session-token
```

This interactive tool will:

1. Ask for your Perplexity email
2. Send a verification code to your email
3. Accept either a 6-digit code or magic link
4. Extract and display your session token
5. Optionally save it to your `.env` file

#### Option 2: Manual (Browser)

1. Log in at [perplexity.ai](https://www.perplexity.ai)
2. Open DevTools (`F12`) → Application/Storage → Cookies
3. Copy the value of `__Secure-next-auth.session-token`
4. Store in `.env`: `PERPLEXITY_SESSION_TOKEN="your_token"`

## Quick Start

```python
from perplexity_webui_scraper import Perplexity

client = Perplexity(session_token="YOUR_TOKEN")
conversation = client.create_conversation()

conversation.ask("What is quantum computing?")
print(conversation.answer)

# Follow-up (context is preserved automatically)
conversation.ask("Explain it simpler")
print(conversation.answer)
```

### Streaming

```python
for chunk in conversation.ask("Explain AI", stream=True):
    if chunk.answer:
        print(chunk.answer, end="\r")
```

### With Options

```python
from perplexity_webui_scraper import (
    CitationMode,
    ConversationConfig,
    Coordinates,
    SourceFocus,
)

config = ConversationConfig(
    model="deep-research",
    citation_mode=CitationMode.MARKDOWN,
    source_focus=[SourceFocus.WEB, SourceFocus.ACADEMIC],
    language="en-US",
    coordinates=Coordinates(latitude=12.3456, longitude=-98.7654),
)

conversation = client.create_conversation(config)
conversation.ask("Latest AI research", files=["paper.pdf"])
print(conversation.answer)
```

## API Reference

### `Perplexity(session_token, config?)`

Main client — create once and reuse across multiple conversations.

| Parameter       | Type           | Description                  |
| --------------- | -------------- | ---------------------------- |
| `session_token` | `str`          | Browser cookie value         |
| `config`        | `ClientConfig` | Timeout, retry, TLS settings |

```python
from perplexity_webui_scraper import ClientConfig, LogLevel, Perplexity

client = Perplexity(
    session_token="YOUR_TOKEN",
    config=ClientConfig(
        timeout=7200,
        max_retries=3,
        logging_level=LogLevel.DEBUG,
        log_file=".debug/perplexity.log",
    ),
)
```

### `client.create_conversation(config?)`

Returns a `Conversation` object. Each conversation maintains its own context for follow-up questions.

```python
conversation = client.create_conversation(ConversationConfig(model="gpt-5.4"))
```

### `Conversation.ask(query, model?, files?, citation_mode?, stream?)`

| Parameter       | Type                      | Default  | Description                  |
| --------------- | ------------------------- | -------- | ---------------------------- |
| `query`         | `str`                     | required | The question to ask          |
| `model`         | `str \| None`             | `"best"` | Model ID string              |
| `files`         | `list[FileInput] \| None` | `None`   | File attachments             |
| `citation_mode` | `CitationMode \| None`    | `None`   | Override conversation config |
| `stream`        | `bool`                    | `False`  | Yield chunks as they arrive  |

Returns `self` (the `Conversation`) for method chaining or iteration when streaming.

#### Conversation Properties

| Property         | Type                     | Description                       |
| ---------------- | ------------------------ | --------------------------------- |
| `answer`         | `str \| None`            | Full response text                |
| `title`          | `str \| None`            | Auto-generated conversation title |
| `search_results` | `list[SearchResultItem]` | Source URLs used in the response  |
| `uuid`           | `str \| None`            | Conversation backend UUID         |

### Models

Models are specified as plain strings — the same style as the OpenAI SDK:

```python
ConversationConfig(model="gpt-5.4-thinking")
conversation.ask("...", model="gemini-3.1-pro")
```

| Model ID                       | Name                       | Description                                                        | Min. Tier |
| ------------------------------ | -------------------------- | ------------------------------------------------------------------ | --------- |
| `"best"`                       | Pro                        | Automatically selects the most responsive model based on the query | pro       |
| `"deep-research"`              | Deep research              | Fast and thorough for routine research                             | pro       |
| `"sonar"`                      | Sonar                      | Perplexity's latest model                                          | pro       |
| `"gemini-3-flash"`             | Gemini 3 Flash             | Google's fast model                                                | pro       |
| `"gemini-3-flash-thinking"`    | Gemini 3 Flash Thinking    | Google's fast model with thinking                                  | pro       |
| `"gemini-3.1-pro"`             | Gemini 3.1 Pro             | Google's latest model                                              | pro       |
| `"gemini-3.1-pro-thinking"`    | Gemini 3.1 Pro Thinking    | Google's latest model with thinking                                | pro       |
| `"gpt-5.4"`                    | GPT-5.4                    | OpenAI's latest model                                              | pro       |
| `"gpt-5.4-thinking"`           | GPT-5.4 Thinking           | OpenAI's latest model with thinking                                | pro       |
| `"claude-sonnet-4.6"`          | Claude Sonnet 4.6          | Anthropic's fast model                                             | pro       |
| `"claude-sonnet-4.6-thinking"` | Claude Sonnet 4.6 Thinking | Anthropic's newest reasoning model                                 | pro       |
| `"claude-opus-4.6"`            | Claude Opus 4.6            | Anthropic's most advanced model                                    | max       |
| `"claude-opus-4.6-thinking"`   | Claude Opus 4.6 Thinking   | Anthropic's Opus reasoning model with thinking                     | max       |
| `"grok-4.1"`                   | Grok 4.1                   | xAI's latest model                                                 | pro       |
| `"grok-4.1-thinking"`          | Grok 4.1 Thinking          | xAI's latest model with thinking                                   | pro       |
| `"kimi-k2.5-thinking"`         | Kimi K2.5 Thinking         | Moonshot AI's latest model with thinking                           | pro       |

You can also inspect available models programmatically:

```python
from perplexity_webui_scraper import MODELS

for model_id, model in MODELS.items():
    print(f"{model_id!r:35} → {model.name} [{model.subscription_tier}]")
```

### File Attachments (`FileInput`)

`ask()` accepts files in multiple formats via the `FileInput` type:

```python
from perplexity_webui_scraper import FileInput  # for type annotations

# 1. Local file path (str or Path)
conversation.ask("Describe this image", files=["photo.jpg"])
conversation.ask("Summarize this", files=[Path("document.pdf")])

# 2. Raw bytes — filename defaults to "file", mimetype to "application/octet-stream"
image_bytes: bytes = requests.get("https://example.com/image.jpg").content
conversation.ask("What's in this image?", files=[image_bytes])

# 3. Bytes + filename — mimetype is guessed from the filename extension
conversation.ask("Analyze this", files=[(image_bytes, "photo.jpg")])

# 4. Bytes + filename + explicit mimetype — full control
conversation.ask("Read this PDF", files=[(pdf_bytes, "report.pdf", "application/pdf")])

# Mix and match different types in one call
conversation.ask("Compare these", files=["local.jpg", (remote_bytes, "remote.png")])
```

**Limits:** up to 30 files per prompt, 50 MB each.

### `CitationMode`

| Mode       | Output format  | Description               |
| ---------- | -------------- | ------------------------- |
| `DEFAULT`  | `text[1]`      | Keep original markers     |
| `MARKDOWN` | `text[1](url)` | Convert to markdown links |
| `CLEAN`    | `text`         | Remove all citations      |

### `ConversationConfig`

| Parameter         | Type                               | Default           | Description                                |
| ----------------- | ---------------------------------- | ----------------- | ------------------------------------------ |
| `model`           | `str \| None`                      | `None` (`"best"`) | Model ID string                            |
| `citation_mode`   | `CitationMode`                     | `CLEAN`           | Citation format                            |
| `save_to_library` | `bool`                             | `False`           | Save conversation to Perplexity library    |
| `search_focus`    | `SearchFocus`                      | `WEB`             | Search type (`WEB` or `WRITING`)           |
| `source_focus`    | `SourceFocus \| list[SourceFocus]` | `WEB`             | Source types to prioritize                 |
| `time_range`      | `TimeRange`                        | `ALL`             | Recency filter for results                 |
| `language`        | `str`                              | `"en-US"`         | Language for the response                  |
| `timezone`        | `str \| None`                      | `None`            | IANA timezone (e.g. `"America/Sao_Paulo"`) |
| `coordinates`     | `Coordinates \| None`              | `None`            | Geographic location (lat/lng)              |

### `ClientConfig`

| Parameter               | Type                      | Default    | Description                                 |
| ----------------------- | ------------------------- | ---------- | ------------------------------------------- |
| `timeout`               | `int`                     | `3600`     | Request timeout in seconds                  |
| `impersonate`           | `str`                     | `"chrome"` | Browser fingerprint to impersonate          |
| `max_retries`           | `int`                     | `3`        | Maximum retry attempts on transient errors  |
| `retry_base_delay`      | `float`                   | `1.0`      | Initial backoff delay in seconds            |
| `retry_max_delay`       | `float`                   | `60.0`     | Maximum backoff delay in seconds            |
| `retry_jitter`          | `float`                   | `0.5`      | Jitter factor for retry delay randomization |
| `requests_per_second`   | `float`                   | `0.5`      | Rate limit (requests per second)            |
| `rotate_fingerprint`    | `bool`                    | `True`     | Rotate browser fingerprint on each retry    |
| `max_init_query_length` | `int`                     | `2000`     | Truncate init query to avoid HTTP 414       |
| `logging_level`         | `LogLevel`                | `DISABLED` | Log verbosity                               |
| `log_file`              | `str \| PathLike \| None` | `None`     | Write logs to file instead of stderr        |

### Enums

#### `SourceFocus`

| Value      | Targets                                |
| ---------- | -------------------------------------- |
| `WEB`      | General web search                     |
| `ACADEMIC` | Academic papers and scholarly articles |
| `SOCIAL`   | Social media (Reddit, Twitter, etc.)   |
| `FINANCE`  | SEC EDGAR filings                      |

#### `SearchFocus`

| Value     | Description          |
| --------- | -------------------- |
| `WEB`     | Search the web       |
| `WRITING` | Writing-focused mode |

#### `TimeRange`

| Value        | Description    |
| ------------ | -------------- |
| `ALL`        | No time filter |
| `TODAY`      | Last 24 hours  |
| `LAST_WEEK`  | Last 7 days    |
| `LAST_MONTH` | Last 30 days   |
| `LAST_YEAR`  | Last 365 days  |

#### `LogLevel`

| Value      | Description                  |
| ---------- | ---------------------------- |
| `DISABLED` | No logging (default)         |
| `DEBUG`    | All messages including debug |
| `INFO`     | Info, warnings, and errors   |
| `WARNING`  | Warnings and errors only     |
| `ERROR`    | Errors only                  |
| `CRITICAL` | Critical/fatal errors only   |

## Exceptions

| Exception                          | Description                                    |
| ---------------------------------- | ---------------------------------------------- |
| `PerplexityError`                  | Base exception for all library errors          |
| `HTTPError`                        | HTTP error with status code and response body  |
| `AuthenticationError`              | Session token is invalid or expired (HTTP 403) |
| `RateLimitError`                   | Rate limit exceeded (HTTP 429)                 |
| `FileUploadError`                  | File upload to Perplexity's S3 failed          |
| `FileValidationError`              | File validation failed (size, type, not found) |
| `ResearchClarifyingQuestionsError` | Research mode requires clarifying questions    |
| `ResponseParsingError`             | API response could not be parsed               |
| `StreamingError`                   | Error during streaming response                |

```python
from perplexity_webui_scraper import (
    AuthenticationError,
    PerplexityError,
    ResearchClarifyingQuestionsError,
)

try:
    conversation.ask("Analyze recent market trends", model="deep-research")
except ResearchClarifyingQuestionsError as e:
    print("Needs clarification:", e.questions)
except AuthenticationError:
    print("Token expired — refresh your session token")
except PerplexityError as e:
    print(f"Library error: {e}")
```

## MCP Server (Model Context Protocol)

The library includes an MCP server that exposes every model as a separate tool for AI assistants like Claude Desktop and Antigravity. Enable only the models you need to keep agent context size small.

### Configuration

Add to your MCP config file (no installation required):

**Claude Desktop** (`~/.config/claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "perplexity-webui-scraper": {
      "command": "uvx",
      "args": [
        "--from",
        "perplexity-webui-scraper[mcp]@latest",
        "perplexity-webui-scraper-mcp"
      ],
      "env": {
        "PERPLEXITY_SESSION_TOKEN": "your_token_here"
      }
    }
  }
}
```

**From GitHub prod branch:**

```json
{
  "mcpServers": {
    "perplexity-webui-scraper": {
      "command": "uvx",
      "args": [
        "--from",
        "perplexity-webui-scraper[mcp]@git+https://github.com/henrique-coder/perplexity-webui-scraper.git@prod",
        "perplexity-webui-scraper-mcp"
      ],
      "env": {
        "PERPLEXITY_SESSION_TOKEN": "your_token_here"
      }
    }
  }
}
```

**From local directory (for development):**

```json
{
  "mcpServers": {
    "perplexity-webui-scraper": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/perplexity-webui-scraper",
        "run",
        "perplexity-webui-scraper-mcp"
      ],
      "env": {
        "PERPLEXITY_SESSION_TOKEN": "your_token_here"
      }
    }
  }
}
```

### Available Tools

Each tool uses a specific AI model. Enable only the ones you need:

| Tool                      | Model                      | Description                                                        | Min. Tier |
| ------------------------- | -------------------------- | ------------------------------------------------------------------ | --------- |
| `pplx_ask`                | Pro                        | Automatically selects the most responsive model based on the query | pro       |
| `pplx_deep_research`      | Deep research              | Fast and thorough for routine research                             | pro       |
| `pplx_sonar`              | Sonar                      | Perplexity's latest model                                          | pro       |
| `pplx_gemini_flash`       | Gemini 3 Flash             | Google's fast model                                                | pro       |
| `pplx_gemini_flash_think` | Gemini 3 Flash Thinking    | Google's fast model with thinking                                  | pro       |
| `pplx_gemini31_pro`       | Gemini 3.1 Pro             | Google's latest model                                              | pro       |
| `pplx_gemini31_pro_think` | Gemini 3.1 Pro Thinking    | Google's latest model with thinking                                | pro       |
| `pplx_gpt54`              | GPT-5.4                    | OpenAI's latest model                                              | pro       |
| `pplx_gpt54_thinking`     | GPT-5.4 Thinking           | OpenAI's latest model with thinking                                | pro       |
| `pplx_claude_s46`         | Claude Sonnet 4.6          | Anthropic's fast model                                             | pro       |
| `pplx_claude_s46_think`   | Claude Sonnet 4.6 Thinking | Anthropic's newest reasoning model                                 | pro       |
| `pplx_claude_o46`         | Claude Opus 4.6            | Anthropic's most advanced model                                    | max       |
| `pplx_claude_o46_think`   | Claude Opus 4.6 Thinking   | Anthropic's Opus reasoning model with thinking                     | max       |
| `pplx_grok41`             | Grok 4.1                   | xAI's latest model                                                 | pro       |
| `pplx_grok41_think`       | Grok 4.1 Thinking          | xAI's latest model with thinking                                   | pro       |
| `pplx_kimi_k25_think`     | Kimi K2.5 Thinking         | Moonshot AI's latest model with thinking                           | pro       |

**All tools support `source_focus`:** `web`, `academic`, `social`, `finance`, `all`

## Disclaimer

This is an **unofficial** library. It uses internal APIs that may change without notice. Use at your own risk.

By using this library, you agree to Perplexity AI's [Terms of Service](https://www.perplexity.ai/hub/legal/terms-of-service).
