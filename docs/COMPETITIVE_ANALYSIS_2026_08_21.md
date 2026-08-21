# NeuralCleave vs OpenClaw — Gap Analysis & Build Plan (Round 4)
**2026-08-21 | Supersedes `COMPETITIVE_ANALYSIS_2026_08_17.md` for gap-tracking purposes**

> Round 3's P0–P9 list (persistent privacy audit log, backup/restore CLI, cost/usage tracking, Groq/Together/Fireworks providers, Brave/Tavily web search, exec-approval allowlist, `models` CLI + host metrics, normalized `/think` ladder, skill review lifecycle, plugin install/enable CLI, Mintlify docs pass) shipped via PRs #132–#135 (2026-08-17 through 2026-08-20). This round re-verified every one of those claims against current source in both repos rather than trusting the prior doc, and found three of them are **not fully wired** the way the round-3 doc claimed — the same "built in isolation, never reaches the live path" bug shape that has recurred every round so far (privacy audit transport in round 2, `WriteSkillTool`/`PluginRegistry` in round 3, now exec-approval channel notification and the reasoning-effort ladder in round 4).

**Method note:** every NeuralCleave claim below was verified against actual source in this repo via two independent research passes — one tracing round-3's shipped features end-to-end from CLI/tool entry point through to the live gateway path, one surveying OpenClaw's actual git history and docs (not just `CHANGELOG.md`, which was found this round to lag real merged work by several days) at `c:/Amit-Projects/AI-Projects/Openclaw`.

---

## 1. Headline verdict

The structural gap from prior rounds (OpenClaw as a much bigger, funded, multi-platform project with native apps, a browser extension, and a widget/marketplace ecosystem) hasn't changed and isn't closable solo — not repeated here. What *is* new: round 4 found real bugs in round 3's own delivery rather than a long list of brand-new OpenClaw capability. OpenClaw's `CHANGELOG.md` has barely moved since 08-17 (four new onboarding/import fix bullets), but its actual git history has kept shipping underneath the changelog — most notably a more mature capability-scoped widget/dashboard security spec (`docs/web/dashboard-architecture.md`) and a finer-grained secrets model (protected vs. agent-readable). Neither is a quick win; both confirm the direction round 3 already flagged as "heavier lift, revisit later" rather than adding urgency.

The actionable core of round 4 is: **finish what round 3 already claimed to finish.** Three specific gaps between claimed and actual behavior, all cheap to close because the surrounding infrastructure already exists.

---

## 2. NeuralCleave: current state snapshot (post PR #135)

- **Version**: 2.1.5 (`pyproject.toml:7`, `neuralcleave/__init__.py:7`) — unchanged, per [[feedback_versioning]]
- **Channel adapters**: 31 files under `neuralcleave/channels/` (excluding `__init__.py`/`base.py`)
- **LLM providers**: 19, confirmed against `neuralcleave/models/router.py` (anthropic, google, deepseek, ollama, openai, mistral, xai, cohere, moonshot, zhipu, qwen, ernie, doubao, openrouter, azure, bedrock, groq, together, fireworks)
- **Tests**: ~6,753 test functions across 330 files under `tests/`
- **Docs consolidation**: confirmed complete — `docs-site/` no longer exists (only a stale `.gitignore` line remains); `mintlify-docs/` is the sole active docs tree. (Round 3's doc implied this was still pending; it wasn't — correcting that here.)
- Persistent privacy audit log, backup/restore CLI, cost/usage tracking, Groq/Together/Fireworks, Brave/Tavily search, skill review lifecycle, and plugin install/enable CLI are all **confirmed genuinely wired end-to-end** — no issues found in these six.

---

## 3. OpenClaw: what's changed since 08-17

`CHANGELOG.md`'s "Unreleased" section only gained four bullets (all onboarding/import-migration UX, team-scale, not backend-relevant) — but `git log` between 08-17 and 08-21 shows real merged work the changelog hasn't caught up to yet:

