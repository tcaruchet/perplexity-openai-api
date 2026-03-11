# Perplexity OpenAI Proxy

Production-ready OpenAI-compatible API proxy for Perplexity.

This project exposes a FastAPI server that emulates the `OpenAI Chat Completions` API and forwards requests to Perplexity through the bundled scraper client. It is designed for practical compatibility with OpenAI SDKs, LangChain, agent frameworks, and self-hosted integrations that expect an OpenAI-style interface.

## Features

- OpenAI-compatible `POST /v1/chat/completions`
- OpenAI-compatible `GET /v1/models`
- Dynamic model discovery from Perplexity
- Structured output support:
  - `response_format={"type":"json_object"}`
  - `response_format={"type":"json_schema", ...}`
- Strict structured output enforcement
- Tool / function calling support
- Retry flow for required tool calls
- Streaming responses
- Conversation persistence with cleanup
- Optional API key protection
- Rate limiting
- Docker and Docker Compose support
- Production-friendly defaults for container deployment

## Compatibility Goals

This proxy is intended to work well with clients expecting an OpenAI-like API, including:

- `openai` Python SDK
- LangChain
- LangGraph
- custom agent runtimes
- self-hosted tools that support `base_url`

### Notes

Because the upstream model is not OpenAI, compatibility is best-effort in places where upstream behavior differs. This repository includes guardrails to reduce those differences:

- retries for required tool calls
- structured output validation
- normalized tool arguments
- OpenAI-style error payloads

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/max/perplexity-openai-proxy.git
cd perplexity-openai-proxy
```

### 2. Create environment file

```bash
cp .env.example .env
```

Set at minimum:

```env
PERPLEXITY_SESSION_TOKEN=your_session_token
OPENAI_API_KEY=your_optional_local_api_key
PORT=8000
LOG_LEVEL=INFO
ENABLE_RATE_LIMITING=true
REQUESTS_PER_MINUTE=60
CONVERSATION_TIMEOUT=3600
MAX_CONVERSATIONS_PER_USER=100
DEFAULT_MODEL=perplexity-auto
DEFAULT_CITATION_MODE=CLEAN
```

### 3. Run locally

Using `uv`:

```bash
uv sync --upgrade --all-groups
uv run python openai_server.py
```

Or with plain Python:

```bash
pip install -U pip
pip install .
python openai_server.py
```

### 4. Verify

```bash
curl http://localhost:8000/health
curl http://localhost:8000/v1/models
```

## Docker

### Build and run

```bash
docker compose up -d --build
```

### Check logs

```bash
docker compose logs -f perplexity-api
```

### Stop

```bash
docker compose down
```

## Getting the Perplexity session token

1. Sign in to https://www.perplexity.ai
2. Open browser developer tools
3. Go to cookies for `perplexity.ai`
4. Copy the value of `__Secure-next-auth.session-token`
5. Put it into `.env` as `PERPLEXITY_SESSION_TOKEN`

Keep this token private.

## API Endpoints

### Health

- `GET /health`

### Stats

- `GET /stats`

### Models

- `GET /v1/models`
- `GET /v1/models/{model_id}`
- `POST /v1/models/refresh`

### Conversations

- `GET /conversations`
- `DELETE /conversations/{conversation_id}`

### Chat Completions

- `POST /v1/chat/completions`

## Example: OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="local-key",
    base_url="http://localhost:8000/v1",
)

response = client.chat.completions.create(
    model="perplexity-auto",
    messages=[
        {"role": "user", "content": "Explain what FastAPI is in two sentences."}
    ],
)

print(response.choices[0].message.content)
```

## Example: Structured Output

```python
from openai import OpenAI
import json

client = OpenAI(
    api_key="local-key",
    base_url="http://localhost:8000/v1",
)

response = client.chat.completions.create(
    model="perplexity-auto",
    messages=[
        {
            "role": "user",
            "content": "Return a JSON object with fields name, category, and summary for FastAPI."
        }
    ],
    response_format={"type": "json_object"},
)

data = json.loads(response.choices[0].message.content)
print(data)
```

