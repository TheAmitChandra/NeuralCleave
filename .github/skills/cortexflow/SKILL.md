---
name: cortexflow
description: "Use when: building CortexFlow, implementing any module, creating branches, writing code, running tests, committing changes, designing architecture, implementing security, setting up databases, building the frontend, configuring infrastructure, or any task related to the CortexFlow autonomous cognitive operating system project."
---

# CortexFlow — Autonomous Cognitive Operating System
## Master Skill File — Complete Project Knowledge Base

---

## CRITICAL WORKFLOW RULES (ALWAYS FOLLOW)

### Git Branching Strategy
- **Every mechanism/module gets its own branch** — never develop on `main`
- Branch naming: `feature/<module-name>` (e.g. `feature/agent-runtime`, `feature/memory-system`)
- Create branch → implement → write tests → pass tests → merge to `main`
- **Commit every change immediately** — atomic commits, one logical change per commit
- **Push every commit immediately** after committing — never batch pushes

### Commit Format
```
<type>(<scope>): <short description>

Types: feat | fix | refactor | test | docs | chore | security
Scope: agent-runtime | memory | workflow | security | tools | frontend | db | api | observability | learning
```

### Branch Lifecycle
```
git checkout -b feature/<module>
# ... implement ...
git add -A
git commit -m "feat(<scope>): <description>"
git push origin feature/<module>
# ... test passes ...
git checkout main
git merge feature/<module> --no-ff
git push origin main
git branch -d feature/<module>
```

---

## PROJECT IDENTITY

**Name:** CortexFlow  
**Type:** Autonomous Cognitive Operating System  
**Vision:** "The Kubernetes for Autonomous AI Agents"  
**Mission:** Build the most secure, intelligent, and reliable autonomous cognitive OS for next-generation AI-driven automation  
**Primary Language:** Python (backend), TypeScript (frontend)  
**Primary LLM:** Gemini API (model-agnostic — also supports DeepSeek, Ollama, local models)

---

## WHY CORTEXFLOW EXISTS — OPENCLAW ANALYSIS

