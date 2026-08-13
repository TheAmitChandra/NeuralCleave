# NeuralCleave vs OpenClaw — Refreshed Gap Analysis & Build Plan
**2026-08-13 | Supersedes `COMPETITIVE_STRATEGY_2026_08.md` for gap-tracking purposes**

> That earlier doc's P0–P10 list (semantic memory embeddings, orchestrator wiring, canvas WebSocket, MCP server, settings UI for all providers, config hot-reload, exec approval, Mintlify docs, skills gallery, multi-step tool chains) was closed across PRs #114–#119 (2026-08-07/08, per project memory). This document verifies those claims against current source (not against the old doc's assumptions), re-surveys OpenClaw at its current version, and sets the next build priorities. Keep the old doc for the "why we're different" narrative; treat this one as the current status + roadmap source of truth.

**Method note:** every claim below about NeuralCleave was checked against actual source in this repo (file paths + line evidence), not against prior memory or docs. Every claim about OpenClaw was checked against its actual `package.json`/README/source files at `c:/Amit-Projects/AI-Projects/Openclaw`, not against the old comparison table (which had at least one stale claim — see §4).

---

## 1. Headline verdict

The P0–P10 punch list is genuinely closed — nine of ten items are real, working code, not stubs. One item (privacy audit) is **half-wired**: the audit log and report endpoints exist, but nothing in the actual provider call path ever writes to it, so the "privacy audit" is currently silent in production. That's the same bug shape as the old "`embedding=None`" issue — infrastructure built, integration point never connected. It's the single highest-value fix in this document.

Beyond that, closing the old list mostly cleared *known* debt — it didn't close the *structural* gap with OpenClaw, which comes from OpenClaw simply being a much bigger, more heavily funded project (200+ contributors, calendar-versioned releases, ~150 extensions). Re-surveying OpenClaw at v2026.8.1 surfaced several capability categories NeuralCleave has zero presence in (media generation, computer-use/screen control, secrets vaulting, agent-CLI delegation) that weren't in the original gap list at all. Those are now §5 below.

---

## 2. NeuralCleave: verified current state (post PR #119)

| # | Claim from old doc | Verified status | Evidence |
|---|---|---|---|
| 1 | Semantic memory embeddings wired | ✅ **Genuinely fixed** | `neuralcleave/memory/embedder.py` — lazy-loaded `all-MiniLM-L6-v2` singleton, async `encode()` via thread-pool executor, real vectors flow into `MemoryRetrievalPipeline.retrieve()`. Not a stub. |
| 2 | Orchestrator wired into gateway | ✅ **Fixed** | `neuralcleave/gateway/main.py:90-97` — `AgentOrchestrator()` constructed and `set_orchestrator()` called in lifespan startup, with a caught-and-logged failure path. |
| 3 | Canvas WebSocket connected in frontend | ✅ **Fixed** | `frontend/.../canvas/page.tsx:510-541` — real `new WebSocket(.../ws/canvas)` subscription with 5s-poll fallback if the socket drops. |
| 4 | MCP server support | ✅ **Server done**, ⚠️ **no client** | `neuralcleave/mcp/server.py` implements real JSON-RPC 2.0 `tools/list` + `tools/call`. But `neuralcleave/mcp/spawn.py` only spawns/manages NeuralCleave's *own* server subprocess — there is no code anywhere that connects **out** to a third-party MCP server. OpenClaw is bidirectional; NeuralCleave is server-only. |
| 5 | Settings UI for all 13 providers | ✅ **Fixed** | `frontend/.../settings/page.tsx` — all 8 previously config.toml-only providers (Mistral, xAI, Cohere, Moonshot, Zhipu, Qwen, ERNIE, Doubao) now have password-type key fields, a provider dropdown, and payload wiring (lines 24-31, 177-184, 800-807). |
| 6 | Config hot-reload | ✅ **Present** | `neuralcleave/gateway/config_watcher.py` exists; `watchfiles>=0.21.0` is a declared dependency; referenced from `cli.py`, `hub/installer.py`, `gateway/routes.py`. |
| 7 | Exec approval manager | ✅ **Fixed** | `neuralcleave/tools/approvals.py` — `ApprovalQueue` with async `Event`-gated `ApprovalRequest`, `POST /approvals/{id}/approve|deny` routes, `ShellTool` awaits the gate before running when `require_approval=True`. |
| 8 | Multi-step tool chains | ✅ **Fixed** | `neuralcleave/agent/pipeline.py:458` `_run_tool_chain()`, bounded by `max_tool_steps` (constructor param, default `_MAX_TOOL_STEPS`), metric `tool_chain_depth` recorded in `observability/metrics.py`. See caveat in §3. |
| 9 | Privacy audit | ⚠️ **Half-wired — functionally silent** | `neuralcleave/privacy/audit.py` (`PrivacyAuditLog`, module singleton `AUDIT_LOG`) and `neuralcleave/privacy/middleware.py` (`AuditTransport`, an `httpx.AsyncBaseTransport` wrapper) both exist and are well-built. But `neuralcleave/models/router.py` — where all 13 providers actually make their 7 separate `httpx.AsyncClient()` calls — **never imports or wraps with `AuditTransport`**. `AUDIT_LOG` is only ever *read* (by the report/clear routes in `gateway/routes.py`); nothing in the real request path ever *writes* to it. The privacy report endpoint will always return empty in production. See §5.1 — this is the top-priority fix. |
| 10 | Mintlify docs | ✅ **Done**, ⚠️ **duplicated** | `mintlify-docs/` has 27 real MDX pages (Getting Started, Architecture, full API reference incl. MCP/approvals/privacy/voice, Voice section, Skills gallery, Changelog). But the old static-HTML `docs-site/` (CNAME, its own `docs/` subtree, GitHub Pages deploy) is still present and presumably still deployed — two documentation sites now exist with unclear source-of-truth. |
| 11 | Skills gallery | ✅ **Fixed** | 22 example skills under `skills/examples/` (calendar, GitHub, Jira, Linear, Notion, Obsidian, Spotify, weather, HuggingFace classify, translate, system monitor, pomodoro, etc.) plus `mintlify-docs/skills-gallery.mdx`. |
| 12 | Voice UI page | ✅ **Fixed** | `frontend/.../voice/page.tsx` with wake-word, transcript, and subsystems sections, 7 dedicated test files. |

