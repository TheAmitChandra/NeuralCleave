# NeuralCleave vs OpenClaw — Gap Analysis & Build Plan (Round 3)
**2026-08-17 | Supersedes `COMPETITIVE_ANALYSIS_2026_08_13.md` for gap-tracking purposes**

> The 2026-08-13 doc's P0–P8 list (privacy-audit wiring, MCP client, un-buffered tool streaming, docs-site consolidation, OpenRouter/Bedrock/Azure providers, bundled browser automation, fal.ai image generation, an OpenClaw config importer, and 1Password secrets + a 19-file channel `_resolve` consolidation) is **fully closed**, per PRs #126–#131 (2026-08-14 through 2026-08-16). This document does not re-verify those — see project memory (`project_pr131_p8_gap_analysis.md`) for the closing PR. It re-surveys both projects at their current state and sets the next build priorities.

**Method note:** every NeuralCleave claim below was checked against actual source in this repo (file/line evidence), not against prior docs or memory. Every OpenClaw claim was checked against its current source/docs at `c:/Amit-Projects/AI-Projects/Openclaw` (which has continued shipping heavily — PR numbers now in the 122000+ range, well past the 2026-08-13 snapshot).

---

## 1. Headline verdict

The structural gap from the 08-13 doc (OpenClaw being a much bigger, multi-platform, heavily-funded project with native iOS/Android/macOS apps, a browser extension, and a plugin marketplace) hasn't changed and isn't closable solo — that verdict stands and isn't repeated here. What *is* new: with the 08-13 list closed, a fresh backend/gateway-focused comparison surfaces a different flavor of gap than last time. Round 2 was about **wiring things that already existed but were disconnected** (audit log, providers). Round 3 is more about **operational maturity a real deployment needs but NeuralCleave hasn't built yet**: durable state (backup/restore, a privacy audit log that survives a restart), operational visibility (cost tracking, provider health, host metrics), and a couple of cheap provider/tool breadth wins (fast-inference LLM providers, better web search backends).

None of these are individually hard. All are portable to a solo Python dev. The common thread is "things you notice are missing the first time you run this in anger for a few weeks," not "things you notice on day one."

---

## 2. NeuralCleave: current state snapshot (post PR #131)

- **Version**: 2.1.6 (unchanged — per [[feedback_versioning]], no bump until full-parity launch)
- **Channels**: 34 adapter files — already covers every text/chat platform in OpenClaw's channel list, plus several OpenClaw lacks entirely (Bluesky, Mastodon, QQ, RocketChat, Viber, WeChat Work, XMPP). **Not a gap category this round** — see §4 finding 15.
- **LLM providers**: 16, confirmed against `neuralcleave/models/router.py` (anthropic, google, deepseek, ollama, openai, mistral, xai, cohere, moonshot, zhipu, qwen, ernie, doubao, openrouter, azure, bedrock).
- **Secrets**: `ENV:` and `op://` (1Password CLI) both resolve through one shared `config.resolve_secret()`, used by all providers and all 19 previously-duplicated channel adapters.
- Everything else from the 08-13 snapshot (semantic memory, orchestrator, canvas WS, MCP server+client, config hot-reload, exec approvals, multi-step tool chains, un-buffered streaming, privacy audit *recording*, Mintlify docs, skills gallery, OpenClaw importer) still holds and isn't re-litigated here.

---

## 3. OpenClaw: what's changed since 08-13

OpenClaw's `CHANGELOG.md` "Unreleased" section alone lists dozens of shipped items since the last survey — Fish Audio speech, ClickClack channel, Buzz (Nostr-based) channel improvements, Control UI dashboard/session/permission work, GPT-5.6 support, a `backup sqlite create|list|verify|restore` CLI, Skill Workshop history-review self-learning, and much more. Most of it is either (a) already covered by NeuralCleave in some form, (b) native-app/browser-extension/Control-UI-specific and out of reach for a solo Python backend, or (c) team-scale (channel-specific work like Buzz/ClickClack that assumes dedicated maintainers per integration).

The findings below are the subset that is genuinely new, backend/gateway-relevant, and realistically portable.

---

## 4. Newly identified gaps

Ranked by build-plan priority in §5; this section states what's missing and why it matters. Each finding was checked against both repos' actual source, not changelogs alone.

