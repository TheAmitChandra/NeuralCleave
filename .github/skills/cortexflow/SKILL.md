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
# Immediately commit every logical change with descriptive messages
git add -A
git commit -m "feat(<scope>): <description>"
git push origin feature/<module>
# ... test passes ...
git checkout main
git merge feature/<module> --no-ff
git push origin main
# DO NOT delete the branch — keep all branches for historical reference
```

> **RULE: Never delete any feature branch after merging. All branches are kept permanently.**

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

---

## QUEUE ARCHITECTURE

Dedicated Celery queues — workers scale independently:

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

Celery routing config in `backend/app/workers/celery_app.py`:
```python
task_routes = {
    "app.workers.agent_worker.plan_task": {"queue": "planning_queue"},
    "app.workers.agent_worker.execute_task": {"queue": "execution_queue"},
    "app.workers.agent_worker.validate_task": {"queue": "validation_queue"},
    "app.workers.agent_worker.reflect_task": {"queue": "reflection_queue"},
    "app.workers.workflow_worker.*": {"queue": "high_priority_queue"},
}
```

---

## WORKFLOW STATE MACHINE

### Normal Path
```
PENDING → RUNNING → VALIDATING → REFLECTING → COMPLETED
```

### Failure Path
```
RUNNING → FAILED → RETRYING (max 3) → ROLLED_BACK
```

### Pause/Resume Path
```
RUNNING → PAUSED → RESUMED → RUNNING
```

### Full State Transition Table
| From | Event | To |
|---|---|---|
| PENDING | agent_assigned | RUNNING |
| RUNNING | validation_started | VALIDATING |
| VALIDATING | reflection_started | REFLECTING |
| REFLECTING | all_tasks_complete | COMPLETED |
| RUNNING | error_raised | FAILED |
| FAILED | retry_triggered | RETRYING |
| RETRYING | max_retries_exceeded | ROLLED_BACK |
| RUNNING | pause_requested | PAUSED |
| PAUSED | resume_requested | RUNNING |
| RUNNING | human_override | PAUSED |

Persist all transitions to `audit_logs` table.

---

## EXECUTION ISOLATION LEVELS

Every tool execution is assigned an isolation tier based on risk score:

| Risk Level | Score Range | Isolation Type | Technology |
|---|---|---|---|
| Low | 0–25 | Shared process | Python subprocess with limits |
| Medium | 26–60 | Ephemeral container | Docker (auto-removed after exec) |
| High | 61–85 | Isolated container | Docker + network isolation |
| Critical | 86–100 | Human approval required | Block until operator approves |

Rules:
- Shell tools: minimum Medium isolation
- Browser tools: minimum High isolation
- File writes: minimum Medium isolation
- API calls: Low isolation unless external comms
- Database writes: Medium isolation
- `requires_approval: true` tools: always Critical

---

## MEMORY COMPRESSION STRATEGY

Context explosion prevention — critical for long-running agents:

### Compression Layers
1. **Context Summarization** — LLM-generated summary when context > 80% of model limit
2. **Semantic Pruning** — Remove embeddings with similarity > 0.95 (deduplication)
3. **Importance Scoring** — Score each memory entry; prune low-score entries first
4. **TTL Expiration** — Short-term Redis memory: TTL 1 hour; episodic: TTL configurable
5. **Embedding Deduplication** — Cosine similarity check before storing new vector

### Importance Score Formula
```python
importance = (recency_weight * recency) + (access_weight * access_count) + (relevance_weight * relevance_score)
# Default weights: recency=0.4, access=0.3, relevance=0.3
```

### Summarization Trigger
- Token count > 75% of model context window → trigger summarization
- Memory entries > 500 per agent → trigger pruning
- Redis memory TTL: 3600s (1h) for short-term, configurable via env

---

## MODEL FAILURE FALLBACK SYSTEM

### Fallback Chain
```
Gemini Pro (primary)
  ↓ [timeout / rate limit / API error]
DeepSeek (secondary)
  ↓ [unavailable]
Ollama local inference (tertiary)
  ↓ [unavailable]
