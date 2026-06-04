# CortexFlow — Master Knowledge Base (Agent Skills File)
> **Use this file for every CortexFlow task.** It contains complete project context, architecture, patterns, conventions, and development rules needed to develop this project correctly.

---

## 1. PROJECT IDENTITY

| Field | Value |
|---|---|
| **Name** | CortexFlow |
| **Vision** | "The Kubernetes for Autonomous AI Agents" |
| **Type** | Autonomous Cognitive Operating System (Cognitive OS for AI Agents) |
| **Mission** | Most secure, intelligent, and reliable autonomous cognitive OS for next-gen AI-driven automation |
| **Status** | Active development — Phase 1 (Foundation) in progress |
| **Pitch target** | OpenAI, Microsoft, enterprise customers |
| **GitHub** | `TheAmitChandra/CortexFlow` |
| **License** | MIT |

**CortexFlow is NOT:**
- A chatbot or prompt wrapper
- A personal assistant (that is OpenClaw's domain)
- A replacement for human judgment

**CortexFlow IS:**
- A production-grade cognitive infrastructure platform
- Enterprise-grade multi-tenant orchestration
- Zero-trust sandboxed execution runtime
- Deterministic DAG-based workflow engine

---

## 2. ABSOLUTE WORKFLOW LAWS — NEVER VIOLATE

> ⛔ These rules were violated on 2026-05-23. Never repeat.

1. **ONE file changed = ONE immediate commit + ONE immediate push. No exceptions.**
2. Never use `git add -A` — always stage the exact file changed
3. Never accumulate multiple changes before committing
4. Sequence is non-negotiable: `edit file → git add <that file> → git commit → git push → then next file`
5. Never delete feature branches — all branches kept permanently
6. Never commit secrets, API keys, or passwords
7. Never expose internal error details in API responses
8. Never use string interpolation in SQL — always parameterized queries
9. Never hardcode configuration — use `backend/app/config.py` (pydantic-settings)

### Branch Strategy
```bash
git checkout -b feature/<module-name>

# For EVERY single file:
git add <that-exact-file>
git commit -m "feat(<scope>): <description>"
git push origin feature/<module-name>

# After all files done and tests pass:
git checkout main
git merge feature/<module-name> --no-ff -m "feat(<scope>): merge <description>"
git push origin main
# DO NOT delete the branch — keep all branches permanently
```

### Commit Format
```
<type>(<scope>): <short description>

Types: feat | fix | refactor | test | docs | chore | security
Scopes: agent-runtime | memory | workflow | security | tools | frontend | db | api | observability | learning
```

---

## 3. FULL TECHNOLOGY STACK

### Backend
| Technology | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Core runtime |
| FastAPI | 0.115.5 | REST API + WebSocket server |
| Uvicorn | 0.32.1 | ASGI server |
| Pydantic v2 | ≥2.11.5 | Data validation + settings |
| pydantic-settings | 2.6.1 | Config via env vars |
| SQLAlchemy (async) | 2.0.36 | ORM for PostgreSQL |
| asyncpg | 0.30.0 | Async PostgreSQL driver |
| Alembic | 1.14.0 | Database migrations |
| Celery[redis] | 5.4.0 | Distributed task queue + DAG |
| Redis[hiredis] | 5.2.1 | Cache, broker, pub/sub, short-term memory |
| Qdrant-client | ≥1.16.0 | Vector DB client |
| Neo4j | 5.27.0 | Knowledge graph driver |
| google-generativeai | 0.8.3 | Gemini API (primary LLM) |
| openai | 1.57.2 | DeepSeek via OpenAI-compatible API |
| ollama | 0.4.4 | Local inference |
| sentence-transformers | 3.3.1 | Embeddings |
| torch | 2.6.0 | PyTorch for ML |
| transformers | 4.47.1 | HuggingFace transformers |
| scikit-learn | ≥1.4.0 | ML utilities |
| prometheus-client | 0.21.1 | Metrics |
| opentelemetry-* | 1.29.0 | Distributed tracing |
| playwright | 1.49.0 | Browser automation |
| docker | 7.1.0 | Docker SDK for sandbox |
| hvac | 2.3.0 | HashiCorp Vault client |
| slowapi | 0.1.9 | Rate limiting |
| structlog | 24.4.0 | Structured JSON logging |
| python-jose | 3.3.0 | JWT authentication |
| passlib[bcrypt] | 1.7.4 | Password hashing |
| tenacity | 9.0.0 | Retry logic |
| httpx | 0.27.2 | Async HTTP client |

### Frontend
| Technology | Version | Purpose |
|---|---|---|
| Next.js | 14+ (App Router) | Framework, SSR |
| TypeScript | Latest | Type safety |
| Tailwind CSS | Latest | Styling (dark theme only) |
| shadcn/ui | Latest | UI components |
| React Flow | Latest | Live agent graph visualization |
| Zustand | Latest | UI/client state management |
| React Query v5 | Latest | Server state management |
| Vitest | Latest | Frontend testing |
| pnpm | Latest | Package manager |

### Databases
| Database | Port | Purpose |
|---|---|---|
| PostgreSQL 16 | 5432 | Relational data, episodic memory, event store |
| Qdrant | 6333/6334 | Vector semantic memory |
| Neo4j | 7474 (HTTP), 7687 (Bolt) | Knowledge graph memory |
| Redis 7+ | 6379 | Short-term memory, cache, broker, pub/sub |

### Infrastructure
| Technology | Purpose |
|---|---|
| Docker + Docker Compose | Containerization, sandbox execution |
| Kubernetes | Production orchestration, autoscaling |
| Prometheus | Metrics collection + alerting |
| OpenTelemetry | Distributed tracing |
| NGINX | Reverse proxy, TLS termination |
| GitHub Actions | CI/CD |
| Grafana | Metrics visualization |

---

## 4. PROJECT FILE STRUCTURE (COMPLETE)

```
CortexFlow/
├── .github/
│   ├── skills/cortexflow/SKILL.md          ← Original master knowledge base
│   ├── workflows/                           ← CI/CD GitHub Actions
│   │   ├── ci.yml
│   │   ├── test.yml
│   │   └── deploy.yml
│   └── AGENTS.md                            ← AI agent coding rules
├── backend/
│   ├── app/
│   │   ├── main.py                          ← FastAPI entry point + lifespan
│   │   ├── config.py                        ← Settings via pydantic-settings
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── agents.py               ← Agent CRUD + control
│   │   │   │   ├── workflows.py            ← Workflow run/pause/resume/rollback
│   │   │   │   ├── memory.py               ← Memory search/store/delete
│   │   │   │   ├── tools.py                ← Tool list/execute/schema
│   │   │   │   ├── events.py               ← Event triggers
│   │   │   │   ├── auth.py                 ← Login/refresh/logout/me
│   │   │   │   ├── observability.py        ← Logs/metrics/traces
│   │   │   │   ├── approvals.py            ← Human approval queue
│   │   │   │   └── mcp.py                  ← MCP protocol endpoint
│   │   │   └── websocket.py                ← WebSocket event streams
│   │   ├── core/                           ← All 12 core modules
│   │   │   ├── agent_runtime/              ← Module 1: Agent lifecycle
│   │   │   │   ├── agent.py               ← AgentRuntime class, AgentState enum
│   │   │   │   ├── loop.py                ← Autonomous execution loop
│   │   │   │   ├── lifecycle.py           ← Create/start/pause/resume/terminate
│   │   │   │   └── heartbeat.py           ← Agent heartbeat system
│   │   │   ├── orchestration/             ← Module 2: Multi-agent coordination
│   │   │   │   ├── orchestrator.py        ← Multi-agent coordinator
│   │   │   │   ├── planner.py             ← PlannerAgent: task→DAG decomposition
│   │   │   │   ├── router.py              ← RouterAgent: assigns tasks to agents
│   │   │   │   ├── executor.py            ← ExecutorAgent: runs tools
│   │   │   │   ├── validator.py           ← ValidatorAgent: verifies results
│   │   │   │   ├── critic.py              ← CriticAgent: reviews output quality
│   │   │   │   ├── security_agent.py      ← SecurityAgent: monitors risks
│   │   │   │   └── observer_agent.py      ← ObserverAgent: tracks runtime state
│   │   │   ├── memory/                    ← Module 3: 4-tier memory
│   │   │   │   ├── short_term.py          ← Redis TTL memory (1h)
│   │   │   │   ├── long_term.py           ← Qdrant vector memory
│   │   │   │   ├── episodic.py            ← PostgreSQL workflow history
│   │   │   │   ├── knowledge_graph.py     ← Neo4j entity relationships
│   │   │   │   └── retrieval.py           ← Unified retrieval pipeline
│   │   │   ├── workflow_engine/           ← Module 4: DAG execution
│   │   │   │   ├── dag.py                 ← DAG builder + executor
│   │   │   │   ├── scheduler.py           ← Celery-based scheduler
│   │   │   │   ├── checkpoints.py         ← Checkpoint persistence
│   │   │   │   └── recovery.py            ← Crash recovery + rollback
│   │   │   ├── security/                  ← Module 5: Zero-trust
│   │   │   │   ├── zero_trust.py          ← Zero-trust pipeline
│   │   │   │   ├── sandbox.py             ← Docker sandbox isolation
│   │   │   │   ├── permission_engine.py   ← Permission scope verification
│   │   │   │   ├── prompt_injection.py    ← Injection detection
│   │   │   │   └── audit.py               ← Immutable audit logging
│   │   │   ├── tools/                     ← Module 6: Tool system
│   │   │   │   ├── registry.py            ← Tool registry + registration
│   │   │   │   ├── browser.py             ← Playwright browser automation
│   │   │   │   ├── filesystem.py          ← File read/write/search
│   │   │   │   ├── shell.py               ← Sandboxed shell commands
│   │   │   │   ├── api_caller.py          ← REST/GraphQL API caller
│   │   │   │   └── database_tool.py       ← DB query tool
│   │   │   ├── reflection/                ← Module 7: Quality scoring
│   │   │   │   ├── engine.py              ← Reflection orchestrator
│   │   │   │   ├── hallucination.py       ← Hallucination detection
│   │   │   │   └── scorer.py              ← Execution quality scorer (0-100)
│   │   │   ├── events/                    ← Module 8: Event bus
│   │   │   │   ├── bus.py                 ← Redis pub/sub event bus
│   │   │   │   ├── triggers.py            ← Cron, webhook, GitHub, email triggers
│   │   │   │   └── handlers.py            ← Event handler dispatch
│   │   │   ├── learning/                  ← Module 9: Adaptive learning
│   │   │   │   ├── feedback.py            ← Feedback collection
│   │   │   │   ├── optimizer.py           ← RL behavior optimizer
│   │   │   │   ├── predictor.py           ← Workflow outcome predictor
│   │   │   │   ├── recommender.py         ← Workflow recommendation
│   │   │   │   └── failure_detector.py    ← Failure pattern detection
│   │   │   ├── observability/             ← Module 10: Observability stack
│   │   │   │   ├── metrics.py             ← Prometheus metrics definitions
│   │   │   │   ├── metrics_collector.py   ← Metrics collection logic
│   │   │   │   ├── tracing.py             ← OpenTelemetry tracing setup
│   │   │   │   ├── span_recorder.py       ← Span recording
│   │   │   │   ├── logs.py                ← Structured JSON logging (structlog)
│   │   │   │   └── audit_trail.py         ← Audit trail management
│   │   │   ├── model_router/              ← Module 11: LLM routing
│   │   │   │   ├── router.py              ← Intelligent model router
│   │   │   │   ├── gemini.py              ← Gemini Pro/Flash client
│   │   │   │   ├── deepseek.py            ← DeepSeek Coder client
│   │   │   │   ├── ollama.py              ← Ollama local inference client
│   │   │   │   └── token_budget.py        ← Token budgeting + cost tracking
│   │   │   └── governance/                ← Module 12: RBAC + policies
│   │   │       ├── rbac.py                ← Role-based access control
│   │   │       ├── approvals.py           ← Human approval workflow
│   │   │       ├── policy.py              ← Runtime policy engine
│   │   │       └── governance_engine.py   ← Governance orchestrator
│   │   ├── db/
│   │   │   ├── postgres.py                ← SQLAlchemy async session factory
│   │   │   ├── qdrant.py                  ← Qdrant client init
│   │   │   ├── neo4j.py                   ← Neo4j driver init
│   │   │   ├── redis.py                   ← Redis client init
│   │   │   └── models/                    ← SQLAlchemy ORM models
│   │   │       ├── __init__.py            ← Exports all models (import order matters!)
│   │   │       ├── user.py                ← User model
│   │   │       ├── agent.py               ← Agent model
│   │   │       ├── task.py                ← Task model
│   │   │       ├── workflow.py            ← Workflow model
│   │   │       ├── memory.py              ← MemoryEntry model
│   │   │       ├── tool_call.py           ← ToolCall model
│   │   │       └── audit.py               ← AuditLog model
│   │   ├── schemas/                       ← Pydantic request/response schemas
│   │   │   └── auth.py                    ← Auth schemas (more to be added)
│   │   ├── sdk/                           ← Python SDK for external use
│   │   └── workers/                       ← Celery task workers
│   │       ├── celery_app.py              ← Celery app config + queue routing
│   │       ├── agent_worker.py            ← Agent task workers
│   │       └── workflow_worker.py         ← Workflow execution workers
│   ├── tests/
│   │   ├── unit/                          ← 40 unit test files (comprehensive)
│   │   ├── integration/                   ← Integration tests
│   │   └── benchmarks/                    ← Performance benchmark suite
│   ├── alembic/                           ← DB migration scripts
│   ├── conftest.py                        ← pytest fixtures
│   ├── pyproject.toml                     ← Python project config
│   ├── Dockerfile                         ← Backend container
│   └── requirements.txt                   ← Python dependencies
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── (dashboard)/              ← All dashboard pages (layout group)
│   │   │   │   ├── layout.tsx            ← Dashboard shell layout
│   │   │   │   ├── dashboard/            ← System health overview
│   │   │   │   ├── agents/               ← Agent management
│   │   │   │   ├── workflows/            ← Workflow builder + history
│   │   │   │   ├── memory/               ← Memory explorer
│   │   │   │   ├── security/             ← Approvals + policies
│   │   │   │   ├── observability/        ← Metrics + audit logs
│   │   │   │   └── settings/             ← Config + integrations
│   │   │   ├── login/                    ← Login page
│   │   │   ├── layout.tsx                ← Root layout
│   │   │   ├── page.tsx                  ← Root redirect to /dashboard
│   │   │   ├── providers.tsx             ← React providers wrapper
│   │   │   └── globals.css               ← Global styles
│   │   ├── components/
│   │   │   ├── AgentGraph.tsx            ← React Flow live agent visualization
│   │   │   ├── WorkflowBuilder.tsx       ← Drag-and-drop DAG builder
│   │   │   └── layout/                   ← Sidebar/navbar components
│   │   ├── lib/
│   │   │   └── api.ts                    ← Axios API client (NEXT_PUBLIC_API_URL)
│   │   ├── store/                        ← Zustand stores
│   │   └── test/                         ← Frontend tests
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── next.config.mjs
│   ├── tsconfig.json
│   ├── vitest.config.ts
│   └── Dockerfile
├── deploy/
│   ├── docker-compose.yml                ← Production stack
│   ├── docker-compose.dev.yml            ← Local dev stack
│   ├── k8s/                              ← Kubernetes manifests
│   │   ├── namespace.yaml
│   │   ├── backend.yaml
│   │   ├── frontend.yaml
│   │   ├── postgres.yaml
│   │   ├── qdrant.yaml
│   │   ├── neo4j.yaml
│   │   ├── redis.yaml
│   │   └── ingress.yaml
│   ├── nginx/                            ← NGINX reverse proxy config
│   ├── prometheus/                       ← Prometheus config + alert rules
│   ├── grafana/                          ← Grafana dashboards
│   └── otel/                             ← OpenTelemetry collector config
├── docs/
│   └── IDEA.md                           ← Original vision document
├── requirements.txt                      ← Root Python deps (mirrors backend)
├── requirements-dev.txt                  ← Dev-only deps
├── requirements-test.txt                 ← Test deps
├── requirements-rag.txt                  ← LlamaIndex (optional, install separately)
└── README.md                             ← Full project documentation (1024 lines)
```

---

## 5. BACKEND CODING CONVENTIONS

### Core Rules
- **All I/O must use `async/await`** — no blocking calls
- **All request/response schemas** must be Pydantic models in `backend/app/schemas/`
- **FastAPI.Depends()** for DB sessions and auth injection
- **SQLAlchemy async ORM** for PostgreSQL — never raw SQL strings
- **Alembic** for ALL database schema changes — never alter tables manually
- **Never expose internal errors** in API responses (catch and return generic message)
- **Structured JSON logging** via `structlog` with trace IDs, agent IDs, task IDs
- **No hardcoded values** — all config via `app/config.py` using pydantic-settings
- **One responsibility per file** — keep files focused and small
- **Type hints everywhere** — enforced by mypy
- **Black formatter + isort** for code style

### Database Session Pattern
```python
from app.db.postgres import get_db
from sqlalchemy.ext.asyncio import AsyncSession

@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ...
```

### Settings Access Pattern
```python
from app.config import get_settings
settings = get_settings()  # LRU-cached singleton
```

### Logging Pattern
```python
from app.core.observability.logs import get_logger
logger = get_logger(__name__)
logger.info("agent.task_completed", agent_id=agent_id, task_id=task_id)
```

### Metrics Pattern
```python
from app.core.observability.metrics import get_metrics
m = get_metrics()
m.agent_tasks_total.labels(agent_type="planner", status="completed").inc()
```

### Tracing Pattern
```python
from app.core.observability.tracing import traced_operation
async with traced_operation("agent.task", attributes={"agent_id": agent_id}):
    ...
```

---

## 6. FRONTEND CODING CONVENTIONS

### Core Rules
- **`"use client"` directive** required on all components that use hooks
- **Server state** → React Query (`useQuery`, `useMutation`, `useQueryClient`)
- **UI/client state** → Zustand stores in `frontend/src/store/`
- **API calls** → `frontend/src/lib/api.ts` (Axios, base URL from `NEXT_PUBLIC_API_URL`)
- **Dark theme only** — `slate-950` background, `slate-800` cards, `slate-700` borders
- **TypeScript strictly** — run `pnpm type-check` before committing

### API Client Pattern
```typescript
// frontend/src/lib/api.ts
import axios from 'axios';
const api = axios.create({ baseURL: process.env.NEXT_PUBLIC_API_URL });
```

### Zustand Store Pattern
```typescript
// frontend/src/store/agents.ts
import { create } from 'zustand';
interface AgentStore {
  agents: Agent[];
  setAgents: (agents: Agent[]) => void;
}
export const useAgentStore = create<AgentStore>((set) => ({
  agents: [],
  setAgents: (agents) => set({ agents }),
}));
```

---

## 7. ALL 12 CORE MODULES

### Module 1: Agent Runtime (`core/agent_runtime/`)
**AgentState enum:** `IDLE | PLANNING | EXECUTING | VALIDATING | REFLECTING | PAUSED | TERMINATED`

**AgentRuntime class** (`agent.py`):
- `agent_id: str`, `config: AgentConfig`
- `start()`, `stop()`, `pause()`, `resume()`, `submit_task(task)`
- State transitions via `_state_lock` (asyncio.Lock)
- Background `_run_loop()` drains `_task_queue`
- Cognitive pipeline hooks: `_plan()`, `_execute()`, `_validate()`, `_reflect()` (override in subclasses)
- Emits Prometheus metrics on every state change

**AgentConfig (Pydantic):**
```python
name: str
agent_type: str = "generic"
max_concurrent_tasks: int = 1
heartbeat_interval_seconds: float = 30.0
task_timeout_seconds: float = 300.0
max_retries: int = 3
metadata: dict[str, Any]
```

### Module 2: Multi-Agent Orchestration (`core/orchestration/`)
**8 Specialized Agents:**
| Agent | File | Responsibility |
|---|---|---|
| PlannerAgent | `planner.py` | Decomposes goals into SubTask DAGs |
| RouterAgent | `router.py` | Assigns SubTasks to worker agents |
| ExecutorAgent | `executor.py` | Executes tools via tool system |
| ValidatorAgent | `validator.py` | Verifies correctness + consensus |
| CriticAgent | `critic.py` | Reviews quality, flags issues |
| SecurityAgent | `security_agent.py` | Monitors risks, enforces policies |
| ObserverAgent | `observer_agent.py` | Tracks runtime, feeds metrics |
| MemoryAgent | (in memory module) | Manages all memory tier operations |

**PlannerAgent** decomposes text into `Plan` with `SubTask` list. `Plan.execution_order()` returns topologically sorted parallel batches (BFS). Raises `PlanDecompositionError` on circular deps or empty goals.

**Communication:** Redis pub/sub event bus + Celery task queues + structured message schemas.

### Module 3: Memory Architecture (`core/memory/`)
**4-Tier System:**
| Tier | Store | File | TTL/Retention |
|---|---|---|---|
| Short-term | Redis | `short_term.py` | 1 hour TTL |
| Semantic | Qdrant | `long_term.py` | Until pruned |
| Episodic | PostgreSQL | `episodic.py` | Configurable |
| Knowledge Graph | Neo4j | `knowledge_graph.py` | Permanent |

**Retrieval Pipeline** (`retrieval.py`):
```
Query → Embedding (sentence-transformers, dim=384) → Qdrant ANN (top-k=20)
→ Metadata filter (agent_id, memory_type, time range)
→ Cross-encoder reranking (top-20 → top-5)
→ Hybrid search (vector + BM25)
→ Context scoring (recency + access freq + relevance)
→ Deduplication → Final assembly
```

**Qdrant Collections:**
- `conversation_embeddings` — dim: 384, metric: cosine
- `workflow_embeddings` — dim: 384, metric: cosine
- `knowledge_embeddings` — dim: 384, metric: cosine
- `task_embeddings` — dim: 384, metric: cosine

**Memory Compression Triggers:**
- Token count > 75% of model window → summarization
- Memory entries > 500/agent → pruning
- Importance score: `(0.4 × recency) + (0.3 × access_count) + (0.3 × relevance)`

### Module 4: Workflow Engine (`core/workflow_engine/`)
**State Machine:**
```
Normal:  PENDING → RUNNING → VALIDATING → REFLECTING → COMPLETED
Failure: RUNNING → FAILED → RETRYING (×3) → ROLLED_BACK
Pause:   RUNNING → PAUSED → RUNNING
```

**Key capabilities:** DAG execution via Celery, checkpoint persistence in PostgreSQL, rollback on failure, parallel execution for independent tasks, workflow versioning (immutable once executed), diff inspection.

### Module 5: Security Architecture (`core/security/`)
**Zero-Trust Pipeline:**
```
Request → Schema Validate (Pydantic) → Permission Check
→ Risk Scoring (0–100) → Policy Evaluation
→ Dry-Run Simulation (if risk > 60) → Sandbox Allocation → Execute
→ Result Validation → Audit Log
```

**Execution Isolation Tiers:**
| Risk Score | Isolation | Technology |
|---|---|---|
| 0–25 | Shared process | Python subprocess with limits |
| 26–60 | Ephemeral container | Docker (auto-removed) |
| 61–85 | Isolated container | Docker + network isolation |
| 86–100 | Human approval required | Block until operator approves |

**Escalation Chain:**
```
Risk 61–85  → Operator notified (15 min SLA)
Risk 86–100 → Admin notified (5 min SLA)
Policy violation → Security Auditor (immediate)
```

**Threat Model:** prompt injection, memory poisoning, sandbox escape, credential leakage, privilege escalation, adversarial workflows, unauthorized API access, cross-tenant data access.

### Module 6: Tool Execution System (`core/tools/`)
**ToolDefinition (Pydantic):**
```python
name: str                          # e.g. "browser.navigate"
permissions: list[str]             # e.g. ["web_access"]
risk_level: Literal["low", "medium", "high", "critical"]
requires_approval: bool
sandbox_required: bool
timeout_seconds: int
allowed_domains: list[str] | None  # for browser tools
```

**Tool Categories:**
- `browser.*` — Playwright (navigate, click, scrape, screenshot) — min High isolation
- `file.*` — Read/write/search (path-scoped) — min Medium isolation
- `shell.*` — Allowlist-only commands — min Medium isolation
- `api.*` — REST/GraphQL calls — Low isolation
- `db.*` — SQL queries (read-only default) — Medium isolation
- `ml.*` — Model inference — Low isolation
- `comms.*` — Email, notifications — approval required

### Module 7: Reflection Engine (`core/reflection/`)
- Execution quality scoring (0–100) via `scorer.py`
- Hallucination detection via confidence thresholding + fact-checking (`hallucination.py`)
- Retry strategy: `retry | rethink | escalate`
- Feeds adaptive learning system
- Behavioral pattern analysis

### Module 8: Event System (`core/events/`)
**Trigger Sources:**
| Source | Technology | Example |
|---|---|---|
| Email | IMAP / Gmail API | New inbox message |
| GitHub | Webhooks | PR opened or merged |
| Database | PostgreSQL LISTEN/NOTIFY | Row inserted/updated |
| Webhook | FastAPI endpoint | External system event |
| Cron | Celery Beat | Scheduled recurring job |
| Monitoring | Prometheus Alertmanager | Infrastructure alert |

**Pipeline:** `Event → Redis Event Bus → Agent Trigger → Workflow Execution`

### Module 9: Adaptive Learning (`core/learning/`)
**Learning Pipeline:**
```
Action → Execution → Outcome → Feedback Score → Reward Calculation
→ Behavior Weight Update → Future Actions Influenced
```

**Components:**
- `feedback.py` — FeedbackCollector (explicit + implicit)
- `optimizer.py` — BehaviorOptimizer (RL strategy weights)
- `predictor.py` — WorkflowPredictor (predicts next actions)
- `recommender.py` — WorkflowRecommender
- `failure_detector.py` — FailurePatternDetector

### Module 10: Observability (`core/observability/`)
**Stack:**
- Prometheus metrics: token usage, API costs, execution times, memory pressure
- OpenTelemetry: distributed traces across agents and tools
- Structured logging: JSON with trace IDs, agent IDs, task IDs (structlog)
- Audit trail: immutable record of every tool execution + approval

**Key Prometheus Metrics** (from `metrics.py`):
- `agents_active` — gauge with `agent_type` label
- `agent_tasks_total` — counter with `agent_type`, `status` labels
- `workflow_executions_total`, `tool_calls_total`, `memory_retrieval_latency`

### Module 11: Model Router (`core/model_router/`)
**Routing Table:**
| Task Type | Primary | Fallback |
|---|---|---|
| Complex reasoning | Gemini Pro | DeepSeek |
| Code generation | DeepSeek Coder | Gemini |
| Summarization | Gemini Flash | Ollama |
| Embeddings | sentence-transformers (local) | — |
| Cheap inference | Ollama | — |

**Fallback Chain:** `Gemini → DeepSeek → Ollama → DEGRADED MODE`

**Token Budget:**
```python
max_tokens_per_task: int = 50_000
max_tokens_per_workflow: int = 500_000
max_cost_per_workflow_usd: float = 1.00
alert_threshold_pct: float = 0.80
```

**Retry Policy:**
| Provider | Max Retries | Backoff | Timeout |
|---|---|---|---|
| Gemini | 3 | Exponential (1s, 2s, 4s) | 30s |
| DeepSeek | 2 | Linear (2s, 4s) | 45s |
| Ollama | 1 | Fixed (3s) | 60s |

### Module 12: Governance & Policy (`core/governance/`)
**RBAC Roles:** `admin | developer | operator | viewer | auditor`

**Approval Workflow:**
```
Action Request → Risk Score → If score ≥ threshold → Create ApprovalRequest
→ Notify Operator → Wait for approval → Execute | Reject
```

**Dynamic Policy Updates:** Policies reloaded without restart via Redis pub/sub.

---

## 8. DATABASE SCHEMAS

### PostgreSQL ORM Models (SQLAlchemy)
- `users` — UUID pk, email, hashed_password, role, created_at
- `agents` — UUID pk, name, type, status, config JSONB, user_id FK, created_at
- `tasks` — UUID pk, title, description, status, agent_id FK, workflow_id, parent_task_id FK, result JSONB, risk_score, timestamps
- `workflows` — UUID pk, name, dag_definition JSONB, status, checkpoint JSONB, user_id FK, created_at
- `tool_calls` — UUID pk, tool_name, parameters JSONB, result JSONB, risk_score, approved_by FK, agent_id FK, task_id FK, created_at
- `memory_entries` — UUID pk, agent_id FK, memory_type, content JSONB, embedding_id, created_at
- `audit_logs` — UUID pk, actor_id, action, resource_type, resource_id, metadata JSONB, ip_address, created_at
- `reasoning_steps` — UUID pk, agent_id FK, task_id FK, step_type, content JSONB, confidence, created_at
- `feedback` — UUID pk, agent_id FK, task_id FK, score, feedback_type, metadata JSONB, created_at
- `approvals` — UUID pk, tool_call_id FK, requested_by FK (agent), reviewed_by FK (user), status, reason, timestamps
- `permissions` — UUID pk, agent_id FK, scope, granted_by FK, expires_at, created_at

### Neo4j Graph Nodes + Relationships
```cypher
(:User {id, email, role})
(:Agent {id, name, type, status})
(:Workflow {id, name, status})
(:Tool {id, name, risk_level})
(:Task {id, title, status})
(:Feedback {id, score, type})

(:User)-[:OWNS]->(:Agent)
(:Agent)-[:EXECUTES]->(:Workflow)
(:Agent)-[:USES]->(:Tool)
(:Workflow)-[:CONTAINS]->(:Task)
(:Task)-[:DEPENDS_ON]->(:Task)
(:Agent)-[:LEARNS_FROM]->(:Feedback)
(:Agent)-[:COMMUNICATES_WITH]->(:Agent)
(:Workflow)-[:TRIGGERED_BY]->(:Tool)
```

---

## 9. API ENDPOINTS

### Auth
```
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

### Agents
```
POST   /api/v1/agents/create
GET    /api/v1/agents/{agent_id}
GET    /api/v1/agents/
PATCH  /api/v1/agents/{agent_id}/status
DELETE /api/v1/agents/{agent_id}
POST   /api/v1/agents/{agent_id}/execute
```

### Workflows
```
POST   /api/v1/workflows/run
GET    /api/v1/workflows/{workflow_id}
POST   /api/v1/workflows/{workflow_id}/pause
POST   /api/v1/workflows/{workflow_id}/resume
POST   /api/v1/workflows/{workflow_id}/rollback
GET    /api/v1/workflows/{id}/versions
POST   /api/v1/workflows/{id}/rollback?version=3
GET    /api/v1/workflows/{id}/diff?v1=2&v2=3
POST   /api/v1/workflows/simulate
```

### Memory
```
GET    /api/v1/memory/search?q=&agent_id=&type=
POST   /api/v1/memory/store
DELETE /api/v1/memory/{memory_id}
```

### Tools
```
GET    /api/v1/tools/
POST   /api/v1/tools/execute
GET    /api/v1/tools/{tool_name}/schema
```

### Events
```
POST   /api/v1/events/trigger
GET    /api/v1/events/
```

### Observability
```
GET    /api/v1/observability/logs
GET    /api/v1/observability/metrics
GET    /api/v1/observability/traces/{trace_id}
GET    /api/v1/observability/agents/{agent_id}/graph
```

### Approvals
```
GET  /api/v1/approvals/pending
POST /api/v1/approvals/{approval_id}/approve
POST /api/v1/approvals/{approval_id}/reject
POST /api/v1/approvals/{approval_id}/modify
```

### MCP (Model Context Protocol)
```
GET/POST /mcp/  ← MCP server endpoint (no /api/v1/ prefix)
```

### WebSocket Streams
```
ws://host/ws/agents      ← Live agent state
ws://host/ws/workflows   ← Workflow execution
ws://host/ws/events      ← System events
ws://host/ws/approvals   ← Live approval stream
```

### Health
```
GET /health   ← Liveness probe
GET /ready    ← Readiness probe (checks PostgreSQL + Redis)
```

---

## 10. CELERY QUEUE ARCHITECTURE

**Dedicated queues — workers scale independently:**
| Queue | Purpose | Priority |
|---|---|---|
| `planning_queue` | PlannerAgent task decomposition | High |
| `execution_queue` | Tool execution, sandbox ops | High |
| `validation_queue` | ValidatorAgent + CriticAgent | Medium |
| `reflection_queue` | Reflection engine, scoring | Medium |
| `observability_queue` | Metrics, tracing, audit writes | Low |
| `high_priority_queue` | Time-critical agent tasks | Critical |
| `low_priority_queue` | Background learning, pruning | Low |
| `approval_queue` | Human approval requests | High |

**Worker autoscaling:**
| Queue | Min Workers | Max Workers | Scale Trigger |
|---|---|---|---|
| planning_queue | 1 | 4 | queue depth > 10 |
| execution_queue | 2 | 16 | queue depth > 5 |
| validation_queue | 1 | 8 | queue depth > 10 |
| reflection_queue | 1 | 4 | queue depth > 20 |

**Start command:**
```bash
celery -A app.workers.celery_app worker --loglevel=info \
  -Q planning_queue,execution_queue,validation_queue,reflection_queue,high_priority_queue
```

---

## 11. ENVIRONMENT VARIABLES

### Backend (.env in backend/)
```bash
# Required
SECRET_KEY=<jwt-secret-minimum-32-chars>
GEMINI_API_KEY=<your-key>

# Databases (pre-filled for local Docker)
DATABASE_URL=postgresql+asyncpg://cortex:cortex@localhost:5432/cortexflow
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=cortexflow

# App
APP_ENV=development  # development|staging|production|test
DEBUG=False
LOG_LEVEL=INFO
API_V1_PREFIX=/api/v1
ALLOWED_ORIGINS=http://localhost:3000

# Optional AI providers
DEEPSEEK_API_KEY=<your-key>
OLLAMA_BASE_URL=http://localhost:11434

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
PROMETHEUS_PORT=9090

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60

# JWT
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# GitHub
GITHUB_WEBHOOK_SECRET=<hmac-secret>
```

### Frontend (.env.local in frontend/)
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

## 12. DEVELOPMENT WORKFLOW & QUICK-START

### Start infrastructure (local)
```bash
docker-compose -f deploy/docker-compose.dev.yml up -d
# Starts: PostgreSQL, Qdrant, Neo4j, Redis
```

### Backend dev server
```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Celery worker
```bash
cd backend
celery -A app.workers.celery_app worker --loglevel=info \
  -Q planning_queue,execution_queue,validation_queue,reflection_queue,high_priority_queue
```

### Frontend dev server
```bash
cd frontend
pnpm install
pnpm dev  # → http://localhost:3000
```

### API docs (debug mode only)
- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Run tests
```bash
cd backend
pytest tests/ -v --cov=app --cov-fail-under=80
# Coverage requirement: minimum 80% (enforced by CI)
```

### Security scan
```bash
bandit -r app/ -f screen
```

### Frontend type check
```bash
cd frontend && pnpm type-check
```

---

## 13. TESTING REQUIREMENTS

- **Minimum coverage: 80%** enforced by CI (pytest-cov --cov-fail-under=80)
- **40 unit test files** in `backend/tests/unit/` covering all modules
- **Integration tests** in `backend/tests/integration/` (requires running services)
- **Benchmarks** in `backend/tests/benchmarks/` — run on every main merge
- **Frontend tests** via Vitest
- **Test naming:** `test_<module>_<function>_<scenario>`
- **Security scan:** `bandit -r app/` must be clean before merge

---

## 14. SECURITY NON-NEGOTIABLES

1. All user inputs validated with Pydantic schemas before processing
2. All tool executions pass through risk analysis pipeline
3. SQL queries use parameterized queries only — never string interpolation
4. Secrets stored in environment variables or HashiCorp Vault — never in code
5. JWT: 15 min access tokens, 7 day refresh tokens
6. Shell and browser tools always sandboxed in Docker containers
7. Rate limiting on all API endpoints (slowapi)
8. CORS configured to allowlist only known frontend origins
9. Every tool execution, approval, and permission change is audit logged
10. All LLM inputs scanned for prompt injection before sending
11. HTTPS enforced in production (NGINX TLS termination)
12. No agent can escalate its own permissions

---

## 15. 11-STAGE COGNITIVE PIPELINE

All agent tasks flow through this pipeline in order:
```
1.  INPUT RECEPTION       — Validate, sanitize, classify intent
2.  INTENT UNDERSTANDING  — LLM-based intent extraction, structured output
3.  TASK DECOMPOSITION    — Break into atomic subtasks, build DAG
4.  MEMORY RETRIEVAL      — Semantic + Episodic + Graph lookup
5.  PLANNING              — Generate execution plan + tool selections
6.  RISK ANALYSIS         — Score each action, flag high-risk ops
7.  TOOL SELECTION        — Match tools to task + permissions
8.  EXECUTION             — Run in sandbox, collect results
9.  VALIDATION            — Verify results against expectations
10. REFLECTION            — Score quality, detect hallucinations
11. MEMORY CONSOLIDATION  — Store outcomes, update embeddings, update graph
```

---

## 16. FRONTEND DASHBOARD PAGES

**This is a command center, NOT a chat UI. Dark theme only (slate-950 bg).**

| Page | URL | Purpose |
|---|---|---|
| Dashboard | `/dashboard` | System health, active agents, recent events |
| Agents | `/agents` | Create, monitor, control, inspect agents |
| Workflows | `/workflows` | Drag-and-drop DAG builder (React Flow), execution history |
| Memory Explorer | `/memory` | Semantic search, knowledge graph browser |
| Security Center | `/security` | Approval queue, permission manager, policy editor |
| Observability | `/observability` | Live agent graph, metrics, audit logs, traces |
| Settings | `/settings` | API keys, model routing config, integrations |

---

## 17. DEVELOPMENT PHASES

| Phase | Status | Key Features |
|---|---|---|
| Phase 1 — Foundation | 🔲 In Progress | FastAPI scaffold, PostgreSQL, JWT auth, Gemini integration, frontend shell |
| Phase 2 — Memory & Tools | 🔲 Planned | Qdrant, Neo4j, memory retrieval, tool registry, browser, workflow DAG |
| Phase 3 — Security & Reliability | 🔲 Planned | Zero-trust, sandbox, injection defense, human approval, reflection, observability |
| Phase 4 — Multi-Agent Intelligence | 🔲 Planned | All 8 agent types, communication bus, distributed orchestration |
| Phase 5 — Adaptive Learning | 🔲 Planned | Feedback loop, RL optimizer, failure detection, behavioral prediction |
| Phase 6 — Enterprise Infrastructure | 🔲 Planned | Kubernetes, autoscaling, enterprise observability, multi-tenant |

---

## 18. BENCHMARK TARGETS (SLOs)

| Metric | Target |
|---|---|
| API Availability | 99.9% |
| Task Completion Rate | > 95% |
| Workflow Completion Rate | > 98% |
| P50 API Response Time | < 200ms (excl. LLM inference) |
| P99 Workflow Latency | < 30s |
| Hallucination Rate | < 2% |
| Recovery Time Objective | < 5 minutes |
| Recovery Point Objective | < 15 minutes |
| Memory Hit Rate | > 85% |
| Tool Success Rate | > 99% |

---

## 19. MCP COMPATIBILITY

CortexFlow is both an **MCP server** and an **MCP client**:
- Exposes `/mcp/` endpoint for external AI clients (Claude, Cursor, etc.)
- Consumes external MCP servers as tool providers
- MCP tools tagged `source: "mcp"` in Tool Registry

---

## 20. KEY ARCHITECTURAL DECISIONS & GOTCHAS

1. **`requirements.txt` has duplicate `mypy==1.13.0`** — this is a known issue, harmless but should be fixed
2. **Schemas directory is sparse** — only `auth.py` exists; all other module schemas need to be created
3. **Frontend `src/app/(dashboard)/` uses route groups** — the `(dashboard)` is a Next.js route group, not a URL segment
4. **WebSocket endpoint** is in `api/websocket.py` registered without the `/api/v1` prefix
5. **MCP endpoint** also registered without `/api/v1` prefix (at `/mcp/`)
6. **`app/db/models/__init__.py`** exports all models — import order matters for SQLAlchemy relationship resolution
7. **RAG packages (LlamaIndex)** are in a separate `requirements-rag.txt` — install only if needed
8. **`conftest.py`** at backend root provides shared pytest fixtures
9. **Frontend uses pnpm** (not npm) — always use `pnpm` commands
10. **Celery queues** must all be specified when starting workers — omitting a queue means tasks for it won't run
11. **Neo4j** uses separate databases per tenant in production (Neo4j 4+ multi-database feature)
12. **Agent Trust Score** starts at 0.5, decreases with hallucinations/policy violations; < 0.3 = suspended
13. **Workflow DAG definitions are immutable once executed** — changes create new versions
14. **Feature flags** are cached in Redis with 60s TTL for hot reload without restart

---

## 21. COMPETITIVE POSITIONING

CortexFlow vs competitors (all check ✅ for CortexFlow):
- Enterprise Multi-tenancy ✅
- Zero-Trust Sandboxing ✅
- Deterministic DAG Workflows ✅
- 4-Tier Memory Architecture ✅
- RBAC + Governance ✅
- Hallucination Mitigation ✅
- Full Observability Stack ✅
- Adaptive Learning ✅
- Multi-Model Cost Routing ✅
- Human-in-the-Loop UX ✅
- Air-Gapped Local Mode ✅
- Kubernetes-Native Scale ✅
- Knowledge Graph Memory ✅
- Risk-Scored Execution ✅
- MCP Compatibility ✅

Competitors (CrewAI, AutoGen, LangChain) lack most of these ❌.

---

## 22. AGENT IDENTITY MODEL

```python
class AgentIdentity(BaseModel):
    id: UUID                         # immutable
    name: str
    type: AgentType                  # planner|router|executor|validator|critic|memory|security|observer
    capability_profile: list[str]    # declared capabilities
    permission_scope: list[str]      # granted permissions
    trust_score: float               # 0.0–1.0 (starts at 0.5)
    behavioral_metrics: dict
    execution_history_count: int
    created_at: datetime
    last_active_at: datetime
```

**Trust score rules:**
- Starts at 0.5 for all new agents
- Increases: successful validated task completions
- Decreases: hallucinations, policy violations, failed validations
- < 0.3 → agent suspended, admin notified
- Affects routing priority (higher trust → preferred for critical tasks)