OpenClaw (https://github.com/openclaw/openclaw) is a personal AI assistant built in TypeScript, designed for messaging channels (WhatsApp, Telegram, Discord, etc.). It uses a Gateway daemon, WebSocket protocol, and plugin-based skill system.

### OpenClaw's Core Architecture (What We Studied)
- Single Gateway daemon controls all messaging surfaces
- WebSocket API for control-plane clients
- Plugin API with code plugins and bundle-style plugins
- Memory is a single plugin slot (only one active at a time)
- Sandboxing is optional Docker-based (only for non-main sessions)
- Personal-use focus, NOT enterprise-grade
- TypeScript monorepo with pnpm
- Skills published via ClawHub registry
- DM pairing as primary security model
- No agent hierarchy (explicitly refuses manager-of-managers)
- No heavy orchestration layers (explicitly excluded from vision)

### OpenClaw Limitations CortexFlow Solves

| Limitation | CortexFlow Solution |
|---|---|
| Personal-use only, no enterprise | Enterprise-grade multi-tenant platform |
| Single memory plugin slot | Hierarchical 4-tier memory architecture (Redis/PostgreSQL/Qdrant/Neo4j) |
| Optional sandbox only for non-main sessions | Zero-trust sandboxing for ALL executions |
| No deterministic orchestration | DAG-based deterministic workflow engine |
| No multi-agent planner/validator/critic | Full multi-agent coordination system |
| No hallucination mitigation | Multi-layer hallucination detection + validation |
| No cost optimization | Multi-model routing + token budgeting |
| No observability stack | Prometheus + OpenTelemetry + full audit logs |
| No RBAC / governance | Role-based access control + approval chains |
| No adaptive learning | Reinforcement-based behavioral optimization |
| No risk-scored execution | Risk analysis before every tool call |
| No knowledge graph | Neo4j graph memory |
| No vector search built-in | Qdrant semantic memory |
| TypeScript only | Python ecosystem (FastAPI, LlamaIndex, HuggingFace) |
| No DAG workflows | Celery-based DAG task execution |
| Prompt injection basic defense | Multi-layer prompt injection defense system |

---

## TECHNOLOGY STACK

### Backend
| Purpose | Technology | Version |
|---|---|---|
| Main Backend | FastAPI | Latest |
| Runtime | Python AsyncIO | 3.12+ |
| Worker Queue | Celery | Latest |
| Message Broker | Redis | 7+ |
| Authentication | JWT/OAuth2 | - |
| Realtime Events | WebSockets | - |
| API Documentation | OpenAPI/Swagger | - |

### Frontend
| Purpose | Technology |
|---|---|
| Framework | Next.js 14+ (App Router) |
| Styling | Tailwind CSS |
| State Management | Zustand |
| Graph Visualization | React Flow |
| UI Components | shadcn/ui |
| Realtime | SSE + WebSockets |

### AI & ML Stack
| Purpose | Technology |
|---|---|
| Primary LLM | Gemini API (google-generativeai) |
| Secondary LLMs | DeepSeek API, Ollama |
| Embeddings | sentence-transformers |
| Transformers | HuggingFace transformers |
| ML | scikit-learn |
| RAG | LlamaIndex |
| Adaptive Learning | Custom reinforcement logic |

### Databases
| Purpose | Technology | Port |
|---|---|---|
| Relational | PostgreSQL 16 | 5432 |
| Vector Search | Qdrant | 6333 |
| Knowledge Graph | Neo4j | 7474/7687 |
| Cache + Broker | Redis | 6379 |

### Infrastructure
| Purpose | Technology |
|---|---|
| Containerization | Docker + Docker Compose |
| Orchestration | Kubernetes (K8s manifests) |
| Monitoring | Prometheus |
| Observability | OpenTelemetry |
| Reverse Proxy | NGINX |
| CI/CD | GitHub Actions |

---

## PROJECT STRUCTURE

```
CortexFlow/
├── .github/
│   ├── skills/
│   │   └── cortexflow/
│   │       └── SKILL.md              ← THIS FILE
│   ├── workflows/
│   │   ├── ci.yml
│   │   ├── test.yml
│   │   └── deploy.yml
│   └── AGENTS.md
├── backend/
│   ├── app/
│   │   ├── main.py                   ← FastAPI app entry point
│   │   ├── config.py                 ← Settings (pydantic-settings)
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── agents.py
│   │   │   │   ├── workflows.py
│   │   │   │   ├── memory.py
│   │   │   │   ├── tools.py
│   │   │   │   ├── events.py
│   │   │   │   ├── auth.py
│   │   │   │   └── observability.py
│   │   │   └── websocket.py
│   │   ├── core/
│   │   │   ├── agent_runtime/        ← Module 1
│   │   │   │   ├── agent.py
│   │   │   │   ├── loop.py
│   │   │   │   ├── lifecycle.py
│   │   │   │   └── heartbeat.py
│   │   │   ├── orchestration/        ← Module 2
│   │   │   │   ├── planner.py
│   │   │   │   ├── router.py
│   │   │   │   ├── executor.py
│   │   │   │   ├── validator.py
│   │   │   │   └── critic.py
│   │   │   ├── memory/               ← Module 3
│   │   │   │   ├── short_term.py
│   │   │   │   ├── long_term.py
│   │   │   │   ├── episodic.py
│   │   │   │   ├── knowledge_graph.py
│   │   │   │   └── retrieval.py
│   │   │   ├── workflow_engine/      ← Module 4
│   │   │   │   ├── dag.py
│   │   │   │   ├── scheduler.py
│   │   │   │   ├── checkpoints.py
│   │   │   │   └── recovery.py
│   │   │   ├── security/             ← Module 5
│   │   │   │   ├── zero_trust.py
│   │   │   │   ├── sandbox.py
│   │   │   │   ├── permission_engine.py
│   │   │   │   ├── prompt_injection.py
│   │   │   │   └── audit.py
│   │   │   ├── tools/                ← Module 6
│   │   │   │   ├── registry.py
│   │   │   │   ├── browser.py
│   │   │   │   ├── filesystem.py
│   │   │   │   ├── shell.py
│   │   │   │   ├── api_caller.py
│   │   │   │   └── database_tool.py
│   │   │   ├── reflection/           ← Module 7
│   │   │   │   ├── engine.py
│   │   │   │   ├── hallucination.py
│   │   │   │   └── scorer.py
│   │   │   ├── events/               ← Module 8
│   │   │   │   ├── bus.py
│   │   │   │   ├── triggers.py
│   │   │   │   └── handlers.py
│   │   │   ├── learning/             ← Module 9
│   │   │   │   ├── feedback.py
│   │   │   │   ├── optimizer.py
│   │   │   │   └── predictor.py
│   │   │   ├── observability/        ← Module 10
│   │   │   │   ├── metrics.py
│   │   │   │   ├── tracing.py
│   │   │   │   └── logs.py
│   │   │   ├── model_router/         ← Module 11
│   │   │   │   ├── router.py
│   │   │   │   ├── gemini.py
│   │   │   │   ├── deepseek.py
│   │   │   │   └── ollama.py
│   │   │   └── governance/           ← Module 12
│   │   │       ├── rbac.py
│   │   │       ├── approvals.py
│   │   │       └── policy.py
│   │   ├── db/
│   │   │   ├── postgres.py
│   │   │   ├── qdrant.py
│   │   │   ├── neo4j.py
│   │   │   ├── redis.py
│   │   │   └── models/
│   │   │       ├── agent.py
│   │   │       ├── workflow.py
│   │   │       ├── task.py
│   │   │       ├── memory.py
│   │   │       ├── tool_call.py
│   │   │       ├── audit.py
│   │   │       └── user.py
│   │   ├── schemas/                  ← Pydantic schemas
│   │   └── workers/                  ← Celery workers
│   │       ├── celery_app.py
│   │       ├── agent_worker.py
│   │       └── workflow_worker.py
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   ├── alembic/                      ← DB migrations
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── dashboard/
│   │   ├── agents/
│   │   ├── workflows/
│   │   ├── memory/
│   │   ├── security/
│   │   └── observability/
│   ├── components/
│   ├── lib/
│   ├── package.json
│   └── Dockerfile
├── deploy/
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   └── k8s/
│       ├── namespace.yaml
│       ├── backend.yaml
│       ├── frontend.yaml
│       ├── postgres.yaml
│       ├── qdrant.yaml
│       ├── neo4j.yaml
│       ├── redis.yaml
│       └── ingress.yaml
├── docs/
│   └── IDEA.md
└── README.md
```

---

## DEVELOPMENT PHASES & BRANCH MAP

### Phase 1 — Foundation
**Branch:** `feature/phase1-foundation`
- Sub-branches: `feature/project-scaffold`, `feature/fastapi-setup`, `feature/postgres-integration`, `feature/auth-jwt`, `feature/gemini-integration`, `feature/frontend-dashboard-shell`

### Phase 2 — Memory & Tools
**Branches:**
- `feature/qdrant-vector-memory`
- `feature/short-term-memory`
- `feature/long-term-memory`
- `feature/episodic-memory`
- `feature/knowledge-graph-neo4j`
- `feature/memory-retrieval-pipeline`
- `feature/tool-registry`
- `feature/browser-automation`
- `feature/workflow-engine-dag`

### Phase 3 — Security & Reliability
**Branches:**
- `feature/zero-trust-security`
- `feature/sandbox-execution`
- `feature/prompt-injection-defense`
- `feature/permission-engine`
- `feature/human-approval-layer`
- `feature/hallucination-mitigation`
- `feature/reflection-engine`
- `feature/retry-rollback-checkpoints`
- `feature/observability-stack`
- `feature/audit-logging`

### Phase 4 — Multi-Agent Intelligence
**Branches:**
- `feature/planner-agent`
- `feature/router-agent`
- `feature/validator-agent`
- `feature/critic-agent`
- `feature/security-agent`
- `feature/observer-agent`
- `feature/multi-agent-orchestration`
- `feature/agent-communication-bus`

### Phase 5 — Adaptive Learning
**Branches:**
- `feature/feedback-loop`
- `feature/reinforcement-optimizer`
- `feature/failure-pattern-detection`
- `feature/behavioral-prediction`
- `feature/workflow-recommendation`

### Phase 6 — Enterprise Infrastructure
**Branches:**
- `feature/kubernetes-deployment`
- `feature/prometheus-monitoring`
- `feature/opentelemetry-tracing`
- `feature/autoscaling`
- `feature/rbac-governance`
- `feature/enterprise-observability`

---

## MODULE SPECIFICATIONS

### Module 1: Agent Runtime
**Branch:** `feature/agent-runtime`

Core responsibilities:
- Agent lifecycle management (create, start, pause, resume, terminate)
- Autonomous execution loop
- Persistent session management (survives crashes/restarts)
- Heartbeat system for goal evaluation
- Context awareness (user state, workflow state, environment)

Agent execution loop pattern:
```python
async def run(self):
    while not self.task_completed:
        context = await self.memory.retrieve()
        plan = await self.planner.generate(context)
        action = await self.executor.execute(plan)
        result = await self.validator.verify(action)
        await self.memory.store(result)
        await self.reflection.review(result)
```

Agent states: `IDLE | PLANNING | EXECUTING | VALIDATING | REFLECTING | PAUSED | TERMINATED`

### Module 2: Multi-Agent Orchestration
**Branch:** `feature/multi-agent-orchestration`

Agent types:
| Agent | Class | Responsibility |
|---|---|---|
| Planner | `PlannerAgent` | Decomposes tasks into subtask graphs |
| Router | `RouterAgent` | Assigns subtasks to worker agents |
| Executor | `ExecutorAgent` | Executes actions via tool system |
| Validator | `ValidatorAgent` | Verifies action correctness |
| Critic | `CriticAgent` | Reviews output quality |
| Memory | `MemoryAgent` | Maintains memory consolidation |
| Security | `SecurityAgent` | Monitors execution risks |
| Observer | `ObserverAgent` | Tracks runtime state |

Communication: Event bus (Redis pub/sub) + Celery task queues + structured message schemas

### Module 3: Memory Architecture
**Branch:** `feature/memory-system`

4-tier memory:
1. **Short-term** (Redis) — active context, current session, TTL-based
2. **Long-term Semantic** (Qdrant) — vector embeddings, semantic retrieval
3. **Episodic** (PostgreSQL) — workflows, execution history, outcomes
4. **Knowledge Graph** (Neo4j) — relationships between agents/tools/workflows/users

Retrieval pipeline:
```
Input → Embedding (sentence-transformers) → Qdrant semantic search → 
Context ranking → Relevance filtering → Prompt assembly
```

### Module 4: Workflow Engine
**Branch:** `feature/workflow-engine`

DAG-based execution using Celery chains/chords:
- Retries with exponential backoff
- Rollback on failure
- Checkpoint persistence in PostgreSQL
- Parallel execution for independent tasks
- Workflow state: `PENDING | RUNNING | PAUSED | COMPLETED | FAILED | ROLLED_BACK`

### Module 5: Security Architecture
**Branch:** `feature/security`

Zero-trust pipeline:
```
Request → Risk Analysis → Policy Validation → Permission Check → Sandbox → Execution
```

Security layers:
1. **Sandboxed Execution** — Docker container isolation for dangerous ops
2. **Permission Engine** — Granular scopes (filesystem/network/browser/API)
3. **Human Approval Layer** — Critical actions require explicit approval
4. **Secret Isolation** — Encrypted vault, scoped tokens, secure injection
5. **Prompt Injection Defense** — Multi-layer detection: pattern matching + LLM-based analysis
6. **Risk Scoring** — Each tool call gets a risk score (0-100)

Threat model defenses:
- Prompt injection attacks
- Memory poisoning
- Sandbox escape
- Credential leakage
- Privilege escalation
- Adversarial workflows

### Module 6: Tool Execution System
**Branch:** `feature/tool-system`

Tool schema:
```python
class ToolDefinition(BaseModel):
    name: str                        # e.g. "browser.navigate"
    permissions: list[str]           # e.g. ["web_access"]
    risk_level: Literal["low", "medium", "high", "critical"]
    requires_approval: bool
    sandbox_required: bool
    timeout_seconds: int
    allowed_domains: list[str] | None  # for browser tools
```

Tool categories:
- `browser.*` — Playwright-based (navigate, click, scrape, screenshot)
- `file.*` — Read, write, search (path-scoped)
- `shell.*` — Restricted commands (allowlist-only)
- `api.*` — REST/GraphQL calls
- `db.*` — SQL queries (read-only by default)
- `ml.*` — Model inference calls
- `comms.*` — Email, notifications (approval required)

### Module 7: Reflection Engine
**Branch:** `feature/reflection-engine`

Capabilities:
- Execution quality scoring (0-100)
- Hallucination detection (confidence thresholding + fact-checking)
- Retry recommendations (strategy: retry / rethink / escalate)
- Workflow optimization suggestions
- Behavioral pattern analysis

### Module 8: Event System
**Branch:** `feature/event-system`

Trigger sources:
| Source | Technology | Example |
|---|---|---|
| Email | IMAP/Gmail API | New inbox message |
| GitHub | Webhooks | New PR merged |
| Database | PostgreSQL LISTEN/NOTIFY | Row update |
| Webhook | FastAPI endpoint | External event |
| Cron | Celery beat | Scheduled jobs |
| Monitoring | Prometheus alerts | Infrastructure alert |

Pipeline: `Event → Redis Event Bus → Agent Trigger → Workflow Execution`

### Module 9: Adaptive Learning System
**Branch:** `feature/adaptive-learning`

Learning pipeline:
```
Action → Execution → Outcome → Feedback Score → Reward Calculation → 
Behavior Weight Update → Next Action Influenced
```

Components:
- `FeedbackCollector` — captures explicit + implicit feedback
- `RewardCalculator` — scores outcomes (task completion, efficiency, accuracy)
- `BehaviorOptimizer` — updates strategy weights
- `FailurePatternDetector` — identifies recurring failure modes
- `WorkflowPredictor` — predicts next actions and branches

### Module 10: Observability System
**Branch:** `feature/observability`

Stack:
- **Prometheus** — metrics (token usage, API costs, execution times, memory)
- **OpenTelemetry** — distributed tracing across agents and tools
- **Structured logging** — JSON logs with trace IDs, agent IDs, task IDs

Frontend panels:
- Live agent graph (React Flow visualization)
- Runtime metrics dashboard
- Audit log explorer
- Cost analytics

### Module 11: Model Router
**Branch:** `feature/model-router`

Routing table:
| Task Type | Primary | Fallback |
|---|---|---|
| Complex reasoning | Gemini Pro | DeepSeek |
| Code generation | DeepSeek Coder | Gemini |
| Summarization | Gemini Flash | Local Ollama |
| Embeddings | sentence-transformers | - |
| Cheap inference | Ollama (local) | - |

Cost optimization:
- Token budgeting per task
- Prompt caching (Gemini)
- Memory summarization before context assembly
- Embedding reuse (cache in Redis + Qdrant)

### Module 12: Governance & Policy Layer
**Branch:** `feature/governance`

RBAC roles: `admin | developer | operator | viewer | auditor`

Approval workflow:
```
Action Request → Risk Score Calculation → 
If risk >= threshold → Create ApprovalRequest → 
Notify Operator → Wait for approval → Execute | Reject
```

---

## DATABASE SCHEMAS

### PostgreSQL Tables
```sql
-- users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR UNIQUE NOT NULL,
    hashed_password VARCHAR NOT NULL,
    role VARCHAR NOT NULL DEFAULT 'developer',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- agents
CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR NOT NULL,
    type VARCHAR NOT NULL,  -- planner|router|executor|validator|critic|memory|security|observer
    status VARCHAR NOT NULL DEFAULT 'idle',
    config JSONB,
    user_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- tasks
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT,
    status VARCHAR NOT NULL DEFAULT 'pending',
    agent_id UUID REFERENCES agents(id),
    workflow_id UUID,
    parent_task_id UUID REFERENCES tasks(id),
    result JSONB,
    risk_score FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- workflows
CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR NOT NULL,
    dag_definition JSONB NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',
    checkpoint JSONB,
    user_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- tool_calls
CREATE TABLE tool_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_name VARCHAR NOT NULL,
    parameters JSONB,
    result JSONB,
    risk_score FLOAT,
    approved_by UUID REFERENCES users(id),
    agent_id UUID REFERENCES agents(id),
    task_id UUID REFERENCES tasks(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- memory_entries
CREATE TABLE memory_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id),
    memory_type VARCHAR NOT NULL,  -- short_term|episodic|semantic
    content JSONB NOT NULL,
    embedding_id VARCHAR,  -- Qdrant point ID
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- audit_logs
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID,
    action VARCHAR NOT NULL,
    resource_type VARCHAR NOT NULL,
    resource_id UUID,
    metadata JSONB,
    ip_address VARCHAR,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- reasoning_steps
CREATE TABLE reasoning_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id),
    task_id UUID REFERENCES tasks(id),
    step_type VARCHAR NOT NULL,  -- intent|decomposition|planning|execution|validation|reflection
    content JSONB NOT NULL,
    confidence FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- feedback
CREATE TABLE feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id),
    task_id UUID REFERENCES tasks(id),
    score FLOAT NOT NULL,
    feedback_type VARCHAR NOT NULL,  -- explicit|implicit|system
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- approvals
CREATE TABLE approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_call_id UUID REFERENCES tool_calls(id),
    requested_by UUID REFERENCES agents(id),
    reviewed_by UUID REFERENCES users(id),
    status VARCHAR NOT NULL DEFAULT 'pending',  -- pending|approved|rejected
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- permissions
CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id),
    scope VARCHAR NOT NULL,
    granted_by UUID REFERENCES users(id),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Qdrant Collections
```
conversation_embeddings   — dim: 384, metric: cosine
workflow_embeddings        — dim: 384, metric: cosine
knowledge_embeddings       — dim: 384, metric: cosine
task_embeddings            — dim: 384, metric: cosine
```

### Neo4j Graph Schema
```cypher
// Nodes
(:User {id, email, role})
(:Agent {id, name, type, status})
(:Workflow {id, name, status})
(:Tool {id, name, risk_level})
(:Task {id, title, status})
(:Feedback {id, score, type})

// Relationships
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

## API ENDPOINTS

### Agents API
```
POST   /api/v1/agents/create
GET    /api/v1/agents/{agent_id}
GET    /api/v1/agents/
PATCH  /api/v1/agents/{agent_id}/status
DELETE /api/v1/agents/{agent_id}
POST   /api/v1/agents/{agent_id}/execute
```

### Workflows API
```
POST   /api/v1/workflows/run
GET    /api/v1/workflows/{workflow_id}
POST   /api/v1/workflows/{workflow_id}/pause
POST   /api/v1/workflows/{workflow_id}/resume
POST   /api/v1/workflows/{workflow_id}/rollback
```

### Memory API
```
GET    /api/v1/memory/search?q=&agent_id=&type=
POST   /api/v1/memory/store
DELETE /api/v1/memory/{memory_id}
```

### Tools API
```
GET    /api/v1/tools/
POST   /api/v1/tools/execute
GET    /api/v1/tools/{tool_name}/schema
```

### Observability API
```
GET    /api/v1/observability/logs
GET    /api/v1/observability/metrics
GET    /api/v1/observability/traces/{trace_id}
GET    /api/v1/observability/agents/{agent_id}/graph
```

### Auth API
```
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
GET    /api/v1/auth/me
```

### WebSocket Events
```
ws://host/ws/agents          — Live agent state stream
ws://host/ws/workflows       — Workflow execution stream
ws://host/ws/events          — System event stream
```

---

## SECURITY REQUIREMENTS (NON-NEGOTIABLE)

1. **All user inputs** must be validated with Pydantic schemas before processing
2. **All tool executions** must pass through risk analysis before executing
3. **SQL queries** must use parameterized queries only — never string interpolation
4. **Secrets** stored in environment variables or HashiCorp Vault — never in code
5. **JWT tokens** must have short expiry (15 min access, 7 day refresh)
6. **Sandbox** all shell/browser tools in Docker containers
7. **Rate limiting** on all API endpoints (slowapi or fastapi-limiter)
8. **CORS** configured to allowlist only known frontend origins
9. **Audit log** every tool execution, approval, and permission change
10. **Prompt injection** check: scan all LLM inputs for injection patterns before sending
11. **Input sanitization**: strip dangerous characters from user-provided data
12. **HTTPS** enforced in production (NGINX TLS termination)

---

## COGNITIVE PIPELINE (MUST IMPLEMENT IN ORDER)

```
1. Input Reception       — validate, sanitize, classify intent
2. Intent Understanding  — LLM-based intent extraction with structured output
3. Task Decomposition    — break into atomic subtasks, build DAG
4. Memory Retrieval      — semantic + episodic + graph memory lookup
5. Planning              — generate execution plan with tool selections
6. Risk Analysis         — score each action, flag high-risk ops
7. Tool Selection        — select tools based on task requirements and permissions
8. Execution             — run tools in sandbox, collect results
9. Validation            — verify results against expectations
10. Reflection           — score quality, detect hallucinations, log insights
11. Memory Consolidation — store outcomes, update embeddings, update graph
```

---

## FRONTEND DASHBOARD SPECIFICATION

The frontend is a **command center**, NOT a chat UI.

Pages:
1. **Dashboard** (`/dashboard`) — system health, active agents, recent events
2. **Agents** (`/agents`) — list, create, monitor, control agents
3. **Workflows** (`/workflows`) — builder (drag-and-drop with React Flow), execution history
4. **Memory Explorer** (`/memory`) — search semantic memory, browse knowledge graph
5. **Security Center** (`/security`) — permissions, approvals queue, policy manager
6. **Observability** (`/observability`) — live agent graph, metrics, audit logs, traces
7. **Settings** (`/settings`) — API keys, model config, integrations

---

## TESTING REQUIREMENTS

Every branch must pass tests before merging to main:
- Unit tests: `pytest backend/tests/unit/`
- Integration tests: `pytest backend/tests/integration/`
- Coverage requirement: minimum 80%
- Frontend: `pnpm test` (Vitest)
- Security scan: `bandit -r backend/app/`

Test naming: `test_<module>_<function>_<scenario>`

---

## ENVIRONMENT VARIABLES

```bash
# Backend
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/cortexflow
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<secret>
GEMINI_API_KEY=<secret>
DEEPSEEK_API_KEY=<secret>
SECRET_KEY=<jwt-secret>
ALLOWED_ORIGINS=http://localhost:3000

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

## QUICK-START COMMANDS

```bash
# Start all services (dev)
docker-compose -f deploy/docker-compose.dev.yml up -d

# Run backend dev server
cd backend && uvicorn app.main:app --reload --port 8000

# Run Celery worker
cd backend && celery -A app.workers.celery_app worker --loglevel=info

# Run frontend dev server
cd frontend && pnpm dev

# Run tests
cd backend && pytest tests/ -v --cov=app

# Run migrations
cd backend && alembic upgrade head
```

---

## IMPLEMENTATION RULES

1. **Python style**: Black formatter, isort, type hints everywhere
2. **Async first**: Use `async/await` for all I/O operations
3. **Pydantic models**: All request/response schemas as Pydantic models
4. **Dependency injection**: Use FastAPI's `Depends()` for DB sessions, auth
5. **Error handling**: Never expose internal errors to API responses
6. **Logging**: Structured JSON logging with OpenTelemetry trace IDs
7. **No hardcoded values**: All config via `app/config.py` using pydantic-settings
8. **Database**: Use SQLAlchemy async ORM for PostgreSQL, Alembic for migrations
9. **Never commit secrets**: .env files are gitignored
10. **One responsibility per file**: Keep files focused and small

---

## OPENCLAW FEATURES TO SURPASS

| Feature | OpenClaw | CortexFlow Target |
|---|---|---|
| Memory | Single plugin | 4-tier hierarchical |
| Agents | Single main agent | 8 specialized agent types |
| Sandboxing | Optional Docker | Always-on zero-trust |
| Workflow | Prompt-driven | DAG deterministic |
| Observability | Limited | Full Prometheus + OTEL |
| Governance | None | RBAC + approval chains |
| Learning | None | Reinforcement-based |
| Model routing | Single model | Multi-model cost optimization |
| Security | DM pairing | Zero-trust pipeline |
| Enterprise | None | Full enterprise RBAC |
| Scale | Single-host | Kubernetes-native |
