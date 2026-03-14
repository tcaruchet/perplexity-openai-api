# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0).

## [0.6.2] - 2026-03-13

### Added

- Created complete native documentation site using MkDocs Material.
- Automated setup for GitHub Pages with native zero-branch action deployment instead of legacy `gh-pages` clones.

### Changed

- Refactored `core.py` to enable concurrent thread-pooled file uploads, supporting huge attachments in parallel without network blocking/latency.
- Updated argument validation pipelines using strict Python 3.10+ `match`/`case` structural pattern matching instead of explicit type tracking instances.
- Neutralized hardcoded workflow rules and environment references in `AGENTS.md` to be fully cross-platform.
- Restructured `pyproject.toml` allocating `mkdocs` to an isolated `docs` dependency group for clean CI/CD sync boundaries.

### Fixed

- Replaced ambiguous `# type: ignore` suppresses with explicit and defensive runtime assertion typings in HTTP resilience retry mechanics.

## [0.6.1] - 2026-03-12

### Changed

- Bumped project version to 0.6.1 to match existing current stable version.