DEGRADED MODE — return structured error, pause workflow, notify operator
```

### Retry Policy per Provider
| Provider | Max Retries | Backoff | Timeout |
|---|---|---|---|
| Gemini | 3 | Exponential (1s, 2s, 4s) | 30s |
| DeepSeek | 2 | Linear (2s, 4s) | 45s |
| Ollama | 1 | Fixed (3s) | 60s |

### Degraded Execution Mode
- Log provider failure to `audit_logs`
- Emit `model.provider.failed` event to event bus
- Pause affected workflows
- Notify operators via configured channel (webhook/email)
- Resume when provider recovers (health check every 60s)

---

## DISTRIBUTED AGENT COORDINATION

For multi-node deployments:

### Node Types
| Node | Role |
|---|---|
| Controller Node | Runs PlannerAgent, RouterAgent |
| Worker Node | Runs ExecutorAgent (horizontally scaled) |
| Memory Node | Runs MemoryAgent, manages Qdrant/Neo4j |
| Observer Node | Runs ObserverAgent, feeds Prometheus |

### Coordination Mechanism
- **Redis pub/sub** for agent-to-agent events
- **Celery task routing** for cross-node work assignment
- **PostgreSQL advisory locks** for distributed workflow checkpoints
- **Node-aware scheduler** routes tasks to nodes based on capability tags

### Cross-Node Scheduling
```python
# Task routed to node with tag: gpu=true, memory=high
task.apply_async(queue="execution_queue", routing_key="node.gpu")
```

---

## MCP COMPATIBILITY

CortexFlow supports **Model Context Protocol (MCP)** for external tool interoperability.

### Implementation
- CortexFlow exposes an **MCP server** endpoint (`/mcp/`) for external AI clients
- CortexFlow can consume **external MCP servers** as tool providers
- MCP tools registered in the Tool Registry with `source: "mcp"` tag

### MCP Tool Schema Extension
```python
class MCPToolDefinition(ToolDefinition):
    source: Literal["internal", "mcp", "plugin"]
    mcp_server_url: str | None = None
    mcp_schema: dict | None = None
```

### Benefits
- Interoperability with Claude, Cursor, other MCP-compatible clients
- External tool ecosystem integration without custom connectors
- Future-proof extensibility

---

## HUMAN-IN-THE-LOOP UX

### Philosophy
> Autonomy must remain controllable at all times. Humans can intervene, override, or pause any agent at any point.

### UX Interaction Points
1. **Approval Queue** — frontend panel shows pending approvals with context + risk score
2. **Live Pause** — any running workflow can be paused mid-execution from dashboard
3. **Manual Override** — operator can inject a manual action replacing agent's planned action
4. **Intervention UI** — modal showing agent's reasoning at pause point, allowing edit + resume
5. **Step-through Mode** — debug mode where every cognitive stage requires manual confirm

### Approval Card (Frontend)
Each approval card shows:
- Action requested (tool name + parameters)
- Risk score (visual gauge)
- Agent's reasoning for this action
- Memory context that led to this decision
- Approve / Reject / Modify buttons

### Frontend API
```
POST /api/v1/approvals/{approval_id}/approve
POST /api/v1/approvals/{approval_id}/reject
POST /api/v1/approvals/{approval_id}/modify
GET  /api/v1/approvals/pending
WebSocket: ws://host/ws/approvals  ← live approval stream
```

---

## DISASTER RECOVERY

### Backup Strategy
| Data | Backup Method | Frequency | Retention |
|---|---|---|---|
| PostgreSQL | pg_dump → encrypted S3/local | Every 6h | 30 days |
| Qdrant snapshots | Qdrant snapshot API | Daily | 7 days |
| Neo4j dump | `neo4j-admin dump` | Daily | 7 days |
| Redis RDB | Redis BGSAVE | Every 15min | 24h |
| Workflow checkpoints | PostgreSQL (already persisted) | Real-time | Forever |

### Workflow Restoration
- Every workflow has checkpoints stored in `workflows.checkpoint` JSONB
- On restart: query incomplete workflows, resume from last checkpoint
- Checkpoint replay: re-execute from last successful step (idempotent steps required)

### Recovery RTO/RPO Targets
- RTO (Recovery Time Objective): < 5 minutes
- RPO (Recovery Point Objective): < 15 minutes

### Idempotency Requirements
- All tool calls must include idempotency keys
- Re-execution of a completed step returns cached result, does not re-execute

---

## RESOURCE SCHEDULING

### GPU Scheduling (for local inference)
- Ollama GPU allocation managed via Docker resource limits
- GPU-intensive tasks routed to `gpu_queue`
- CPU-only fallback if GPU unavailable

### Worker Allocation Table
| Queue | Min Workers | Max Workers | Scale Trigger |
|---|---|---|---|
| planning_queue | 1 | 4 | queue depth > 10 |
| execution_queue | 2 | 16 | queue depth > 5 |
| validation_queue | 1 | 8 | queue depth > 10 |
| reflection_queue | 1 | 4 | queue depth > 20 |
| observability_queue | 1 | 2 | queue depth > 100 |

### Token Budget Enforcement
```python
class TokenBudget(BaseModel):
    max_tokens_per_task: int = 50_000
    max_tokens_per_workflow: int = 500_000
    max_cost_per_workflow_usd: float = 1.00
    alert_threshold_pct: float = 0.80  # alert at 80% budget
