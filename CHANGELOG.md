# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0] - 2026-07-17

**Launch release — full OpenClaw parity achieved; CortexFlow leads in 13 capability categories.**

### Added — Channels (32 total, up from 12)

- `LineAdapter` — HMAC-SHA256 webhook; push-message API; user/group/room targets; echo guard
- `FeishuAdapter` — v1 + v2 event schema routing; tenant access token cache; open_id/chat_id targets
- `ZaloAdapter` — HMAC-SHA256 webhook; OAuth2 refresh token with auto-renewal; Zalo OA v3 CS API
- `WeChatWorkAdapter` — SHA1 URL challenge; XML inbound; access token cache; touser/toparty/totag targets
- `QQBotAdapter` — Ed25519 webhook; op=13 challenge; AT/C2C/GROUP/DIRECT events; QQBot auth header
- `TlonAdapter` — Urbit Eyre HTTP API; SSE channel; legacy + modern Tlon letter formats; poke via chat-action-1
- `iMessageAdapter` — BlueBubbles REST polling; direct/SMS/group targets; isFromMe skip; echo guard
- `GoogleChatAdapter` — JWT service account OAuth2; space + thread targets; verification token
- `MessengerAdapter` — Meta Graph API v19.0; HMAC-SHA256 webhook; text/attachment/postback events
- `RocketChatAdapter` — DDP WebSocket; REST v1 login; stream-room-messages; SHA-256 password digest
- `BlueskyAdapter` — AT Protocol XRPC polling; app-password auth; JWT auto-refresh; threaded replies
- `ViberAdapter` — REST + HMAC-SHA256 webhook; 7,000-char send limit; 7 inbound event types
- `XMPPAdapter` — slixmpp asyncio; MUC rooms (XEP-0045); XEP-0199 ping; SCRAM-SHA-1
- `NostrAdapter` — NIP-04 encrypted DMs; pure-Python secp256k1 + BIP-340 Schnorr; multi-relay
- `SynologyChatAdapter` — SYNO.Chat.External API; outgoing webhook; user/channel/int targets
- `TwitchAdapter` — IRC-over-WebSocket; IRCv3 tags; multi-channel join; auto-reconnect
- `TwilioVoiceAdapter` — multi-turn speech via asyncio.Future + TwiML; HMAC-SHA1 verification
- `QQBotAdapter` — guild + C2C + group + DM events; access token cache (7200 s, 60 s buffer)
- `WeChat Work` — aiohttp webhook; XML inbound; access token cache; full send-target support

### Added — LLM Providers (13 total, 19 model aliases)

- Mistral AI — `api.mistral.ai`; `mistral-large` in complex_reasoning routing
- xAI Grok — `api.x.ai`; `grok-3` in complex_reasoning routing
- Cohere v2 — `api.cohere.com`; bespoke v2 response parser; `command-r-plus` in summarization
- Moonshot AI / Kimi — `api.moonshot.cn`; `moonshot-v1-8k` in general routing
- Zhipu AI GLM — `open.bigmodel.cn`; `glm-4-flash` in intent_extraction + cheap_inference
- Alibaba Qwen / DashScope — `dashscope.aliyuncs.com`; `qwen-max` in code_generation + code_review
- Baidu ERNIE / Qianfan — `qianfan.baidubce.com`; `ERNIE-Speed-128K` in cheap_inference
- ByteDance Doubao / Ark — `ark.cn-beijing.volces.com`; `doubao-lite-4k` in cheap_inference
- 14 provider aliases added (`kimi`, `xai`, `zhipu`, `alibaba`, `baidu`, `bytedance`, …)
- All 8 new providers accept `ENV:VAR_NAME` resolution via `resolve_secret()`

### Added — Multi-Agent Orchestration (`cortexflow_ai/orchestrator/`)