**Additional finding — streaming tool use is still buffered.** `neuralcleave/agent/pipeline.py:260` comment: *"When tools are registered, buffer the first generation so we can [detect TOOL_CALL: markers]."* Multi-step tool chains (item 8) now loop correctly, but **each individual step in the chain still non-streams** — the model's first-pass generation is fully buffered before the client sees anything, whenever tools are registered. The old doc's "streaming tool use: No" gap is *narrower* now (only affects tool-using turns) but not closed.

### 2.1 Current top-line facts
- **Version**: 2.1.5 (unchanged — per [[feedback_versioning]], no bump until full parity launch)
- **Channels**: 31 adapter files in `neuralcleave/channels/` (Telegram, Discord, Slack, WhatsApp, Signal, Matrix, IRC, XMPP, Nostr, Bluesky, Tlon, LINE, Feishu, WeChat Work, QQ Bot, Zalo, Mastodon, Twitch, Viber, SMS, Email, Mattermost, Nextcloud, RocketChat, Google Chat, Synology, iMessage, Messenger, Twilio Voice, Webhook, Teams)
- **LLM providers**: 13, confirmed exactly against `models/router.py` (gemini, anthropic, openai, deepseek, ollama, mistral, xai, cohere, moonshot, zhipu, qwen, ernie, doubao)
- **Tests**: 6,171 test functions found under `tests/` (up from 6,016 at last snapshot)
- **Mobile**: confirmed absent — no react-native/capacitor/expo in `frontend/package.json`
- **Media generation**: confirmed absent — no image/video/music generation code anywhere in `neuralcleave/`

---

## 3. OpenClaw: refreshed snapshot (v2026.8.1, as of 2026-08-13)

Verified directly against `c:/Amit-Projects/AI-Projects/Openclaw` — `package.json` files opened for ~150 of the ~150 `extensions/` subpackages, plus `apps/`, `packages/`, `docs/agent-runtime-architecture.md`, `VISION.md`, `SECURITY.md`.