### 4.1 Privacy audit log has no persistence
`neuralcleave/privacy/audit.py` docstrings say outright that "there is no persistence — the log resets on restart"; it's a plain Python list behind a `threading.Lock`. OpenClaw's audit ledger lives in its shared SQLite state DB and survives restarts. Given that a durable, auditable privacy trail is an explicit part of NeuralCleave's enterprise pitch ([[user_amit]]), an audit log that vanishes on every restart undercuts that pitch the same way the *unwired* audit log did in Round 2 — this is Round 3's version of that same bug shape.

### 4.2 No backup/restore command at all
OpenClaw ships `openclaw backup create|verify|restore`, `backup sqlite create|list|verify|restore` (online SQLite backup API + SHA-256 verification), and `backup git init|create|log|verify|restore`. NeuralCleave's `cli.py` has no `backup` command group whatsoever — confirmed by listing every `@cli.group()` in the file (config, migrate, channels, tools, voice, memory, plugins, cloud, autostart, skills, sandbox, orchestrate, hub, canvas — no backup). A user's entire memory store, config, and skills currently have zero first-party disaster-recovery path.

### 4.3 No cost/usage tracking
`neuralcleave/models/router.py` already records `input_tokens`/`output_tokens` per call at multiple sites, but there is no pricing table, no dollar-cost rollup, and no CLI/API surface to see it (`grep -rln "cost|pricing"` under `neuralcleave/` returns nothing). OpenClaw surfaces per-provider usage/quota via `openclaw status --usage` and `openclaw models status`. The hard part (token counting) is already done in NeuralCleave — only the pricing math and a surface are missing.

### 4.4 Three fast-inference providers missing, nearly free to add
Groq, Together, and Fireworks are absent from `models/router.py` (`grep -rln "groq|together\.ai|fireworks"` across the repo returns nothing), despite NeuralCleave already having a generic OpenAI-compatible request helper (`_generic_openai_compatible_generate`, reused for Mistral/xAI/Moonshot/etc.) that these three would slot into almost verbatim. All three are popular for cheap/fast inference and frequently requested by cost-conscious self-hosters.

### 4.5 Web search tool covers only two weak backends
`neuralcleave/tools/web_search.py` implements only SearXNG (self-hosted) and DuckDuckGo (Instant Answer + HTML scrape fallback) — no Brave, Tavily, Exa, Firecrawl, or Perplexity, all of which OpenClaw supports and all of which are simple HTTP-API integrations with generous free tiers. DDG scraping is the weakest link in NeuralCleave's tool story; this is a low-effort, high-perceived-quality fix.

### 4.6 Exec approvals have no allowlist, no persistence, no channel-forwarded approval
`neuralcleave/tools/approvals.py`'s `ApprovalQueue` is an in-memory dict with binary approve/deny — no persistent glob/argv allowlist (OpenClaw: per-agent `pattern`/`argPattern` allowlist with `security: deny|allowlist|full` + `ask: off|on-miss|always`), and no forwarding of a pending approval into the channel that triggered it. NeuralCleave already has 34 channel adapters, which makes "approve via a reply in Slack/Telegram/Discord" a natural, low-effort extension rather than new infrastructure.

### 4.7 No model-catalog / provider-health CLI
There is no `models` command group in `cli.py` at all. With 16 configured providers, a solo operator has no first-party way to check "which of my configured providers actually have working credentials right now" short of trying each one in a live conversation. OpenClaw's `openclaw models status|list|refresh|scan` does live auth probing with structured failure reasons (`expired`, `rate_limit`, `no_model`, etc.).

### 4.8 No host resource metrics, single flat health check
`neuralcleave/gateway/routes.py`'s `/health` is a constant `{"ok": true}` and `/status` reports only uptime + session count — no CPU/memory/disk. `neuralcleave/observability/metrics.py` has no resource gauges (`grep` for `psutil` across `neuralcleave/` returns nothing). OpenClaw has three-tier health probes (`/health`, `/startup`, `/ready`) plus RSS/heap/event-loop/CPU diagnostics. Cheap to add given NeuralCleave already has a working Prometheus metrics endpoint to attach gauges to.

