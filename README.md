<div align="center">

<img src="docs/assets/icon.png" width="128" alt="Logo">

# Perplexity WebUI Scraper

Python scraper to extract AI responses from [Perplexity's](https://www.perplexity.ai) web interface.

[![PyPI](https://img.shields.io/pypi/v/perplexity-webui-scraper?color=blue)](https://pypi.org/project/perplexity-webui-scraper)
[![Python](https://img.shields.io/pypi/pyversions/perplexity-webui-scraper)](https://pypi.org/project/perplexity-webui-scraper)
[![License](https://img.shields.io/github/license/henrique-coder/perplexity-webui-scraper?color=green)](./LICENSE)

</div>

---

**📚 Full Documentation & Advanced Guide:** [https://henrique-coder.github.io/perplexity-webui-scraper/](https://henrique-coder.github.io/perplexity-webui-scraper/)

---

## What is this?

This library allows you to interact with Perplexity programmatically, start conversations, upload files, and stream responses back, all using the same web interface endpoints used by the browser, but powered by Python.

- **Requirements:** A Perplexity Pro or Max account, and your browser's Session Token.
- **Key Features:** Full latest model support (GPT-5.4, Opus 4.6, Deep Research), file attachments, asynchronous streaming, and an out-of-the-box MCP Server for AI agents.

## Quick Start

### 1. Install

```bash
uv add perplexity-webui-scraper
```

### 2. Basic Example

```python
from perplexity_webui_scraper import Perplexity

client = Perplexity(session_token="YOUR_TOKEN")
conversation = client.create_conversation()

conversation.ask("What is quantum computing?")
print(conversation.answer)
```

## Disclaimer

This is an **unofficial** library. It uses internal APIs that may change without notice. Use at your own risk. By using this library, you agree to Perplexity AI's [Terms of Service](https://www.perplexity.ai/hub/legal/terms-of-service).