- `AgentNodeConfig` — named sub-agents with model_override, task_types, routing_keywords, channel_patterns (glob), priority, max_concurrent, enabled
- `AgentOrchestrator` — filter → fallback → priority → round-robin routing pipeline; `NoEligibleNodeError` / `NodeNotFoundError`
- `MemoryNamespaceStore` — LRU key-value store per node; configurable max_entries (default 1000); put/get/delete/search/list_by_tag/clear/stats
- `MemoryNamespaceManager` — lazy namespace registry; global_stats; namespace isolation by default, explicit sharing via `memory_namespace` field
- 7 REST endpoints under `/api/v1/orchestrator/` — nodes CRUD + route + status + memory + namespaces
- `cortex orchestrate list/add/remove/route/status` CLI

### Added — Hub Marketplace (`cortexflow_ai/hub/`)

- `PackageScanner` — dual-pass safety: AST walk (13 blocked imports) + regex (14 dangerous patterns); pre-install gate
- `HubRegistry` — `~/.cortexflow/hub/registry.json` backed; list/search/get/add/remove/enable/disable
- `HubInstaller` — async install (https + data URI fetch, SHA-256 checksum, scanner gate, SkillWriter integration)
- 8 REST endpoints `/api/v1/hub/`; 9 CLI commands `cortex hub list/search/install/remove/info/enable/disable/scan/status`

### Added — Self-Modifying Skills (`cortexflow_ai/skills/`)

- `SkillWriter` — AST validate + blocked-import check; persist to `~/.cortexflow/skills/{name}/skill.py`; hot-load via importlib
- `DynamicPlugin`, `DynamicFunctionTool` — auto-wrap plain functions with type-hint inference
- `WriteSkillTool`, `ListSkillsTool`, `DeleteSkillTool` — LLM-callable tools for writing skills in conversation
- `cortex skills write/list/show/delete/validate` CLI

### Added — Visual Canvas (`cortexflow_ai/canvas/`)

- `CanvasBlock` — 7 block types: text, markdown, image, table, code, chart, html; JSON serialization
- `CanvasRenderer` — 200-block ring buffer; async WebSocket broadcast; dead-subscriber cleanup
- `CanvasTool` — 9 LLM-callable actions; auto-wired in gateway lifespan
- 4 REST endpoints; real-time `/ws/canvas`; live HTML page at `/canvas` (bar/line/pie via Canvas API)
- `cortex canvas open/status/clear/render` CLI

### Added — Progressive Web App (`cortexflow_ai/pwa/`)

- `build_manifest()` — W3C Web App Manifest; start_url=/app; display=standalone; 192 + 512 SVG icons
- `PushManager` — file-backed VAPID subscription store; `generate_vapid_keys()` (EC P-256)
- Service Worker — cache-first shell; network-first /api/ + /ws/; Web Push; notificationclick focus
- Full WebSocket chat UI: hello/ping/message_chunk/message_done protocol; install-prompt banner; iOS safe-area

### Added — Sandbox (`cortexflow_ai/sandbox/`)

- `LocalSandbox` — asyncio subprocess; sanitised env (strips all API key prefixes)
- `DockerSandbox` — `--rm --network none --memory --cpus --security-opt no-new-privileges`
- `SSHSandbox` — asyncssh primary; ssh-CLI fallback; password/key-file/agent auth
- `SandboxManager` — factory with `local()`/`docker()`/`ssh()`/`from_config()`

### Added — Desktop & Installation

- Tauri 2.x sidecar pipeline — `lib.rs` sidecar spawn; `bundle_backend.ps1`; `cortexflow-backend.spec`; system tray; Ctrl+Shift+Space hotkey; single-instance guard; close-to-tray
- `AutostartManager` — Windows registry (`HKCU\...\Run`); macOS launchd; Linux systemd user service; `cortex autostart enable/disable/status`
- `scripts/install.sh` (Linux/macOS) + `scripts/install.ps1` (Windows) — detect Python 3.12+, pip-install, `cortex init -y` non-interactive
- `cortex cloud generate/check/status` — Dockerfile, docker-compose, railway.toml, render.yaml manifests; 5-platform auto-detection

### Added — Tools