### 3.1 Extensions, by category (verified via package.json descriptions)
| Category | Count (approx) | Notable entries |
|---|---|---|
| LLM/model providers | **45+** | anthropic, anthropic-vertex, openai, google, mistral, cohere, deepseek, qwen, qianfan (Baidu), volcengine (Doubao), moonshot, zai (Zhipu), amazon-bedrock (+ mantle), azure/microsoft-foundry, cloudflare-ai-gateway, vercel-ai-gateway, openrouter, together, fireworks, featherless, arcee, baseten, cerebras, chutes, deepinfra, gmi, kilocode, longcat, meta, minimax, novita, nvidia, sglang, stepfun, synthetic, tencent, venice, vllm, xai, xiaomi, huggingface, llama-cpp, ollama, lmstudio |
| Messaging channels | **~28** | discord, slack, telegram, whatsapp, signal, matrix, irc, imessage, line, feishu, googlechat, msteams, mattermost, nextcloud-talk, synology-chat, zalo/zalouser, twitch, nostr, tlon, sms, webhooks, reef (E2E-encrypted claw-to-claw), buzz, clickclack, raft, qa-channel, mxc |
| Voice/meeting channels | **4** | google-meet, teams-meetings, zoom-meetings (all browser-automation meeting participants), voice-call (real phone calls via Twilio/Telnyx/Plivo) |
| Speech (STT/TTS) | **9** | elevenlabs, azure-speech, fish-audio-speech, inworld, gradium, microsoft, deepgram, senseaudio, tts-local-cli — plus native MLX TTS in the macOS app |
| **Media generation** | **7** | alibaba (video), fal, comfy (ComfyUI), runway, pixverse, plus `image-generation-core`/`video-generation-providers`/`music-generation-providers` shared packages — **NeuralCleave has zero equivalent** |
| Memory | **4** | memory-core, memory-lancedb (real vector embeddings), memory-wiki (persistent wiki), active-memory |
| Web search / extraction | **9** | brave, exa, tavily, firecrawl, duckduckgo, searxng, perplexity, parallel, web-readability, document-extract, file-transfer |
| **Computer-use / agent harness** | **6** | cua-computer (Windows/Linux screen control), openshell (NVIDIA OpenShell sandbox + SSH), browser (tool), **codex, copilot, opencode, opencode-go, kilocode — lets OpenClaw drive Claude Code/Codex/GitHub Copilot/OpenCode CLIs as sub-harnesses** |
| Security/secrets | **4** | vault (HashiCorp), onepassword (1Password SecretRef broker), policy (doctor conformance checks), device-pair (Ed25519 device pairing) |
| Diagnostics | **2** | diagnostics-otel (OpenTelemetry traces/metrics/logs), diagnostics-prometheus |
| Migration | **2** | migrate-claude, migrate-hermes — **one-click import from competing assistants** |
| Dashboard | **1** | workboard — a task/work-board plugin for the Control UI |

### 3.2 Native apps (file counts — real apps, not stubs)
| App | Files | Notes |
|---|---|---|
| iOS | 508 | Swift; WatchOS support lives partly in `apps/shared` |
| Android | 659 | Kotlin; Wear OS support |
| macOS | 526 | Swift menu-bar app |
| Linux | 54 | Tauri-based, much lighter than macOS |
| macOS MLX TTS | 5 | local Apple-silicon TTS sidecar |
| **Windows** | **0 (no directory)** | **Correction to the prior doc**: there is no native Windows app anywhere in the repo — no `apps/windows`, no WinUI references outside a `windows-cmd-helpers.mjs` build script. The old comparison table's "Windows (WinUI)" claim was wrong. OpenClaw's Windows story is the same Lit/Vite Control UI web dashboard every platform gets. **NeuralCleave's Tauri v2 desktop app, which ships real Windows/macOS/Linux installers, is arguably ahead of OpenClaw specifically on Windows.** |