## Example: JSON Schema

```python
from openai import OpenAI
import json

client = OpenAI(
    api_key="local-key",
    base_url="http://localhost:8000/v1",
)

schema = {
    "type": "json_schema",
    "json_schema": {
        "name": "framework_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "language": {"type": "string"},
                "stars_estimate": {"type": "integer"}
            },
            "required": ["name", "language", "stars_estimate"]
        }
    }
}

response = client.chat.completions.create(
    model="perplexity-auto",
    messages=[
        {"role": "user", "content": "Give me a structured summary for FastAPI."}
    ],
    response_format=schema,
)

print(json.loads(response.choices[0].message.content))
```

## Example: Tool Calling

```python
from openai import OpenAI

client = OpenAI(
    api_key="local-key",
    base_url="http://localhost:8000/v1",
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                },
                "required": ["city"]
            }
        }
    }
]

response = client.chat.completions.create(
    model="perplexity-auto",
    messages=[
        {"role": "user", "content": "What's the weather in Berlin?"}
    ],
    tools=tools,
    tool_choice="required",
)

message = response.choices[0].message
print(message.tool_calls)
```

## Request Notes

### `tool_choice`

Supported values:

- `"auto"`
- `"required"`
- `"any"`
- function selection object

When a tool call is required, the proxy retries if upstream does not initially comply.

### `response_format`

Supported:

- `{"type": "text"}`
- `{"type": "json_object"}`
- `{"type": "json_schema", "json_schema": {...}}`

When strict structured output is enabled, invalid upstream output is rejected instead of being silently passed through.

### `strict`

Optional top-level request flag:

```json
{
  "strict": true
}
```

This can be used to force strict structured output handling.

## Authentication

If `OPENAI_API_KEY` is set, clients must send:

```http
Authorization: Bearer your_key
```

If not set, the server accepts requests without API key authentication.

## Environment Variables

| Variable | Required | Default | Description |
|---|---:|---|---|
| `PERPLEXITY_SESSION_TOKEN` | yes | - | Perplexity session token |
| `OPENAI_API_KEY` | no | - | Optional local auth key |
| `HOST` | no | `0.0.0.0` | Bind host |
| `PORT` | no | `8000` | Bind port |
| `LOG_LEVEL` | no | `INFO` | Logging level |
| `ENABLE_RATE_LIMITING` | no | `true` | Enable request limiting |
| `REQUESTS_PER_MINUTE` | no | `60` | Rate limit |
| `CONVERSATION_TIMEOUT` | no | `3600` | Conversation expiry in seconds |
| `MAX_CONVERSATIONS_PER_USER` | no | `100` | Session cap per user |
| `DEFAULT_MODEL` | no | `perplexity-auto` | Default model alias |
| `DEFAULT_CITATION_MODE` | no | `CLEAN` | Citation handling mode |

## Development

### Install dependencies

```bash
uv sync --upgrade --all-groups
```

### Format

```bash
just fmt
```

### Lint

```bash
just lint
```

### Full release check

```bash
just release-check
```

## Production Notes

- Use a dedicated `OPENAI_API_KEY`
- Run behind a reverse proxy if exposing publicly
- Restrict network access where possible
- Rotate the Perplexity session token if compromised
- Monitor upstream changes in Perplexity behavior
- Keep the container image pinned and rebuilt regularly
- Review logs for repeated structured output or tool-call failures

## Limitations

- This is an OpenAI-compatible proxy, not OpenAI itself
- Upstream model behavior can change without notice
- Full parity with all OpenAI APIs is not guaranteed
- Some streaming semantics may differ from OpenAI-native backends
- Tool use and schema compliance still depend on upstream model behavior

## License

MIT

## Disclaimer

This project is an independent compatibility layer. You are responsible for complying with the terms of service, acceptable use policies, and operational/security requirements of the services you use with it.