### 4.9 Reasoning/thinking control is Anthropic-only
`models/router.py` only implements Claude's `extended_thinking`/`thinking_budget_tokens` boolean+budget knob. DeepSeek, Ollama, xAI/Grok, and OpenRouter all natively support some form of `reasoning_effort`/`think` parameter that NeuralCleave doesn't expose at all for those providers. OpenClaw normalizes this into one `/think off|low|medium|high|xhigh|max` ladder mapped per-provider. NeuralCleave already has all the relevant provider adapters — this is incremental wiring, not a new subsystem.

### 4.10 Skill authoring has no review step
`neuralcleave/skills/writer.py`'s `SkillWriter.write_skill()` validates syntax/blocked-imports and then writes **and loads the skill immediately** — no propose → apply/reject/quarantine lifecycle. OpenClaw's Skill Workshop gates every agent-authored skill behind a pending state plus a scanner check before it goes live, and separately mines past sessions in the background to auto-draft skill proposals. A scoped version (pending-state + explicit apply/reject before load) meaningfully raises trust in agent-written code without needing the full self-learning history-scanner.

### 4.11 Plugin system has no install/enable/disable CLI surface
`neuralcleave/plugins/registry.py` only discovers plugins already `pip install`-ed via entry points; `cli.py`'s `plugins` group has only `list` and `reload`. There's no `neuralcleave plugins install <git-url|local-path>`, no persisted enable/disable state, and no trust-confirmation prompt for non-local sources. OpenClaw has a full `plugins search|install|enable|disable|update|uninstall` surface (with explicit `--force` trust gating for non-marketplace sources). Not proposing a hosted marketplace — just the install/enable CLI plumbing, which is realistic without one.

### 4.12 No persistent per-thread task board (lower priority — frontend-heavy)
OpenClaw's bundled (disabled-by-default) Workboard plugin gives a lightweight Kanban surface for agent-owned work cards. NeuralCleave's `orchestrator/task.py` only has `AgentTask`/`AgentResult` dataclasses for node-delegation, no persisted card/board entity or CRUD surface. Directionally interesting given NeuralCleave already has an orchestrator and a Next.js frontend, but this is meaningfully more frontend work than §4.1–4.11 and should rank behind them.

### 4.13 Session dashboards are single-global, not per-thread/capability-scoped (lower priority — heavier lift)
NeuralCleave's `canvas` CLI group + `/api/v1/canvas/status|clear` is one global live-render surface. OpenClaw's per-thread dashboards persist across sessions and gate each widget's network/data/action/prompt access behind an explicit one-time capability grant bound to the exact widget revision. A scoped-down version (per-session pinned blocks + a basic network allow/deny per block) is worth doing eventually but needs a widget sandbox model NeuralCleave doesn't have yet — bigger lift than anything else in this list.

### 4.14 Channels: no material gap (confirmed, not new work)
Checked explicitly this round: OpenClaw's current channel/extension list (discord, feishu, googlechat, imessage, irc, line, matrix, mattermost, msteams, nextcloud-talk, nostr/buzz, signal, slack, sms, synology-chat, telegram, tlon, twitch, webhooks, whatsapp, zalo, clickclack, plus meeting-bot channels requiring Chrome automation + virtual audio) is already matched or exceeded by NeuralCleave's 34 adapters, several of which (Bluesky, Mastodon, QQ, RocketChat, Viber, WeChat Work, XMPP) OpenClaw has no equivalent for. The one open frontier — meeting-bot transcription (Zoom/Teams/Meet captions via headless Chrome) — is newly *plausible* now that NeuralCleave has both browser automation and a voice/STT pipeline, but it's a substantial feature (virtual-audio backend, live-caption scraping), not a priority gap. Flagged as a future "nice to have," not in the build order below.

---

## 5. Recommended build order

### P0 — Persist the privacy audit log
Move `PrivacyAuditLog` from an in-memory list to a SQLite-backed store (NeuralCleave already depends on SQLite elsewhere, e.g. memory store) so audit history survives a gateway restart. Same "trust-repair to effort" ratio as Round 2's P0 (wiring the audit transport) — this closes the other half of that same feature.