- `ShellTool` — allowlist (30+ safe programs); `shell=False`; sandbox `~/cortexflow_files/`; 50 KB output cap; UTF-8; hard timeout
- `BrowserTool` / `BrowserAutomationTool` — headless Chromium via Playwright; 10 actions; domain allowlist; 100 KB text cap
- `FileOpsTool` extended — append / move / copy / mkdir / stat / search added (10 total); `allowed_paths` for full host access; 512 KB read cap with `truncated` flag
- `ContinuousVoiceListener` — always-on microphone; RMS energy VAD; configurable silence/min/max durations; async callbacks; `cortex voice listen` CLI

### Added — Proactive Scheduler

- `HeartbeatScheduler` — async tick loop; interval + cron scheduling; 5-field cron engine (no external dep); `ScheduledTask` with timeout, retry, one-shot; wired into FastAPI lifespan

### Added — Security

- Optional `X-API-Key` HTTP middleware — enforced on `/api/*` when `gateway.api_key` is non-empty; `/health` and `/ws/*` always exempt; `ENV:` resolution supported
- `GatewayConfig.api_key` — new optional config field (default empty, auth disabled)
- 8 new `ModelsConfig` provider key fields — `mistral_api_key` through `ark_api_key`; all support `ENV:` resolution

### Added — Skill Hot-Reload

- `reload_plugin(name)` / `reload_all()` on `PluginRegistry` — `on_unload` → unwire → re-discover → `on_load` → wire; zero gateway restart
- `POST /api/v1/plugins/{name}/reload`; `cortex plugins reload [name]`

### Added — Frontend Pages (Tauri / browser)

- Terminal page — embedded xterm.js terminal connecting to `/ws/terminal`
- Skills page — calls `/api/v1/hub/packages`; tag chips; PackageScanner security badge
- Orchestrator page — agent node cards with per-node memory stats
- Canvas page — live agent reasoning graph viewport; calls `/api/v1/canvas/state`

### Added — CI/CD

- `.github/workflows/build-tauri.yml` — `actions/setup-python@v5` + pip install + platform-specific bundle step; CORTEXFLOW_SKIP_BUNDLE env-var for CI PyInstaller dedup
- `bundle_backend_dispatch.js` — cross-platform sidecar build script

### Added — Test Coverage

- 5,064 tests passing (was ~2,500 at 2.0.0)
- New test suites: gateway auth (21), config extended (35), update_checker edge cases (25), orchestrator routing extended (41), frontend contract tests (25), and all feature suites above

### Fixed

- Canvas page calling non-existent `/api/v1/canvas/snapshot` → now calls `/api/v1/canvas/state`
- Skills page calling non-existent `/api/v1/skills` → now calls `/api/v1/hub/packages`
- `AgentNodeConfig` field `channel_patterns` correctly used throughout (was `routing_channels` in some test helpers)
- `get_latest_version()` httpx patch path corrected (httpx imported inside function body)

---

## [2.0.0] - 2026-06-01 *(baseline before gap-closing sprint)*

Initial public release of the personal AI assistant gateway. Core features:

- FastAPI gateway with WebSocket streaming (`message_chunk` / `message_done`)
- `AgentRuntime` → `ModelRouter` → `ReflectionEngine` pipeline
- 3-tier memory: Redis (hot) → Qdrant (vector ANN) → SQLite (long-term, importance-scored)
- 5 LLM providers: Anthropic, Gemini, DeepSeek, Ollama, OpenAI
- 12 channel adapters: Telegram, Discord, Slack, Email, WhatsApp, SMS/Twilio, Matrix, IRC, Signal, Microsoft Teams, Mattermost, Mastodon, Nextcloud Talk, Generic Webhook, WebSocket/REST
- `cortexflow-sdk` typed ABC plugin system with PEP 451 entry-point discovery
- 13 Prometheus-compatible metrics; `JsonFormatter` structured logging
- `cortex` CLI with init, chat, status, config, version, update commands
- TOML config with `ENV:` secret resolution and typed dataclasses
