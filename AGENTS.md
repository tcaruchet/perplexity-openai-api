# Project Overview

You are an expert AI agent working on the `perplexity-webui-scraper` repository. This document defines the strict project standards, technical stack, file architecture, and CI/CD operations you must adhere to. The core objective of this project is to maintain a high-performance, resilient, and type-safe Python SDK for scraping and interacting with Perplexity AI's web interface.

---

## 🏗️ Technical Stack & Architecture

- **Host OS:** Fedora Linux (Assume cross-platform compatibility for end-users, but local dev scripts assume Linux).
- **Core Language:** Python 3.10+ (Current target in CI is 3.14 for bleeding edge, but must uphold `<3.15` and `>=3.10`).
- **Dependencies & Package Management:** `uv` is used exclusively. _NEVER use `pip`, `poetry`, etc._

### Directory Structure

```text
perplexity-webui-scraper/
├── .github/workflows/
│   └── publish.yml
├── src/perplexity_webui_scraper/
│   ├── cli/
│   ├── mcp/
│   ├── config.py
│   ├── constants.py
│   ├── core.py
│   ├── enums.py
│   ├── exceptions.py
│   ├── http.py
│   ├── logging.py
│   ├── models.py
│   ├── resilience.py
│   └── types.py
├── AGENTS.md
├── CHANGELOG.md
├── Justfile
├── pyproject.toml
└── uv.lock
```

---

## 🎨 Code Quality & Style Standards

### Language

All code, variables, and internal comments must be written in **American English (`en_US`)**.

### Imports

- **ALL imports MUST use `from` syntax.** Never use bare `import module`.

  ```python
  import sys

  from sys import exit
  ```

- **Type Checking Imports:** Use `from typing import TYPE_CHECKING` and put type-only imports under an `if TYPE_CHECKING:` block when dealing with circular imports.

### Type Safety

- **Strict type hints** are mandatory on all classes, functions, and variables.
- Explicit return types are required, including `-> None` for void functions.
- Use the union operator `|` instead of `Optional` or `Union` (e.g., `str | None`).
- Ensure `from __future__ import annotations` is used or implied by modern Python/Ruff configs.

### Code Formatting Practices

- **Linting & Formatting Tools:** `ruff` and `ty`.
- **Ruff Profile:** Line length is 120, indent width is 4 spaces, using double quotes.
- **Docstrings:** Use Google-style docstrings. **ALWAYS include a blank line** between the docstring and the code body.

  ```python
  def example_function(param: int) -> str:
      """This is an example function.

      Args:
          param: An integer input.

      Returns:
          A string representation.
      """

      return str(param)
  ```

- **Logic Patterns:** Prefer `match`/`case` statements for structural pattern matching over long `if/elif` chains. Use DRY and KISS principles.

---

## 🛠️ Developer Operations (Justfile)

Always check the `Justfile` in the root directory and use it.

- **`just install`**: Syncs dependencies utilizing `uv sync --upgrade --all-extras --all-groups`.
- **`just format`**: Runs `prettier` (via npx) and `ruff format` & `ruff check --fix`.
- **`just lint`**: Runs `prettier --check`, `ruff check`, and `ty check`.

---

## 🚀 Versioning & CI/CD workflow

### Source of Truth for Versions

The project no longer considers `pyproject.toml` as the manual source of truth for version bumps.
Releases are exclusively driven by **`CHANGELOG.md`**.

1. **Keep a Changelog Format:** `CHANGELOG.md` adheres to the Keep a Changelog format.
2. **Version Bumps:** Adding a new `## [X.Y.Z] - YYYY-MM-DD` header at the top of the changelog triggers the CI/CD pipeline.
3. **`publish.yml`**:
   - Triggers on modifying `CHANGELOG.md` in the `prod` branch.
   - Automatically synchronizes the new version into `pyproject.toml`.
   - Commits the updated `pyproject.toml` back to the repository.
   - Publishes the build to PyPI using `uv build` and `uv publish`.
   - Creates a GitHub release using the exact changelog block. It also auto-generates a collapsible markdown section showing all git commits merged in that release.

---

## 📦 Handling Dependencies

When asked to add a dependency:

1. Always query `package-query` via the MCP tool `get_package_version('pypi', 'package_name')` first!
2. Use `uv add <package>` or append manually into `pyproject.toml`.
3. Re-run `uv sync`.
