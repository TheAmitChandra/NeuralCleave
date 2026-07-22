# neuralcleave — Project Status Report

**As of:** 2026-06-26
**Source of truth for the checklist below:** [`docs/IMPLEMENTATION_PLAN_v2.md`](IMPLEMENTATION_PLAN_v2.md)

---

## 1. Headline numbers

| Metric | Value |
|---|---|
| Implementation plan completion | **125 / 135 checklist items checked → 93%** |
| Test suite (gateway package) | **1159 tests, all passing** |
| Test suite (`NeuralCleave-sdk` package) | **27 tests, all passing, 100% coverage** |
| Code coverage (`neuralcleave` package) | **99.7%** (4,566 statements, 13 uncovered) |
| Channel adapters implemented | **14 / 14** planned (100%) |
| CLI (`neuralcleave`) commands | ~20 commands across start/stop/status/chat/config/channels/tools/voice/memory/version/update |
| Total commits on `main` | 759+ (130+ merges) |

The remaining 13 uncovered statements in the gateway are platform-unreachable branches (POSIX-only `os.kill`/`SIGTERM`/`start_new_session` paths on this Windows dev machine) or `if __name__ == "__main__":` entrypoint guards — both treated as a permanent, acceptable gap rather than active debt.

---

## 2. What's implemented (backend — effectively 100%)

Everything below is built, tested, and merged to `main`:

- **Gateway**: FastAPI + WebSocket daemon, REST API (`/api/v1/...`), channel manager, session manager, TOML config loader (pydantic-settings) with `ENV:VAR` secret resolution.
- **Channel adapters (14/14)**: Telegram, Discord, Slack, WhatsApp, Email, SMS (Twilio), Matrix, IRC, Signal, Webhook, Mastodon, Microsoft Teams, Mattermost, Nextcloud Talk.
- **Memory (3-tier)**: Redis short-term (TTL context), Qdrant semantic search, SQLite long-term persistence; cross-session shared memory pool; importance scoring + daily pruning; auto-tagging; session archiving/compaction; manual entry editing via `PATCH /api/v1/memory/entries/{id}`.
- **LLM routing**: Task-aware `ModelRouter` across Claude (Anthropic), Gemini (Google), DeepSeek, GPT-4 (OpenAI), and Ollama (local/privacy mode), with automatic fallback chains, per-channel model override, and Claude extended-thinking support.
- **Voice**: Whisper STT (local, `faster-whisper`), ElevenLabs + Kokoro + system (pyttsx3) TTS with auto-fallback, voice cloning, OpenWakeWord wake-word detection, full voice-note round trip (Telegram/Discord voice → transcribe → process → synthesize reply).
- **Reflection engine**: quality scoring + self-correction retry loop.
- **Plugin system**: typed `Plugin` base class (`neuralcleave/plugins/base.py`) covering tool/channel/tts/stt/memory/generic plugin types, subprocess-sandboxed execution, PyPI-based registry (`neuralcleave hub install <package>`).
- **`NeuralCleave-sdk`**: standalone, dependency-free package (`NeuralCleave-sdk/`) exposing `Plugin`/`Tool`/`ChannelAdapter` so third-party plugin authors don't need to install the full gateway. 27 tests, 100% coverage. Published to PyPI (currently v0.1.2), via Trusted Publishing triggered by GitHub Releases.
- **Example plugins** (`examples/plugins/`): three working, independently installable plugins built on `NeuralCleave-sdk` — `NeuralCleave-github` (lists repo events), `NeuralCleave-notion` (searches pages/databases), `NeuralCleave-google-calendar` (lists upcoming events). 37 tests combined, 100% coverage each, all lint+test in CI. All three published to PyPI alongside the SDK.
- **Marketing landing page** (`docs-site/`): static HTML/CSS/JS, no build step — hero, feature grid, OpenClaw comparison table, architecture diagram, quickstart. Deployed to GitHub Pages via `.github/workflows/deploy-pages.yml` on every push to `main` that touches `docs-site/`.
- **Multi-page reference docs** (`docs-site/docs/`): 7 pages — Getting Started, Configuration, CLI Reference, Architecture, Channels, Plugins & SDK, REST API — same plain HTML/CSS/JS approach as the landing page, sharing its stylesheet plus a sidebar/article layout. Every config key, CLI command, channel auth requirement, and REST/WebSocket route was cross-checked against the actual source (`config.py`, `cli.py`, `channels/*.py`, `gateway/routes.py`, `gateway/websocket.py`) rather than written from memory. Verified by screenshotting all 7 pages with Playwright — zero console/page errors.
- **CLI (`neuralcleave`)**: start/stop/status/chat, config show/init/edit, channels list/add/remove, tools list, voice clone, memory prune/clear/archive/edit/search, version, update — ~20 commands total.
- **Observability**: structured JSON logging with trace-friendly context (`ContextLogger`), Prometheus metrics, human-readable dev-mode logging via `rich`.
- **CI/CD**: GitHub Actions — lint (`ruff`) + full test suite on every push; on `main`, builds and pushes a Docker image to GHCR.