```

---

## BENCHMARKING SYSTEM

**Branch:** `feature/benchmarking`

### Core Metrics
| Metric | Description | Target |
|---|---|---|
| Task Completion Rate | % tasks completed successfully | > 95% |
| Hallucination Rate | % responses flagged as hallucinated | < 2% |
| Execution Latency P50 | Median task execution time | < 5s |
| Execution Latency P99 | 99th percentile task time | < 30s |
| Token Efficiency | Tokens used / task complexity score | Minimize |
| Workflow Reliability | % workflows completing without rollback | > 98% |
| Memory Hit Rate | % memory retrievals returning relevant context | > 85% |
| Tool Success Rate | % tool calls completing without error | > 99% |

### Benchmark Runner
- Automated benchmark suite in `backend/tests/benchmarks/`
- Runs on every merge to `main` via GitHub Actions
- Results posted to observability dashboard
- Regression alerts if any metric drops > 5% vs baseline

---

## AI SAFETY PHILOSOPHY

> **Autonomy must remain controllable. Humans remain in the loop for all high-stakes decisions.**

### Core Safety Principles
1. **Bounded Autonomy** — agents operate within explicitly defined permission scopes, never beyond
2. **Reversible Actions** — prefer reversible operations; irreversible ops require approval
3. **Transparency** — every reasoning step is logged and auditable
4. **Fail Safe** — on uncertainty, pause and request human guidance rather than guess
5. **Minimal Footprint** — agents request only the minimum permissions needed for the task
6. **No Self-Modification** — agents cannot modify their own execution rules or permissions
7. **Observable Reasoning** — no black-box decisions; all cognition steps exposed in UI

### Hard Limits (Never Overridable)
- Agents cannot escalate their own permissions
- Agents cannot disable audit logging
- Agents cannot modify governance policies
- Shell access is always sandboxed — never raw host shell
- No agent can communicate outside the system without explicit tool permission

---

## NON-GOALS

CortexFlow does NOT aim to:
- Build AGI or replace human intelligence
- Enable unrestricted autonomous execution without oversight
- Allow raw unsandboxed shell access to host systems
- Remove human oversight from critical or irreversible operations
- Compete with general-purpose chat assistants (it is not a chatbot)
- Provide a prompt wrapper around an LLM
- Replace human judgment in ethical or safety-critical decisions
- Enable autonomous financial transactions without approval
- Build a personal assistant for individual messaging (that is OpenClaw's domain)

CortexFlow IS and PRIORITIZES:
- Controllable autonomy with observable reasoning
- Enterprise-grade orchestration with deterministic workflows
- Secure, sandboxed, risk-scored execution
- Modular, extensible infrastructure for AI workforces

---

## MARKETPLACE ARCHITECTURE

**Branch:** `feature/marketplace`

### Plugin Trust Levels
| Level | Description | Requirements |
|---|---|---|
| Official | Built by CortexFlow team | Code review + security audit |
| Verified | Third-party, reviewed | Signed package + manifest audit |
| Community | Unreviewed public | User installs at own risk |
| Private | Enterprise internal | Org namespace, no public listing |

### Plugin Manifest Schema
```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "author": "org/author",
  "trust_level": "community",
  "permissions": ["web_access", "file.read"],
  "sandbox_required": true,
  "signature": "<ed25519-signature>"
}
```

### Security Requirements
- All plugins run in sandboxed execution (minimum Medium isolation)
- Plugins cannot access host memory or other agents' memory namespaces
- Plugin signatures verified before loading
- Malicious plugin reporting system in marketplace

---

## BROWSER SECURITY POLICIES

Browser automation is one of the highest-risk tool categories.

### Domain Policy
```python
class BrowserPolicy(BaseModel):
    allowed_domains: list[str]          # explicit allowlist
    blocked_domains: list[str]          # e.g. ["banking.com", "*.gov"]
    block_credential_forms: bool = True # prevent password field interaction
    block_downloads: bool = True        # no file downloads without approval
    screenshot_logging: bool = True     # log all screenshots to audit
    max_session_duration_seconds: int = 300
