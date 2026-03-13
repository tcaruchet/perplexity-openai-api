# Getting Started

## Installation

### As a Library

```bash
# From PyPI (stable)
uv add perplexity-webui-scraper

# From GitHub prod branch (latest features and fixes)
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

## Getting Your Session Token

### Option 1: Automatic (CLI Tool)

The library includes an interactive tool to fetch your token via email magic link or verification code.

```bash
uv run get-perplexity-session-token
```

This interactive tool will:

1. Ask for your Perplexity email
2. Send a verification code to your email
3. Accept either a 6-digit code or magic link
4. Extract and display your session token
5. Optionally save it to your `.env` file

### Option 2: Manual (Browser)

1. Log in at [perplexity.ai](https://www.perplexity.ai)
2. Open DevTools (`F12`) → Application/Storage → Cookies
3. Copy the value of `__Secure-next-auth.session-token`
4. Store in `.env`: `PERPLEXITY_SESSION_TOKEN="your_token"`