### 3.3 Core architecture
- **Agent runtime** (`packages/agent-core` + `src/agents/`): a proper pluggable harness system. The built-in runtime id is `openclaw`; provider/model config can select a different registered harness (e.g. hand a request off to the `codex` harness). Supports "model runtime generations" — atomic, versioned snapshots of the model/auth/catalog state, so a config reload can never serve a half-updated generation. This is more mature than anything in NeuralCleave's single-process `ModelRouter`.
- **MCP**: confirmed bidirectional — both an MCP server (exposing OpenClaw's own channels/tools) and an MCP client (per `docs/cli/mcp.md`, connecting outbound to other MCP servers). NeuralCleave has only the server half (§2, item 4).
- **`tool-call-repair` package**: a dedicated package for repairing malformed/hallucinated LLM tool-call output — a reliability primitive NeuralCleave's regex-based `TOOL_CALL:` parsing doesn't have an equivalent for.
- **Security posture** (`SECURITY.md`, `extensions/policy`, `extensions/device-pair`): `openclaw doctor --fix` migrates old config shapes automatically; device pairing uses Ed25519 challenge signing; a dedicated `policy` extension runs conformance checks.
- **Governance** (`VISION.md`): deliberately keeps core lean and pushes new capability into the plugin system — "recurring demand defines interfaces," i.e. once 2-3 plugins converge on the same need, that becomes a core contract. Explicitly will not merge: agent-hierarchy/manager-of-managers frameworks, or heavy orchestration layers duplicating existing infra. Useful context: OpenClaw's own maintainers are *not* trying to build what NeuralCleave's multi-agent orchestrator does — this is a place NeuralCleave can differentiate rather than chase.

---

## 4. Corrections to the prior comparison table

- **Windows desktop**: prior doc credited OpenClaw with "macOS Swift + Linux Tauri + **Windows WinUI**." No Windows app exists in the current source. NeuralCleave's Tauri v2 installer is the more complete Windows-native story between the two projects.
- **MCP**: prior doc marked this a flat OpenClaw win. Still true, but now more precisely: NeuralCleave has closed the *server* half; only the *client* half remains open.
- **Multi-step tool chains**: prior doc listed "single-round-trip only" as fully open. Now partially closed — chains work, but each step is non-streaming (see §2 caveat).

---

## 5. Newly identified gaps (not in the original P0–P10 list)

Ranked by build-plan priority in §6; this section just states what's missing and why it matters.

### 5.1 Privacy audit log is wired to nothing (the new "embedding=None")
`AuditTransport` exists, is well-designed, and is completely unused by the actual provider call path. Anyone who runs `neuralcleave privacy report` today gets an empty report regardless of how many external API calls were made. This directly undermines the "privacy-first, auditable" positioning claim from the last doc — right now that claim is not true in practice.

### 5.2 No MCP client
OpenClaw both serves and consumes MCP. NeuralCleave only serves. Without outbound MCP client support, NeuralCleave's self-modifying skills story and OpenClaw's growing MCP ecosystem stay disconnected — a NeuralCleave user can't point their assistant at an external MCP server (e.g. a company's internal tools server) the way an OpenClaw user can.

### 5.3 Zero media generation
Image/video/music generation is a full capability category (7 dedicated OpenClaw extensions) that NeuralCleave doesn't touch at all. This is increasingly a baseline expectation for a "personal AI assistant," not a nice-to-have.

### 5.4 No computer-use / bundled browser automation
OpenClaw bundles CDP-based browser automation and has an experimental Windows/Linux screen-control driver (`cua-computer`). NeuralCleave's browser automation (Playwright) requires a separate manual install — this is real onboarding friction, and "computer use" is becoming a headline capability across the industry (Claude, ChatGPT Operator, etc.).

### 5.5 No secrets-vault integration
`vault` (HashiCorp) and `onepassword` extensions let OpenClaw resolve API keys from an external secrets manager instead of plaintext config/env vars. Given the stated enterprise-pitch goal ([[user_amit]]), credential-handling maturity is a real procurement checkbox NeuralCleave currently fails.

### 5.6 No agent-CLI delegation ("harness" pattern)
OpenClaw can hand a conversation off to Claude Code, Codex, GitHub Copilot CLI, or OpenCode as a sub-harness. This is a distinctive integration pattern with no NeuralCleave equivalent, and it's a natural extension of NeuralCleave's existing "AI writes its own tools" philosophy — instead of only writing new Python skills, the assistant could delegate to a full coding agent for large tasks.

### 5.7 No import/migration tooling
`migrate-claude` and `migrate-hermes` let a user switch to OpenClaw with their existing assistant history intact. NeuralCleave has no equivalent — and ironically, a "migrate from OpenClaw" importer would be a direct conversion tool aimed at OpenClaw's own installed base.

### 5.8 Provider count and specific enterprise-relevant gaps
13 vs 45+. Most of the delta is long-tail providers that don't matter, but two do: **Amazon Bedrock** and **Azure OpenAI/Foundry** are frequently hard procurement requirements for enterprise buyers, and **OpenRouter** is a single integration that transitively unlocks ~100 more models — disproportionate ROI for one adapter.

### 5.9 Two documentation sites
`docs-site/` (old static HTML, still has its own GitHub Pages deploy config) and `mintlify-docs/` (new, 27 pages) both exist. No indication which is authoritative post-PR-#118. Needs an explicit decision (retire one, or split responsibilities — marketing landing page vs. docs — and say so).

