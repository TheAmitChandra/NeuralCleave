# Performance & Footprint: CortexFlow-AI vs OpenClaw

**Date:** 2026-06-28
**Status:** Structural comparison + CortexFlow-AI internal benchmarks. **Not** a live
request-latency head-to-head — see [Why no live benchmark](#why-no-live-benchmark)
below for exactly why, and what it would take to do one properly.

---

## Why no live benchmark

The plan was to clone OpenClaw, run its gateway locally, and measure real
request-routing latency side by side with CortexFlow-AI's own gateway. That
was abandoned partway through for a concrete, reproducible reason:

- OpenClaw's `package.json` requires Node `>=22.19.0`; this environment has
  `v22.17.1`.
- `pnpm install` (with `--ignore-scripts`, the lightest reasonable option)
  pulled **0.97 GB** of `node_modules` in under three minutes and was still
  going — its `pnpm-workspace.yaml` includes 21 internal packages and 145
  `extensions/`, several of which carry multi-platform native binaries:
  `node-llama-cpp` (with separate CUDA/CPU builds), `@lancedb/lancedb`
  (native vector DB bindings), and full agent SDKs for Claude, Codex, and
  GitHub Copilot.
- Partway through, several large package downloads started failing with
  registry timeouts and retrying (`GET .../node-llama-cpp/... error (23)`),
  a sign of an unstable network path for a multi-GB install, not a one-off
  blip.
- This machine had **37 GB free** at the time. A full install — every
  platform-specific native binary the workspace's `extensions/` pull in —
  was a real risk of consuming a large fraction of that for a single
  benchmark run, with no guarantee the network instability wouldn't strand
  the install halfway through anyway.

Given that, continuing was a judgment call between "spend potentially
10+ GB and significant time chasing a flaky install" and "do the comparison
that's actually available without that cost." This document is the latter.
**Anyone who wants the live comparison can do it on a machine with reliable
multi-GB bandwidth and 15+ GB free** — the methodology section below
documents exactly how to extend this with real numbers once that's
available.

---

## Structural comparison

Measured directly from a fresh `git clone --depth 1` of each project (commit
clones taken 2026-06-28; OpenClaw's `node_modules` excluded since the full
install wasn't completed — see above).

| | OpenClaw | CortexFlow-AI |
|---|---|---|
| Language | TypeScript (Node.js) | Python |
| Repo size (source only, no deps) | 202.5 MB | 0.94 MB (gateway only) |
| Source files (gateway-relevant) | 16,947 (.ts/.tsx/.js/.jsx, **all platforms**: includes Android/iOS/macOS native apps) | 60 (.py) |
| Lines of code | ~4.40M (all platforms combined) | 8,536 (gateway only) |
| Workspace packages | 21 (`packages/*`) | — (single package) |
| Channel/integration extensions | 145 total (`extensions/*`); ~14–15 are messaging-channel adapters (Discord, Telegram, Slack, WhatsApp, Signal, Matrix, IRC, SMS, iMessage, Line, Mattermost, MS Teams, Nextcloud Talk, webhooks) — the rest are LLM providers, tools, and infra (speech, diagnostics, etc.) | 14 channel adapters, all built into the core package |
| Root direct dependencies | 54 (+ 31 devDeps) | 14 |
| Test files | 6,544 (`*.test.ts` / `*.spec.ts`) | 50 |
| Tests (CortexFlow-AI: actually run) | not run (no functional install) | 1,173, all passing, 99.7% coverage |
| Native apps shipped today | Android, iOS, macOS (3 platforms) | None yet — Tauri desktop app is still on the roadmap |
| Project maturity (per `docs/IMPLEMENTATION_PLAN_v2.md`) | 377k GitHub stars, 57k+ commits | Single-developer project, started 2026-06 |

**Read honestly:** OpenClaw is a mature, multi-year, multi-platform ecosystem
with native mobile/desktop apps and a much larger surface area —
the line-count and file-count gap mostly reflects that scope difference
(three native app platforms plus 145 extensions), not raw efficiency.
CortexFlow-AI is a deliberately minimal, single-package Python gateway that
hasn't built its desktop client yet. The dependency-count and channel-count
rows are the fairer apples-to-apples comparisons here.

---

## CortexFlow-AI internal benchmark

Pure-Python hot paths, no external services (Redis/Qdrant/network calls).
Run via `python scripts/benchmark.py --json` (default 2000 iterations, 500
for the async SQLite benchmark) on the same machine used for the structural
comparison above:

| Benchmark | Iterations | Mean | p50 | p95 | p99 | Rate |
|---|---|---|---|---|---|---|
| `complexity_detection` | 2,000 | 0.0029 ms | 0.0014 ms | 0.0135 ms | 0.0237 ms | 345,752/s |
| `message_splitting` | 2,000 | 0.0009 ms | 0.0009 ms | 0.0010 ms | 0.0018 ms | 1,093,493/s |
| `config_parsing` | 2,000 | 0.0083 ms | 0.0078 ms | 0.0097 ms | 0.0127 ms | 121,062/s |
| `sqlite_memory` (store + search) | 500 | 13.94 ms | 13.61 ms | 16.41 ms | 19.30 ms | 72/s |

These are the framework's own routing/parsing/storage overhead —
the part that's actually comparable across implementations, since it
excludes LLM provider latency (which is identical regardless of which
gateway calls the same model API). No equivalent OpenClaw numbers exist
yet for the reason above.

---

## What a real head-to-head would need

To extend this with genuine live numbers:

1. A machine with 15+ GB free and stable broadband (the OpenClaw install
   alone, fully resolved, is likely 5–10 GB based on the partial download).
2. Node `>=22.19.0` (this environment had 22.17.1).
3. Run OpenClaw's `pnpm install && pnpm openclaw setup && pnpm gateway:watch`
   per its README, then hit its `openclaw gateway status` / message-send CLI
   commands with timing wrapped around them — directly comparable to
   `scripts/benchmark.py`'s own timing methodology.
4. Compare config-parse time, message-routing overhead, and idle memory
   footprint (not LLM response time, which is provider-bound and identical
   either way).

Until then, this document is the honest version: a real structural
comparison, real CortexFlow-AI numbers, and a clear paper trail for why the
live comparison isn't here yet.