- **Finer-grained secrets model** (`#126088`, 2026-08-18): splits secrets into "protected, write-only" vs. "agent-readable," plus policy-bound Gateway exec aliases exposed to its agent runtime.
- **Capability-scoped widget/dashboard security spec matured**: `docs/web/dashboard-architecture.md` (rewritten 2026-08-19) now fully documents a per-widget capability manifest (`data` bindings, `actions` allowlist, `prompt`, `net` origin allowlist), byte-and-revision-bound grants, and a `board_widgets` SQLite table. This is the same feature round 3 (§4.13) already flagged as real-but-heavy and deferred — now more concretely specified, not more urgent.
- **Workboard (task/kanban board) build-out continues, but confirmed still opt-in**: `docs/plugins/workboard.md` states plainly it is "bundled but disabled by default," despite new session-dashboard embedding and automation-linking work landing 08-16 through 08-18. Round 3 (§4.12) already correctly deprioritized this; still correct.
- **Subagent delegation/lineage polish**: default delegation preference changed from "suggest" to "prefer" per-agent, plus an audit trail binding subagent spawns to "live authority." Orchestration-shaped, not directly portable given NeuralCleave's orchestrator has a different node/routing model.
- No new tool-call-repair work, no new harness/sub-agent backend extension, no new channel of note since the last survey.

None of this changes round 3's verdict that channels, providers, and core backend feature breadth are not gaps. The one substantive new signal (the widget capability-manifest spec) reinforces rather than escalates a gap already on record.

---

## 4. Newly identified gaps

### 4.1 Exec-approval channel notification is dead code
`neuralcleave/tools/approval_notify.py:43`'s `notify_channel()` — the function meant to forward a pending shell-approval request into the Slack/Telegram/Discord thread that triggered it — is **never called** anywhere except its own definition (repo-wide grep returns exactly the one definition site). `tools/shell.py:196-204` queues the `ApprovalRequest` and awaits it directly; it never calls `notify_channel`. Only the *inbound* half (resolving an approval from a channel reply, `agent/runtime.py:42,823`) is live. Round 3's own doc explicitly claimed this shipped ("forward pending approvals into the originating channel") — it did not, for the outbound half. This is the same "unit-tested in isolation, never reaches the live call site" bug shape found in rounds 2 and 3.

### 4.2 `/ready` probe doesn't check what it claims to check
`gateway/main.py:228-237`'s `/ready` route only checks `get_init_phase() == "ready"`. Round 3's doc claimed it "verifies at least one configured provider + one connected channel are reachable" — it does not; it's a static phase-flag check, functionally not much richer than the flat `/health` it was meant to improve on.

### 4.3 `/think` reasoning-effort ladder doesn't cover Ollama or DeepSeek
`neuralcleave/models/thinking.py:9-20` only maps Anthropic (extended thinking) and xAI/OpenRouter (`reasoning_effort`). Its own docstring admits Ollama's `think` parameter and DeepSeek's reasoning knob were never wired. Round 3's doc claimed the ladder was normalized "across providers" generally — the two most commonly self-hosted/cost-sensitive providers in NeuralCleave's own lineup (Ollama, DeepSeek) are excluded.

### 4.4 Capability-scoped widget/dashboard model (re-confirmed, not new — still deferred)
OpenClaw's now-more-detailed spec (§3) doesn't change round 3's call: a scoped-down version (per-session pinned canvas blocks + a basic per-block network allow/deny) is worth doing eventually but needs a widget sandbox model NeuralCleave doesn't have. Listed here only to record that it was re-examined this round, not overlooked.

---

## 5. Recommended build order

### P0 — Wire `notify_channel` into the live shell-approval path
`tools/shell.py`'s gated-command path already has the originating session/channel context available (it's how the *inbound* approval-reply resolution works). Call `notify_channel()` when an `ApprovalRequest` is queued, reusing the same channel `send()` interface every adapter already implements. Closes a real trust/usability gap: a pending approval currently only surfaces if the requester happens to check a dashboard, not proactively in the channel they're already talking in — the actual pitch of this feature per round 3's own description.

### P1 — Make `/ready` actually verify readiness
Extend `gateway/main.py`'s `/ready` route to check at least one configured provider has valid credentials (reuse `models/health.py`'s `check_providers`) and at least one channel adapter is connected, falling back to the current phase-flag check only as a floor. Cheap given both underlying checks already exist and are exposed elsewhere (`models list/status`, channel `ping()`).

### P2 — Extend the `/think` ladder to Ollama and DeepSeek
Add the two missing provider mappings in `models/thinking.py` (Ollama's `think` boolean/string param, DeepSeek's reasoning-effort equivalent), following the same pattern already used for xAI/OpenRouter. Closes the gap between documented and actual behavior for NeuralCleave's own most privacy/cost-relevant providers.