### 5.10 No distributed tracing
NeuralCleave has Prometheus metrics + structured JSON logs; OpenClaw adds an OpenTelemetry exporter (`diagnostics-otel`) on top of its Prometheus one. Minor gap, worth a small addition given the enterprise-observability angle.

---

## 6. Recommended build order

### P0 — Wire `AuditTransport` into `models/router.py` (this week)
Wrap each of the 7 `httpx.AsyncClient()` instantiations in `neuralcleave/models/router.py` with `AuditTransport`, passing the active session id. This is a small, mechanical change (the transport class is already correct) that turns a currently-false claim ("auditable privacy") into a true one. Highest ratio of trust-repair to effort in this whole document.

### P1 — MCP client
Add outbound MCP client support in `neuralcleave/mcp/` (connect to a configured external MCP server over stdio/SSE, discover its tools, register them into the existing `ToolRegistry`). Closes the bidirectional gap and lets NeuralCleave's skills reach outside its own process.

### P2 — Un-buffer tool-call streaming
The pipeline still buffers the entire first generation whenever tools are registered (`pipeline.py:260`). Stream tokens normally and only pause/buffer once a `TOOL_CALL:` line prefix is detected mid-stream, resuming streaming for any text before/after it. Removes the last major perceived-latency gap for tool-using conversations.

### P3 — Consolidate the two documentation sites
Decide `docs-site/`'s fate explicitly: either retire it in favor of `mintlify-docs/` (with a redirect), or repurpose it as a pure marketing landing page that links out to Mintlify for actual docs. Either is fine; the ambiguous current state isn't.

### P4 — OpenRouter + Bedrock + Azure providers
Three provider adapters, following the existing `ModelRouter` pattern. OpenRouter alone gives disproportionate model-count coverage; Bedrock/Azure remove two common enterprise procurement blockers.

### P5 — Bundle browser automation
Make Playwright (or a lighter CDP client) a default dependency instead of a manual install, and expose it as a first-class tool the same way `ShellTool` is exposed, gated behind the existing approval manager (§2 item 7 already provides the gate — reuse it).

### P6 — One image-generation provider
Pick one (fal.ai or a local Stable Diffusion/diffusers path, in keeping with the "AI-native Python stack" positioning) and wire it as a tool. Closes the media-generation category from zero to one, which is the highest-leverage step (0→1 matters more than 1→7).

### P7 — "Migrate from OpenClaw" importer
A CLI command that reads OpenClaw's config/session export format and produces a NeuralCleave `config.toml` + channel setup. Directly targets OpenClaw's installed base for conversion — unusually high leverage for a solo-dev competitive move.

### P8 — Secrets-vault integration
A `SecretRef`-style resolver supporting at minimum 1Password (broadest individual/small-team adoption) so API keys don't have to live in plaintext config. Follows the existing `ENV:VAR` resolution pattern already in the config loader — this is additive, not a rewrite.

### Deliberately not prioritized
- **Native mobile (iOS/Android)**: OpenClaw's biggest structural advantage (1,100+ combined native app files) and not realistically closable solo. Keep leaning on the PWA story instead of chasing this — it's the correct call, not a gap to feel bad about.
- **Agent-CLI delegation (§5.6)** and **workboard-style dashboard**: interesting, but lower urgency than P0–P8. Revisit after the above land.
- **Chasing the full 45-provider count**: most of the long tail (Baseten, Chutes, Arcee, Featherless, etc.) has negligible user demand; P4's three providers capture nearly all the real-world value.

---

## 7. One-paragraph summary for future sessions

As of 2026-08-13, NeuralCleave's PR #114–#119 fixes are real (9/10 fully verified working), with one half-wired exception: the privacy audit log never actually records real provider traffic because `AuditTransport` isn't plugged into `models/router.py` — fix that first. OpenClaw at v2026.8.1 remains structurally ahead on scale (45+ providers, native mobile, media generation, computer-use, secrets vaulting, agent-CLI delegation) simply by virtue of being a much larger project, but one long-standing comparison claim was wrong (OpenClaw has no native Windows app — NeuralCleave's Tauri build is actually ahead there). The next-highest-leverage moves are: wire the audit transport (P0), add an MCP client (P1), un-buffer tool-call streaming (P2), and pick up OpenRouter/Bedrock/Azure as providers (P4) — all small, mechanical changes with outsized trust or capability payoff, before considering any large new category (media generation, computer-use, mobile).