## 3. What's left (backend is effectively 100%; remaining items are frontend/distribution)

| Area | Items remaining |
|---|---|
| **Tauri desktop app** | Entire `src-tauri/` project, system tray, native notifications, global hotkey, auto-start, single-binary installers (.msi/.dmg/.AppImage) — **not started** |
| **Web UI** | Token usage dashboard — memory timeline/edit, channel status page, and mobile-responsive layout are all done |
| **Distribution/publishing** | Performance benchmarks vs. OpenClaw (an internal-only benchmark exists in `scripts/benchmark.py`, no head-to-head run yet) |

Done since the last revision of this report: `NeuralCleave-sdk` + 3 example plugins published to PyPI via Trusted Publishing; the main app published as `neuralcleave` on PyPI (the original `NeuralCleave` name was already taken); the public Docker image at `ghcr.io/theamitchandra/neuralcleave:latest` (renamed from `NeuralCleave` to match); the memory timeline/edit UI, channel status page, and mobile-responsive layout.

None of the remaining items require backend rework — they're additive (new UI pages, a packaging step, an external publish action). The backend API surface they'd consume (REST + WebSocket + plugin base classes) already exists.

---

## 4. SDK status

**Plugin-authoring SDK — built and published.** `NeuralCleave-sdk/` is a standalone package, published on PyPI (`pip install NeuralCleave-sdk`), exposing `Plugin`/`PluginMetadata`, `Tool`/`ToolResult`, and `ChannelAdapter`/`InboundMessage`/`Attachment` with zero third-party dependencies. Plugin authors write `from NeuralCleave_sdk import Plugin, Tool, ChannelAdapter` instead of installing the full gateway (FastAPI, all 14 channel SDKs, Qdrant client, etc.). 27 tests, 100% coverage, verified isolated from the main `neuralcleave` test suite and lint config. Releases are published automatically via PyPI Trusted Publishing (OIDC) when a GitHub Release with a matching tag prefix is cut — see `docs/PUBLISHING.md`.

**Example plugins — built and published.** `examples/plugins/` has three real, tested plugins proving the SDK works end-to-end: `NeuralCleave-github` (`github_events` tool, GitHub REST API), `NeuralCleave-notion` (`notion_search` tool, Notion API), `NeuralCleave-google-calendar` (`calendar_list_events` tool, Calendar API v3). Each reads its credential from an environment variable in its `Plugin.__init__` and hands it to the `Tool` it constructs; each tool catches network/HTTP/missing-dependency failures and returns `ToolResult.error` rather than raising. 37 tests combined, 100% coverage per package, all wired into CI (lint + test on every push), and all published to PyPI alongside the SDK.

**Client SDK — not started.** A thin Python (and optionally JS/TS) library wrapping the existing REST API (`/api/v1/status`, `/channels`, `/memory/*`) and the WebSocket chat protocol, for external apps that want to talk to a running neuralcleave gateway programmatically. The API surface already exists; this would just be an ergonomic wrapper + published package. Worth building once there's a concrete external consumer asking for it.