```

### Anti-Phishing Controls
- URL validation before navigation (Google Safe Browsing API integration)
- Block redirects to non-allowlisted domains
- Detect and block login form interactions on non-approved domains
- All browser sessions run in isolated Docker container with no host network access

### Credential Isolation
- Browser agents never have access to credential store
- Login flows requiring credentials use a dedicated credentialed-browser-agent with human approval

---

## SEMANTIC SEARCH PIPELINE

Full retrieval pipeline — not just embedding + search:

```
User Query
    ↓
Query Embedding (sentence-transformers)
    ↓
Qdrant Approximate Nearest Neighbor Search (top-k=20)
    ↓
Metadata Filtering (agent_id, memory_type, time range)
    ↓
Cross-Encoder Reranking (rerank top-20 → top-5)
    ↓
Hybrid Search Merge (vector score + BM25 keyword score)
    ↓
Context Scoring (recency + access frequency + relevance)
    ↓
Deduplication (remove near-duplicate results)
    ↓
Final Context Assembly (top-5 results → prompt)
```

### Technologies
- ANN search: Qdrant
- Reranking: `cross-encoder/ms-marco-MiniLM-L-6-v2`
- Hybrid search: Qdrant sparse + dense vectors
- BM25: rank-bm25 library

---

## MULTI-TENANT ISOLATION

Critical for enterprise deployments.

### Isolation Layers
1. **Database** — row-level security in PostgreSQL (`WHERE tenant_id = :tenant_id`)
2. **Memory** — Qdrant collections namespaced per tenant (`{tenant_id}_knowledge`)
3. **Neo4j** — separate database per tenant (Neo4j 4+ multi-database)
4. **Redis** — key prefixing per tenant (`{tenant_id}:{agent_id}:*`)
5. **Celery** — separate queue sets per tenant (configurable)
6. **RBAC** — all permissions scoped to tenant namespace

### Tenant Model
```python
class Tenant(BaseModel):
    id: UUID
    name: str
    plan: Literal["free", "pro", "enterprise"]
    max_agents: int
    max_workflows_per_day: int
    memory_quota_mb: int
    allowed_tools: list[str]