### P1 — `neuralcleave backup` command group
Minimum viable version: `backup create` (tar the state dir + config.toml + SQLite DBs), `backup verify` (checksum), `backup restore` (extract to a fresh-target-only path, matching OpenClaw's restore-safety model). Closes a real disaster-recovery gap with no first-party path today.

### P2 — Cost/usage tracking
A static per-model pricing table (`$/1M input tokens`, `$/1M output tokens`) plus a rollup on top of the token counts `models/router.py` already captures, surfaced via a `neuralcleave usage` CLI command and a REST route. Token counting is done; only pricing math and a surface are missing.

### P3 — Groq, Together, Fireworks providers
Three provider adapters following the existing `_generic_openai_compatible_generate` pattern. Nearly copy-paste given the existing generic helper; disproportionate ROI for cost-conscious users.

### P4 — Brave + Tavily web search backends
Add both as alternate `web_search` tool backends alongside the existing SearXNG/DuckDuckGo paths, selectable via config the same way providers are. Directly replaces the weakest link in the current tool story.

### P5 — Exec approval allowlist + channel-forwarded approval
Persistent glob/argv-pattern allowlist per agent (SQLite table) plus `security: deny|allowlist|full` / `ask` modes matching OpenClaw's model, and forward pending approvals as a message in the originating channel (reuse the 34 existing adapters' `send()`) instead of requiring a separate approval UI visit.

### P6 — `neuralcleave models` CLI + host resource metrics
Bundle these as one PR since both are operator-visibility features: a `models list|status` command doing live credential/auth probing per provider, plus `psutil`-based CPU/RSS/disk gauges added to `/api/v1/status` and the Prometheus endpoint, and a real `/ready` check (verifies at least one configured provider + one connected channel are reachable) alongside the existing flat `/health`.

### P7 — Normalized `/think` control across providers
Wire a `off|low|medium|high|xhigh|max` ladder that maps to each provider's native reasoning-effort parameter (DeepSeek/OpenRouter/xAI `reasoning_effort`, Ollama `think`), extending the existing Anthropic-only `extended_thinking` knob. All target providers already exist in `models/router.py`.

### P8 — Skill review step (propose → apply/reject)
Add a pending state to `SkillWriter.write_skill()` so agent-authored skills require an explicit apply/reject before loading, instead of loading immediately. Scoped down from OpenClaw's full Skill Workshop (no background self-learning history scanner) but closes the most trust-relevant part of that gap.

### P9 — Plugin install/enable CLI
`neuralcleave plugins install <git-url|local-path>` (shells out to `pip install`) with an explicit trust prompt for non-local sources, plus persisted enable/disable state instead of relying purely on entry-point discovery.

### Deliberately not prioritized this round
- **Native mobile/desktop, browser extension, Control-UI-scale web app**: same call as Round 2 — not realistically closable solo, and NeuralCleave's Tauri desktop build already covers the cross-platform-desktop need reasonably well.
- **Per-thread capability-scoped dashboards (§4.13) and a persistent task board (§4.12)**: real but meaningfully heavier lift than P0–P9, and more frontend-shaped than backend-shaped. Revisit after P0–P9 land.
- **Meeting-bot transcription (§4.14)**: newly plausible given existing browser automation + voice pipeline, but substantial new infrastructure (virtual audio, live-caption scraping) — not a priority gap, a future feature bet.
- **Chasing OpenClaw's full channel/provider counts**: confirmed this round that channels are not a gap at all (NeuralCleave leads in several niches), and the provider gap is now down to three specific, cheap wins (P3) rather than a long tail worth chasing.

---

## 6. One-paragraph summary for future sessions

As of 2026-08-17, the 2026-08-13 P0–P8 list is fully closed (PRs #126–#131) and OpenClaw has continued shipping heavily in the interim (PR numbers now past 122000), but almost everything new there is native-app, browser-extension, or Control-UI-specific and out of reach for a solo Python backend. A fresh backend/gateway-focused survey found a different flavor of gap than last round: not "wired to nothing" bugs, but missing operational maturity — the privacy audit log still has no persistence (the direct sequel to Round 2's "wired to nothing" bug, just the other half of the same feature), there's no backup/restore command at all, no cost tracking despite token counts already being recorded, and a few cheap provider/tool breadth wins (Groq/Together/Fireworks, Brave/Tavily search). The recommended order is P0 (persist privacy audit) → P1 (backup/restore) → P2 (cost tracking) → P3 (fast-inference providers) → P4 (better web search) → P5 (exec approval allowlist + channel-forwarded approval) → P6 (models CLI + host metrics) → P7 (normalized thinking control) → P8 (skill review step) → P9 (plugin install CLI), deliberately leaving native platforms, capability-scoped dashboards, and meeting-bot transcription out of scope for now.
