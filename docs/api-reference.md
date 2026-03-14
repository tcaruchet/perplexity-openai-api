# API Reference

## `Perplexity(session_token, config?)`

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

## `client.create_conversation(config?)`

Returns a `Conversation` object. Each conversation maintains its own context for follow-up questions.

```python
from perplexity_webui_scraper import ConversationConfig

conversation = client.create_conversation(ConversationConfig(model="gpt-5.4"))
```

## `Conversation.ask(query, model?, files?, citation_mode?, stream?)`

| Parameter       | Type             | Default  | Description                 |
| --------------- | ---------------- | -------- | --------------------------- | ---------------------------- |
| `query`         | `str`            | required | The question to ask         |
| `model`         | `str             | None`    | `"best"`                    | Model ID string              |
| `files`         | `list[FileInput] | None`    | `None`                      | File attachments             |
| `citation_mode` | `CitationMode    | None`    | `None`                      | Override conversation config |
| `stream`        | `bool`           | `False`  | Yield chunks as they arrive |

Returns `self` (the `Conversation`) for method chaining or iteration when streaming.

### Conversation Properties

| Property         | Type                     | Description                      |
| ---------------- | ------------------------ | -------------------------------- | --------------------------------- |
| `answer`         | `str                     | None`                            | Full response text                |
| `title`          | `str                     | None`                            | Auto-generated conversation title |
| `search_results` | `list[SearchResultItem]` | Source URLs used in the response |
| `uuid`           | `str                     | None`                            | Conversation backend UUID         |

## Models

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

You can also inspect available models programmatically using the package dictionary:

```python
from perplexity_webui_scraper import MODELS

for model_id, model in MODELS.items():
    print(f"{model_id!r:35} → {model.name} [{model.subscription_tier}]")
```

## `CitationMode`

| Mode       | Output format  | Description               |
| ---------- | -------------- | ------------------------- |
| `DEFAULT`  | `text[1]`      | Keep original markers     |
| `MARKDOWN` | `text[1](url)` | Convert to markdown links |
| `CLEAN`    | `text`         | Remove all citations      |

## Configurations

### `ConversationConfig`

| Parameter         | Type           | Default            | Description                             |
| ----------------- | -------------- | ------------------ | --------------------------------------- | ------------------------------------------ |
| `model`           | `str           | None`              | `None` (`"best"`)                       | Model ID string                            |
| `citation_mode`   | `CitationMode` | `CLEAN`            | Citation format                         |
| `save_to_library` | `bool`         | `False`            | Save conversation to Perplexity library |
| `search_focus`    | `SearchFocus`  | `WEB`              | Search type (`WEB` or `WRITING`)        |
| `source_focus`    | `SourceFocus   | list[SourceFocus]` | `WEB`                                   | Source types to prioritize                 |
| `time_range`      | `TimeRange`    | `ALL`              | Recency filter for results              |
| `language`        | `str`          | `"en-US"`          | Language for the response               |
| `timezone`        | `str           | None`              | `None`                                  | IANA timezone (e.g. `"America/Sao_Paulo"`) |
| `coordinates`     | `Coordinates   | None`              | `None`                                  | Geographic location (lat/lng)              |

### `ClientConfig`

| Parameter               | Type       | Default    | Description                                 |
| ----------------------- | ---------- | ---------- | ------------------------------------------- | ------ | ------------------------------------ |
| `timeout`               | `int`      | `3600`     | Request timeout in seconds                  |
| `impersonate`           | `str`      | `"chrome"` | Browser fingerprint to impersonate          |
| `max_retries`           | `int`      | `3`        | Maximum retry attempts on transient errors  |
| `retry_base_delay`      | `float`    | `1.0`      | Initial backoff delay in seconds            |
| `retry_max_delay`       | `float`    | `60.0`     | Maximum backoff delay in seconds            |
| `retry_jitter`          | `float`    | `0.5`      | Jitter factor for retry delay randomization |
| `requests_per_second`   | `float`    | `0.5`      | Rate limit (requests per second)            |
| `rotate_fingerprint`    | `bool`     | `True`     | Rotate browser fingerprint on each retry    |
| `max_init_query_length` | `int`      | `2000`     | Truncate init query to avoid HTTP 414       |
| `logging_level`         | `LogLevel` | `DISABLED` | Log verbosity                               |
| `log_file`              | `str       | PathLike   | None`                                       | `None` | Write logs to file instead of stderr |

## Enums

### `SourceFocus`

| Value      | Targets                                |
| ---------- | -------------------------------------- |
| `WEB`      | General web search                     |
| `ACADEMIC` | Academic papers and scholarly articles |
| `SOCIAL`   | Social media (Reddit, Twitter, etc.)   |
| `FINANCE`  | SEC EDGAR filings                      |

### `SearchFocus`

| Value     | Description          |
| --------- | -------------------- |
| `WEB`     | Search the web       |
| `WRITING` | Writing-focused mode |

### `TimeRange`

| Value        | Description    |
| ------------ | -------------- |
| `ALL`        | No time filter |
| `TODAY`      | Last 24 hours  |
| `LAST_WEEK`  | Last 7 days    |
| `LAST_MONTH` | Last 30 days   |
| `LAST_YEAR`  | Last 365 days  |

### `LogLevel`

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