```

### Tenant Context Propagation
- Every request carries `X-Tenant-ID` header
- FastAPI middleware extracts and validates tenant on every request
- All DB queries automatically scoped via SQLAlchemy event listeners

---

## EVENT REPLAY SYSTEM

**Branch:** `feature/event-sourcing`

### Event Sourcing Design
- Every state-changing event stored in `event_store` table (append-only)
- Events are the source of truth; current state is a projection
- Workflows can be fully replayed from event store for debugging

### Event Store Schema
```sql
CREATE TABLE event_store (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_id UUID NOT NULL,     -- workflow_id or agent_id
    event_type VARCHAR NOT NULL,
    event_data JSONB NOT NULL,
    metadata JSONB,
    sequence_number BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_event_store_stream ON event_store(stream_id, sequence_number);
```

### Replay Use Cases
- Debug failed workflows by replaying step-by-step
- Reproduce bugs in staging environment
- Audit compliance replay
- Training data generation for adaptive learning

---

## RUNTIME POLICY ENGINE

**Branch:** `feature/policy-engine`

### Policy Definition (YAML)
```yaml
# policies/default.yaml
policies:
  - name: "block_external_comms_without_approval"
    applies_to: ["executor_agent"]
    trigger: "tool.execute"
    condition: "tool.category == 'comms'"
    action: "require_approval"
    priority: 100

  - name: "block_file_write_outside_workspace"
    applies_to: ["*"]
    trigger: "tool.execute"
    condition: "tool.name == 'file.write' AND path NOT STARTSWITH workspace_root"
    action: "deny"
    priority: 90

  - name: "rate_limit_api_calls"
    applies_to: ["*"]
    trigger: "tool.execute"
    condition: "tool.category == 'api' AND call_count > 100"
    action: "throttle"
    priority: 80
```

### Policy Evaluation Order
1. Deny policies (highest priority, evaluated first)
2. Approval policies
3. Throttle policies
4. Allow policies (lowest priority, default allow if no match)

### Dynamic Policy Updates
- Policies reloaded without restart via Redis pub/sub signal
- Org-level policies override tenant-level override user-level
- Policy violations always logged to `audit_logs`

---

## AI TOOL VERIFICATION

Before any tool executes:

### Verification Pipeline
```
Tool Call Request
    ↓
1. Schema Validation    — parameters match ToolDefinition schema
    ↓
2. Permission Check     — agent has required permission scope
    ↓
3. Risk Scoring         — calculate risk score (0–100)
    ↓
4. Policy Evaluation    — run through RuntimePolicyEngine
    ↓
5. Dry-Run Simulation   — for high-risk tools: simulate execution path
    ↓
6. Sandbox Allocation   — allocate isolation tier based on risk
    ↓
7. Execution            — run tool in allocated sandbox
    ↓
8. Result Validation    — verify output schema and content
    ↓
9. Audit Log            — record full execution chain
```

### Dry-Run Mode
- Available for: `shell.*`, `file.write`, `db.write`, `api.*`
- Simulates execution without side effects
- Returns predicted outcome for agent to evaluate before real execution
- Activated automatically for risk score > 60

---

## LOCAL-FIRST AI MODE

**Branch:** `feature/local-first-mode`

CortexFlow can operate fully offline — a critical enterprise differentiator.

### Local Stack
| Component | Local Alternative |
|---|---|
| Gemini API | Ollama (llama3, mistral, codellama) |
| sentence-transformers | Runs locally (no API needed) |
| Qdrant | Local Docker instance |
| Neo4j | Local Docker instance |
| PostgreSQL | Local Docker instance |
| Redis | Local Docker instance |

### Air-Gapped Mode
- Zero external network calls
- All models downloaded and cached locally
- Browser tools disabled (no external network)
- Event triggers limited to local sources (filesystem, local webhooks)
- Full cognitive pipeline operates on local models

### Local-First Startup
```bash
docker-compose -f deploy/docker-compose.local.yml up -d
CORTEXFLOW_MODE=local uvicorn app.main:app --reload
```

### Configuration
```bash
CORTEXFLOW_MODE=local|cloud|hybrid
LOCAL_LLM_MODEL=ollama/llama3:70b
LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
DISABLE_EXTERNAL_APIS=true  # air-gapped enforcement
```

---

## DATA RETENTION POLICIES

| Data Type | Default Retention | Configurable |
|---|---|---|
| Audit Logs | 1 year | Yes (min: 90 days) |
| Reasoning Traces | 90 days | Yes |
| Workflow Events | 180 days | Yes |
| Memory Embeddings | Until pruned | Yes |
| Tool Call Records | 180 days | Yes |
| Deleted Workflows | Soft-delete 30 days | Yes |
| Feedback Entries | 1 year | Yes |
| Short-Term Memory | 1 hour (TTL) | Yes |

### Compliance
- **GDPR** — hard-delete all user data on deletion request, confirmed via audit log
- **Tenant-level overrides** — enterprise tenants can extend or shorten retention via policy
- **Archival** — data past retention moved to cold storage (S3 Glacier / local archive) before deletion
- **Secure deletion** — embeddings purged from Qdrant, rows deleted from PostgreSQL, keys expired in Redis, nodes removed from Neo4j

### Retention Enforcement
- Celery beat task runs nightly: `purge_expired_data`
- Soft-deleted records flagged with `deleted_at` timestamp, hard-deleted after grace period
- Deletion events logged to `audit_logs` (irrevocably)

---

## SECRET ROTATION SYSTEM

Secrets never stored permanently in application memory or code.

### Secret Storage Hierarchy
1. **HashiCorp Vault** — production secrets (API keys, DB passwords, JWT secret)
2. **Environment variables** — local dev only (`.env`, gitignored)
3. **Scoped tokens** — short-lived tokens injected at task execution time

### Rotation Capabilities
- Automatic API key rotation (Vault dynamic secrets)
- JWT secret rotation with overlapping validity window (old + new both valid during transition)
- Token expiration renewal before TTL expires (proactive refresh)
- Credential revocation — instant invalidation on breach detection
- Secret usage auditing — every secret access logged with agent_id + task_id

### Vault Integration
```python
# backend/app/core/security/vault.py
async def get_secret(path: str, key: str) -> str:
    """Retrieve secret from Vault. Never cached in memory beyond request scope."""
    ...

async def rotate_secret(path: str) -> None:
    """Trigger rotation and update dependent services."""
    ...
```

### Rules
- No API key hardcoded anywhere in codebase
- No secret in `git log` — enforced by pre-commit hook (`detect-secrets`)
- All secrets injected as environment variables at container start via Vault agent sidecar

---

## WORKFLOW VERSIONING

Workflow DAG definitions are **immutable once executed**.

### Versioning Model
```python
class WorkflowDefinition(BaseModel):
    id: UUID
    name: str
    version: int                    # auto-incremented
    schema_version: str             # e.g. "1.0"
    dag_definition: dict
    policy_snapshot: dict           # policies active at creation time
    is_active: bool
    created_at: datetime
    deprecated_at: datetime | None
```

### Capabilities
- **Versioned definitions** — each change creates a new version; old versions preserved
- **Rollback** — revert to any previous workflow version via API
- **Migration compatibility** — workflow runner checks `schema_version` before execution
- **Diff inspection** — API endpoint returns structural diff between two workflow versions
- **Execution audit** — every workflow run records `workflow_version` used

### API
```
GET  /api/v1/workflows/{id}/versions
POST /api/v1/workflows/{id}/rollback?version=3
GET  /api/v1/workflows/{id}/diff?v1=2&v2=3
```

---

## FEATURE FLAG SYSTEM

**Branch:** `feature/feature-flags`

Staged rollouts and experimental module isolation without redeployment.

### Storage
- Feature flags stored in PostgreSQL `feature_flags` table
- Cached in Redis with TTL 60s (eventual consistency acceptable)
- Flag changes take effect within 60 seconds without restart

### Flag Schema
```python
class FeatureFlag(BaseModel):
    key: str                                    # e.g. "enable_reflection_engine"
    enabled: bool
    rollout_percentage: float = 100.0           # 0–100, for gradual rollout
    tenant_overrides: dict[str, bool] = {}      # per-tenant on/off
    description: str
    expires_at: datetime | None = None          # auto-disable experimental flags
```

### Usage in Code
```python
from app.core.features import flag

if await flag.is_enabled("enable_adaptive_learning", tenant_id=tenant_id):
    await learning_optimizer.run(task)
```

### Capability
- Tenant-scoped enablement (e.g. enable GPU routing only for enterprise tier)
- Experimental module isolation — new modules gated behind flags until stable
- Percentage rollout for gradual deployment risk reduction
- Expiring flags for time-limited experiments

---

## TENANT COST ACCOUNTING

**Branch:** `feature/cost-accounting`

Track and enforce costs per tenant — required for SaaS monetization.

### Tracked Resources
| Resource | Unit | Tracked In |
|---|---|---|
| LLM tokens (input) | tokens | `cost_ledger` |
| LLM tokens (output) | tokens | `cost_ledger` |
| API calls (external) | count | `cost_ledger` |
| Vector storage | MB | `cost_ledger` |
| Workflow executions | count | `cost_ledger` |
| GPU inference time | seconds | `cost_ledger` |
| Storage (PostgreSQL) | MB | `cost_ledger` |

### Cost Ledger Schema
```sql
CREATE TABLE cost_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    resource_type VARCHAR NOT NULL,
    quantity FLOAT NOT NULL,
    unit_cost_usd FLOAT NOT NULL,
    total_cost_usd FLOAT NOT NULL,
    agent_id UUID REFERENCES agents(id),
    task_id UUID REFERENCES tasks(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Quota Enforcement
- Soft quota: alert at 80% usage → email operator
- Hard quota: block new executions at 100% → return `402 Quota Exceeded`
- Real-time cost tracking via Celery signal hooks on every LLM call

---

## CHAOS TESTING STRATEGY

**Branch:** `feature/chaos-testing`

Ensure graceful degradation under failure conditions before production.

### Chaos Scenarios
| Scenario | Simulation Method | Expected Behavior |
|---|---|---|
| Gemini API outage | Mock provider returns 503 | Fallback to DeepSeek |
| Redis failure | Stop Redis container | Celery retries, no data loss |
| PostgreSQL slow | tc netem delay 500ms | Timeout + retry with backoff |
| Qdrant unavailable | Stop Qdrant container | Memory retrieval degrades gracefully |
| Queue overload | Publish 10,000 tasks rapidly | Worker autoscaling, no crash |
| Worker node failure | Kill worker process mid-task | Task requeued from checkpoint |
| Delayed event | Inject 30s delay on event bus | Workflow resumes from checkpoint |
| Memory poisoning | Inject adversarial embedding | Prompt injection defense triggers |

### Tools
- `pytest-chaos` for unit-level fault injection
- Docker Compose service stop/restart for integration chaos
- `locust` for load/overload simulation
- Custom Celery signal interceptors for queue chaos

### Acceptance Criteria
- Zero data loss under any single-component failure
- All workflows resume from checkpoint after node recovery
- No security boundary violated under chaos conditions

---

## EXPLAINABILITY LAYER

Every agent decision must be human-readable and inspectable.

### Explanation Requirements
Agents must record explanations for:
- **Tool selection** — why this tool was chosen over alternatives
- **Workflow pause** — what condition triggered the pause
- **Action denial** — which policy rule denied the action and why
- **Memory retrieval** — why this memory was retrieved (similarity score + context)
- **Model routing** — why this LLM was selected for this task
- **Risk scoring** — breakdown of risk score components

### Explanation Schema
```python
class Explanation(BaseModel):
    decision_type: str          # "tool_selection" | "workflow_pause" | "action_denied" | ...
    decision: str               # what was decided
    reasoning: str              # human-readable explanation
    confidence: float           # 0.0–1.0
    evidence: list[str]         # memory IDs or context snippets used
    policy_refs: list[str]      # policy names that applied
    created_at: datetime
```

### Frontend
- Every reasoning step in the agent graph shows an expandable explanation card
- Security Center shows denial explanations with policy reference
- Memory Explorer shows retrieval explanations with similarity scores

---

## SCHEMA EVOLUTION STRATEGY

All schemas versioned explicitly — critical with multiple long-lived data stores.

### Rules
1. **Never drop a column** — only add columns (with defaults) or deprecate
2. **Backward compatibility** — new code reads old schema; old data always readable
3. **API contracts versioned** — breaking changes go to `/api/v2/`, not in-place
4. **Event schema versioned** — every event carries `schema_version` field
5. **Migration safety** — all Alembic migrations are reversible (downgrade implemented)

### Migration Checklist (per Alembic migration)
- [ ] Upgrade script tested on copy of production data
- [ ] Downgrade script implemented and tested
- [ ] No column drops (use `deprecated: true` metadata instead)
- [ ] Migration runs in < 30 seconds on expected data volume (or uses online DDL)
- [ ] Migration reviewed by second engineer before merge

### Pydantic Schema Versioning
```python
class WorkflowEventV1(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    ...

class WorkflowEventV2(WorkflowEventV1):
    schema_version: Literal["2.0"] = "2.0"
    # new fields with defaults for backward compat
    new_field: str = "default"
```

---

## SLA & RELIABILITY TARGETS

### Target Objectives
| Metric | Target | Measurement |
|---|---|---|
| API Availability | 99.9% | Uptime over 30-day window |
| Workflow Completion Rate | > 98% | Completed / (Completed + Failed) |
| Task Completion Rate | > 95% | Including retried tasks |
| P50 API Response Time | < 200ms | Excluding LLM inference time |
| P99 Workflow Latency | < 30s | End-to-end workflow completion |
| Recovery Time Objective | < 5 minutes | Time to restore after failure |
| Recovery Point Objective | < 15 minutes | Max data loss window |
| Hallucination Rate | < 2% | Flagged by reflection engine |

### Priority Under Contention
During resource contention, execution priority order:
1. Security-flagged approval workflows (always first)
2. High-priority queue tasks
3. Active user-triggered workflows
4. Background learning tasks
5. Observability writes (degraded but non-blocking)

### SLO Monitoring
- Prometheus alerting rules fire when any SLO target is breached
- On-call notification via configured webhook (Slack/PagerDuty/email)
- Monthly SLO review report auto-generated from metrics

---

## SIMULATION ENVIRONMENT

**Branch:** `feature/simulation-mode`

Before real execution, workflows can run in simulation mode to estimate cost and risk.

### Simulation Capabilities
- **Dry-run orchestration** — trace full execution path without side effects
- **Cost estimation** — project token usage and API cost based on task complexity
- **Risk estimation** — score each step's risk before committing to execution
- **Dependency validation** — verify all required tools/permissions are available
- **Execution prediction** — predict likely outcomes based on similar past workflows

### Simulation Output
```python
class SimulationReport(BaseModel):
    workflow_id: UUID
    projected_steps: list[SimulatedStep]
    estimated_tokens: int
    estimated_cost_usd: float
    estimated_duration_seconds: float
    risk_summary: dict                  # per-step risk scores
    predicted_failure_points: list[str]
    dependency_gaps: list[str]          # missing permissions or tools
```

### API
```
POST /api/v1/workflows/simulate
# Returns SimulationReport without executing anything
```

### Activation
- Automatically triggered for workflows with any `risk_level: "high"` step
- Always available on demand via API
- Frontend shows simulation report before user confirms execution

---

## COGNITIVE TRACE COMPRESSION

Long reasoning chains are compressed to prevent unbounded storage growth.

### Compression Strategy
1. **Hierarchical Summarization** — after N reasoning steps, LLM generates a summary that replaces the chain
2. **Semantic Clustering** — group similar reasoning steps, store cluster centroid + count
3. **Reflection Synthesis** — reflection engine distills key learnings into a single insight record
4. **Importance-Based Pruning** — low-importance intermediate steps pruned after workflow completes

### Compression Triggers
- Reasoning chain > 50 steps → trigger hierarchical summarization
- Storage per agent > 100MB of traces → trigger semantic clustering pass
- Workflow completed → trigger reflection synthesis, prune raw steps after 7 days

### Guarantee
Compressed traces always retain:
- Final decision at each cognitive stage
- All tool calls and their results
- All validation/reflection outcomes
- All denial/approval events

Raw intermediate reasoning steps are compressible.

---

## API VERSIONING POLICY

### Versioning Scheme
- All REST APIs versioned under `/api/v{N}/`
- Current stable: `/api/v1/`
- WebSocket APIs versioned via `api_version` field in connection handshake

### Breaking vs Non-Breaking Changes
| Change Type | Action |
|---|---|
| Add new field (optional) | Non-breaking — ship in existing version |
| Remove field | Breaking — requires new version |
| Change field type | Breaking — requires new version |
| Add new endpoint | Non-breaking |
| Change URL path | Breaking — requires new version |
| Change status code semantics | Breaking |

### Deprecation Policy
1. New version released with migration guide
2. Old version marked `deprecated` in OpenAPI docs
3. Deprecation header added to old version responses: `Deprecation: true`
4. Old version maintained for minimum 6 months
5. Old version removed after sunset date announced in changelog

---

## GOVERNANCE ESCALATION RULES

High-risk actions escalate automatically through an approval chain.

### Escalation Triggers
| Condition | Escalation Target |
|---|---|
| Risk score 61–85 | Operator |
| Risk score 86–100 | Admin |
| Policy violation detected | Security Auditor |
| Repeated denial (3x same action) | Admin + Security Auditor |
| Sandbox escape attempt | Security Auditor (immediate) |
| Secret access outside task scope | Security Auditor (immediate) |
| Cross-tenant data access attempt | Admin + Security Auditor (immediate) |

### Escalation Chain
```
Agent Action
    ↓
Risk Score ≥ 61 → Operator notified (15 min SLA)
    ↓ [no response or risk ≥ 86]
Admin notified (5 min SLA)
    ↓ [policy violation or security event]
Security Auditor notified (immediate)
```

### Notification Channels
Configurable per tenant: Slack webhook, email, PagerDuty, or in-app notification.

---

## COGNITIVE BUDGETING

Reasoning depth dynamically adjusted to balance cost, latency, and quality.

### Budget Dimensions
| Dimension | Controls |
|---|---|
| Token budget | Max tokens per reasoning stage |
| Time budget | Max seconds per cognitive step |
| Cost budget | Max USD per task |
| Depth budget | Max reasoning chain length |

### Routing by Task Complexity
| Task Complexity | Reasoning Mode | Model | Max Tokens |
|---|---|---|---|
| Trivial (score 0–20) | Direct response | Gemini Flash / Ollama | 1,000 |
| Simple (score 21–40) | Single-stage reasoning | Gemini Flash | 5,000 |
| Medium (score 41–70) | Full cognitive pipeline | Gemini Pro | 20,000 |
| Complex (score 71–100) | Deep multi-stage + reflection | Gemini Pro | 50,000 |

### Complexity Scorer
```python
class ComplexityScorer:
    def score(self, task: Task) -> int:
        """Returns 0–100. Considers: subtask count, tool dependencies, 
        memory requirements, risk level, novelty vs past tasks."""
```

---

## AGENT IDENTITY MODEL

Every agent has a unique, persistent, verifiable identity.

### Agent Identity Schema
```python
class AgentIdentity(BaseModel):
    id: UUID                            # immutable
    name: str
    type: AgentType                     # planner|router|executor|validator|critic|memory|security|observer
    capability_profile: list[str]       # declared capabilities
    permission_scope: list[str]         # granted permissions
    trust_score: float                  # 0.0–1.0, updated by reflection engine
    behavioral_metrics: dict            # success rate, avg latency, hallucination rate
    execution_history_count: int
    created_at: datetime
    last_active_at: datetime
```

### Trust Score
- Starts at `0.5` for all new agents
- Increases with successful validated task completions
- Decreases with hallucinations, policy violations, failed validations
- Trust score < 0.3 → agent suspended, admin notified
- Trust score affects routing priority (higher trust → preferred for critical tasks)

### Identity Rules
- Agents never share execution identity — each task run carries the agent's `id`
- Agents cannot impersonate other agents
- Agent identities logged in every `audit_log` entry
- Permission scope changes require admin approval and are logged immutably