### Deliberately not prioritized this round
- **Capability-scoped widget/dashboard security model**: real, now more concretely specified upstream, but still a genuinely heavier lift than P0–P2 and requires a sandbox model NeuralCleave doesn't have yet. Revisit after P0–P2 land, not before.
- **Finer-grained protected-vs-agent-readable secrets split**: NeuralCleave's `resolve_secret()` + 1Password/env model already distinguishes "resolved at config load" from "exposed to the agent" implicitly through what's ever passed into a tool call; a formal split is worth a future look but isn't a trust gap on the order of P0–P2.
- **Workboard-equivalent task board**: still opt-in even in OpenClaw itself; no new urgency.
- **Native mobile/desktop, browser extension, widget marketplace**: unchanged verdict from every prior round.

---

## 6. One-paragraph summary for future sessions

As of 2026-08-21, round 3 (P0–P9, `COMPETITIVE_ANALYSIS_2026_08_17.md`) is closed in the sense that all ten features exist and are mostly wired correctly — but re-verifying end-to-end (rather than trusting the round-3 doc's own claims) found three specific overstatements: exec-approval channel notification (`approval_notify.notify_channel`) is dead code never called from the live shell-approval path, `/ready` doesn't actually check provider/channel reachability despite the round-3 doc saying it does, and the `/think` reasoning ladder excludes Ollama and DeepSeek despite being described as normalized "across providers." OpenClaw's changelog has barely moved since 08-17, but its git history shows continued work on a capability-scoped widget/dashboard security model and a finer secrets split — both real, both confirmed as appropriately deferred rather than newly urgent. Round 4's build order is P0 (wire the approval channel notification) → P1 (make `/ready` actually verify readiness) → P2 (extend `/think` to Ollama/DeepSeek), all three narrow, cheap fixes to gaps between what was claimed and what actually runs, deliberately leaving the widget capability model, the secrets split, and all native-platform work out of scope for now.

---

## 7. Implementation note — P0 was deeper than surveyed (added during the build, same day)

§4.1/§5's P0 undersold the actual bug. Tracing the *full* call chain (not just `notify_channel`'s call sites) during implementation found that `ShellTool`/`BrowserAutomationTool`'s `require_approval` flag was **never set to `True` anywhere in the live construction path** — `ToolRegistry.default()` had no parameter to enable it at all, and no config field existed to drive one. This meant the entire exec-approval gate from round 3 (P5) — `ApprovalPolicy`, `APPROVAL_QUEUE`, the allowlist CLI/REST surface, and `notify_channel` — was unreachable in production regardless of the channel-notification bug, not just missing its outbound-notification half. The actual P0 fix shipped:

- A new `[security]` config section (`require_shell_approval`, `security_mode`, `ask_mode`) — the missing on-switch.
- `ToolRegistry.default(require_approval=...)` and `AgentRuntime.from_config()` wiring it through, plus setting `POLICY.security`/`.ask` from config at startup.
- Per-call `_session_id` forwarding (`ToolRegistry.call(session_id=...)` → tool `execute(_session_id=...)`) — `ShellTool`/`BrowserAutomationTool` are shared singletons across every session, so the static constructor-time `session_id` could never reflect which channel/user actually triggered a given request.
- `ApprovalQueue.on_request` hook + `AgentRuntime._handle_new_approval_request` — the actual `notify_channel` wiring §4.1 called for, now reachable.
- `GET`/`POST /api/v1/approvals/policy` extended to read/write `require_shell_approval` live (no restart), plus an `approval_notifications_total` metric.
- Config hot-reload's `_on_config_reload` was found to be a pure log statement claiming to apply "model settings + API keys" while touching nothing — fixed to genuinely apply `[security]` live (the claim about model/API-key hot-reload was removed rather than made real, since that needs `ModelRouter` surgery out of scope here).
- CLI docs/help corrected: `neuralcleave approvals pending/approve/deny` only ever operate on the invoking CLI process's own in-memory queue (`ApprovalQueue` has no persistence or IPC) — they cannot reach a separately running `neuralcleave gateway start` process. The channel-forwarded reply and the REST routes both work correctly since they execute inside the gateway's actual process. This is a real, pre-existing limitation surfaced while auditing the chain, not something this round fixed — worth a proper fix in a future round (make the CLI proxy through the REST API when a gateway is reachable) but out of scope here.

**Why this matters for future rounds:** this is the fourth consecutive round where a feature was found "unit-tested in isolation, never reaches the live path" (privacy audit transport in round 2; `WriteSkillTool`/`PluginRegistry` in round 3; now `require_approval`'s on-switch and config hot-reload's `[security]` handling in round 4). When closing a future gap that involves a boolean flag, a config section, or a callback gated behind "if configured" — grep for every call site that constructs the gated object and confirm at least one of them can actually pass `True`/a non-default value in the live gateway path, not just in tests.
