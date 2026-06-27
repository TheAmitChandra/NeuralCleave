# CortexFlow-AI — Claude Skill File
## Complete Working Knowledge Base for AI-Assisted Development

**Version:** 2.0 | **Analyzed:** 2026-06-06 | **Model:** Claude Sonnet 4.6  
**Use when:** Any task on the CortexFlow-AI codebase — bug fixes, feature implementation, testing, architecture decisions, or enterprise pitch preparation.

---

## PROJECT IDENTITY

**CortexFlow-AI** is an enterprise-grade Autonomous Cognitive Operating System — the "Kubernetes for Autonomous AI Agents." It orchestrates AI agents at scale with deterministic DAG workflows, 4-tier memory, zero-trust sandboxing, multi-model LLM routing, and RBAC governance.

**Target Market:** Enterprise — financial services, healthcare, legal, SaaS companies needing governed AI automation.

**Pitch Positioning:** The only AI agent platform that combines Kubernetes-grade orchestration, bank-grade security, and full enterprise governance — where CrewAI, AutoGen, and LangChain are research tools, CortexFlow-AI is production infrastructure.

---

## ABSOLUTE WORKFLOW RULES (READ FIRST)

> **RULE 1:** One file changed → one immediate commit + one immediate push. No exceptions.  
> **RULE 2:** Never accumulate changes across files before committing.  
> **RULE 3:** Sequence: `edit file → git add <file> → git commit -m "..." → git push → then next file`  
> **RULE 4:** Every bug fix, every new endpoint, every test = its own commit + push.  
> **RULE 5:** Never develop on `main`. Always `feature/<module>` branch.

### Commit Message Format
```
<type>(<scope>): <short description>

Types:  feat | fix | refactor | test | docs | chore | security
Scopes: agent-runtime | memory | workflow | security | tools | frontend
        db | api | observability | learning | governance
```

### Branch Naming
```
feature/agent-runtime
feature/memory-system
feature/workflow-engine
feature/security
feature/observability
```

---

## ARCHITECTURE QUICK REFERENCE

### Entry Points
```
backend/app/main.py              FastAPI app factory + lifespan hooks
backend/main.py                  Uvicorn launcher (development)
backend/app/workers/celery_app.py  Celery config + Beat schedule
```

### Core Module Map
```
app/core/
├── agent_runtime/       AgentRuntime (IDLE→PLANNING→EXECUTING→VALIDATING→REFLECTING)
├── orchestration/       MultiAgentOrchestrator (Planner→Router→Executor→Validator→Critic)
├── memory/              4-tier memory (short_term/episodic/long_term/knowledge_graph + retrieval)
├── workflow_engine/     DAG definition + topological sort + checkpoints + recovery
├── security/            JWT + sandbox (4 Docker tiers) + prompt injection + audit
├── tools/               Tool registry (9-step pipeline) + browser/shell/file/api/db tools
├── model_router/        Gemini/DeepSeek/Ollama + fallback chain + token budgets
├── reflection/          Quality scoring + hallucination detection + decision matrix
├── observability/       structlog + Prometheus + OpenTelemetry + log buffer
├── governance/          RBAC (5 roles, 30+ permissions) + approvals + policy
├── events/              Redis pub/sub event bus + triggers (cron/webhook/email/db)
└── learning/            Feedback collection + behavior optimization + failure detection
```

### Database Layer
```
app/db/
├── postgres.py          AsyncSession factory (pool_size=10, max_overflow=20)
├── redis.py             Redis client (max_connections=50, decode_responses=True)
├── qdrant.py            AsyncQdrantClient (384-dim, Cosine, 4 collections)
├── neo4j.py             AsyncDriver (pool=50, uniqueness constraints on startup)
└── models/              SQLAlchemy ORM: User, Agent, Workflow, Task, ToolCall, AuditLog, MemoryEntry
```

### API Layer
```
app/api/v1/
├── auth.py              /register /login /refresh /logout /me
├── agents.py            /create / /{id} /{id}/status /{id}/execute /{id}(DELETE)
├── workflows.py         /run / /{id} /{id}/pause /resume /rollback /{id}/dag
├── memory.py            /search /store /{id}(DELETE)
├── tools.py             / /{name}/schema /execute
├── observability.py     /logs /metrics /traces/{id} /agents/{id}/graph
├── approvals.py         /pending / /{id} /{id}/approve /reject /cancel
├── events.py            /trigger /webhooks
└── mcp.py               /mcp/initialize /resources/list /tools/call
```

---

## KNOWN BUGS — FIX BEFORE ENTERPRISE PITCH

### CRITICAL (Fix First — Production Breaking)

**BUG-001: Neo4j Cypher Parameterized Path Depth**  
`backend/app/core/memory/knowledge_graph.py:241`  
```python
# BROKEN — $depth not supported in Cypher path expressions
"MATCH path = (a:Agent {id: $agent_id})-[:COMMUNICATES_WITH*1..$depth]->(other:Agent)"

# FIX — interpolate depth as a literal integer
cypher = f"MATCH path = (a:Agent {{id: $agent_id}})-[:COMMUNICATES_WITH*1..{int(depth)}]->(other:Agent) ..."
result = await session.run(cypher, agent_id=str(agent_id))
```

**BUG-002: `asyncio.get_event_loop()` Deprecated**  
`backend/app/core/security/sandbox.py:267`  
```python
# BROKEN in Python 3.10+
loop = asyncio.get_event_loop()
# FIX
loop = asyncio.get_running_loop()
```

**BUG-003: Memory Delete Has No Ownership Check**  
`backend/app/api/v1/memory.py:204`  
```python
# BROKEN — any user can delete any memory entry
result = await db.execute(select(MemoryEntry).where(MemoryEntry.id == mid))
# FIX — add ownership join or user_id column filter
```

**BUG-004: `execute_agent_task` Never Submits to Celery**  
`backend/app/api/v1/agents.py:185-193`  
```python
# BROKEN — task_id created but task never queued
task_id = str(uuid.uuid4())
return {"status": "QUEUED"}   # ← nothing actually queued

# FIX — submit to execution_queue
from app.workers.agent_worker import run_agent_task
run_agent_task.apply_async(args=[agent_id, task_id, body.task], queue="execution_queue", task_id=task_id)
```

**BUG-005: Orphaned Docker Containers on Timeout**  
`backend/app/core/security/sandbox.py:279-293`  
Wrap cleanup (`logs()` + `remove(force=True)`) in a `finally` block so containers are always removed even if `kill()` throws.

---

### HIGH (Fix Before Demo)

**BUG-006:** `import uuid` inside `refresh_tokens()` function body — move to top of `auth.py`  
**BUG-007:** Embedding model loaded lazily — preload `SentenceTransformer("all-MiniLM-L6-v2")` in `main.py` lifespan startup  
**BUG-008:** `user.last_login_at` never updated on login — add `user.last_login_at = datetime.now(timezone.utc)` + `await db.flush()` in login handler  
**BUG-009:** `DELETE /workflows/{id}` endpoint missing — implement with guard against RUNNING state  
**BUG-010:** Observability endpoints return hardcoded empty data — wire to actual Prometheus + SpanRecorder + KnowledgeGraphMemory  

---

### MEDIUM (Fix This Sprint)

**BUG-011:** Container sandbox mixes stdout/stderr — use `stream=True` to separate  
**BUG-012:** PATCH agent route is `/{agent_id}/status` not `/{agent_id}` per spec — decide canonical path and update frontend + SDK  
**BUG-013:** `ToolRegistry.get_instance()` not thread-safe — add double-checked locking with `threading.Lock()`  
**BUG-014:** `ModelRouter` instantiated at module import time — defer to startup or lazy-init  
**BUG-015:** `rollback_workflow` allows RUNNING state — remove "RUNNING" from allowed states  
**BUG-016:** `reflect_sync` uses `asyncio.run()` which crashes if event loop running — use `asyncio.run_coroutine_threadsafe` or remove method  

---

## KEY PATTERNS & CONVENTIONS

### FastAPI Endpoint Pattern
```python
@router.post("/create", response_model=ThingResponse, status_code=status.HTTP_201_CREATED)
async def create_thing(
    body: ThingCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    thing = Thing(...)
    db.add(thing)
    await db.flush()          # flush to get auto-generated id, commit handled by get_db()
    logger.info("thing_created", thing_id=str(thing.id))
    return _thing_to_dict(thing)
```

### Database Session Pattern
```python
# get_db() commits after yield on success, rolls back on exception
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### JWT Auth Pattern
```python
# Access token: 15 min, carries role + tenant_id
# Refresh token: 7 days, carries only user_id
# All secured endpoints: current_user: User = Depends(get_current_user)
# Role-restricted endpoints: current_user: User = Depends(require_role("admin", "operator"))
```

### Tool Execution Pattern
```python
registry = ToolRegistry.get_instance()
result = await registry.execute(
    ToolCallRequest(
        tool_name="file.read",
        agent_id=agent_id,
        parameters={"path": "/data/input.txt"},
    ),
    agent_permissions=["file.read"],
)
# result.success, result.output, result.risk_score, result.isolation_tier
```

### Memory Retrieval Pattern
```python
pipeline = MemoryRetrievalPipeline(agent_id=agent_uuid)
embedding = model.encode(query).tolist()   # 384-dim vector
ctx = await pipeline.retrieve(
    query=query,
    embedding=embedding,
    top_k=10,
    db=db_session,               # needed for long-term PostgreSQL tier
)
prompt_blocks = ctx.to_prompt_blocks()     # ["[SHORT_TERM score=1.00]\n...", ...]
```

### Risk Score → Isolation Tier
```python
# calculate_risk_score(tool_def) → float 0-100
# resolve_isolation_tier(risk_score):
#   0–25  → process             (asyncio subprocess)
#   26–60 → container           (ephemeral Docker)
#   61–85 → isolated_container  (Docker + network=none + read-only FS)
#   86+   → blocked             (requires approval gate)
```

### RBAC Pattern
```python
from app.core.governance.rbac import RBACPolicy, Actor, Role

policy = RBACPolicy()
actor = Actor(actor_id=str(user.id), role=Role(user.role), tenant_id=user.tenant_id or "default")
policy.require(actor, "workflow:run")    # raises PermissionError if denied
```

### Knowledge Graph Pattern
```python
graph = KnowledgeGraphMemory()
# Always use MERGE (idempotent):
await graph.upsert_agent(agent_id, name, agent_type)
await graph.user_owns_agent(user_id, agent_id)
await graph.agent_uses_tool(agent_id, "file.read")
# Query:
tools = await graph.get_agent_tools(agent_id)          # [{name, risk_level, count}]
graph_data = await graph.get_workflow_graph(workflow_id)  # task dependency graph
```

### Reflection Engine Pattern
```python
engine = ReflectionEngine(quality_pass_threshold=60.0, hallucination_threshold=0.5)
result = await engine.reflect(
    task="Summarise the article.",
    output=agent_response,
    sources=reference_docs,
    execution_time_seconds=elapsed,
    attempt_number=retry_count,
)
# result.recommendation: "pass" | "retry" | "rethink" | "escalate"
# result.should_retry, result.should_escalate
# result.retry_delay_seconds (exponential backoff)
```

### Model Router Pattern
```python
from app.core.model_router.router import model_router

response = await model_router.generate(
    prompt="Your prompt here",
    task_type="complex_reasoning",   # routes to gemini-1.5-pro
    system_instruction="You are...",
    temperature=0.2,
    max_tokens=8192,
    agent_id=str(agent_id),         # enables token budget tracking
    task_id=str(task_id),
)
```

### DAG Construction Pattern
```python
dag = WorkflowDAG(name="data-pipeline")
dag.add_node(DAGNode("fetch", tool_name="api.get", parameters={"url": "..."}))
dag.add_node(DAGNode("process", tool_name="file.write", depends_on=["fetch"]))
dag.add_node(DAGNode("notify", tool_name="comms.email", depends_on=["process"],
                     edge_types={"process": EdgeType.ALWAYS}))  # runs even if process fails
dag.validate()                # raises DAGValidationError on cycles or missing deps
groups = dag.execution_groups()  # [[fetch], [process], [notify]]
```

---

## CONFIGURATION REFERENCE

### Required Environment Variables
```bash
SECRET_KEY=<32+ char random string>    # JWT signing key — REQUIRED
GEMINI_API_KEY=<key>                   # Primary LLM provider — REQUIRED
DATABASE_URL=postgresql+asyncpg://cortex:cortex@localhost:5432/cortexflow
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=cortexflow
```

### Optional / Defaults
```bash
APP_ENV=development                    # development | staging | production | test
DEBUG=false                            # Enables /docs /redoc /openapi.json
LOG_LEVEL=INFO
RATE_LIMIT_PER_MINUTE=60
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
ALLOWED_ORIGINS=http://localhost:3000
DEEPSEEK_API_KEY=                      # Falls back to Gemini if empty
OLLAMA_BASE_URL=http://localhost:11434
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

---

## DATABASE MODELS QUICK REFERENCE

### User
```python
id: UUID, email: str (unique), hashed_password: str, full_name: str|None
role: str  # "admin" | "developer" | "operator" | "viewer" | "auditor"
is_active: bool, is_verified: bool, tenant_id: str|None
created_at, updated_at, last_login_at: datetime
```

### Agent
```python
id: UUID, name: str, agent_type: str, status: str
# agent_type: "planner" | "executor" | "validator" | "critic" | "memory" | "security" | "observer" | "router" | "generic"
# status: "IDLE" | "PLANNING" | "EXECUTING" | "VALIDATING" | "REFLECTING" | "PAUSED" | "TERMINATED"
trust_score: float (0–1), owner_id: UUID (FK→users), config: JSONB
```

### Workflow
```python
id: UUID, name: str, status: str, version: int
# status: "PENDING" | "RUNNING" | "PAUSED" | "COMPLETED" | "FAILED" | "ROLLED_BACK"
dag_definition: JSONB, checkpoint_data: JSONB
trigger_source: str  # "manual" | "cron" | "webhook" | "event"
owner_id: UUID (FK→users), agent_id: UUID|None (FK→agents)
```

### Task
```python
id: UUID, title: str, description: str, status: str, priority: int (1–10)
risk_score: float (0–100), retry_count: int, max_retries: int
input_data: JSONB, output_data: JSONB, error_data: JSONB
cognitive_stage: str, workflow_id: UUID (FK), agent_id: UUID (FK)
```

---

## CELERY TASK SUBMISSION PATTERN

```python
# Submit to the correct queue based on priority
from app.workers.celery_app import celery_app

# High priority (agent control)
celery_app.send_task("agent.dispatch", args=[agent_id, payload], queue="high_priority_queue")

# Planning tasks
celery_app.send_task("agent.plan", args=[task_id, goal], queue="planning_queue")

# Execution tasks
celery_app.send_task("agent.execute", args=[task_id], queue="execution_queue")

# Background learning (lowest priority)
celery_app.send_task("learning.consolidate", queue="low_priority_queue")
```

---

## TESTING CONVENTIONS

```bash
# Run all tests
cd backend && pytest

# Run with coverage (must pass ≥80%)
pytest --cov=app --cov-report=term-missing

# Run security scan (must be clean)
bandit -r app/ -f screen

# Run specific module tests
pytest tests/unit/test_auth_jwt.py -v
```

### Test File Locations
```
backend/tests/unit/          Unit tests (no external dependencies)
backend/tests/integration/   Integration tests (require running DBs)
```

### Test Patterns
```python
# Use pytest-asyncio for async tests
@pytest.mark.asyncio
async def test_something():
    ...

# Use factory-boy for fixtures
# Use AsyncSession with real PostgreSQL (no mocks — see SKILL rule)
```

---

## SECURITY RULES (NON-NEGOTIABLE)

1. All inputs validated with Pydantic — never trust raw dicts
2. All SQL via SQLAlchemy ORM — never format strings into queries
3. All tool executions go through `ToolRegistry.execute()` — never call handlers directly
4. JWT expires in 15 minutes — never extend without reason
5. Shell + browser tools always run in Docker sandbox — never in raw subprocess for prod
6. All agent actions written to `audit_logs` — immutable, indexed
7. LLM inputs scanned for prompt injection before forwarding
8. Secrets from env vars only — never hardcode in source
9. CORS allowlist only — never use `allow_origins=["*"]` in non-dev
10. `require_role()` dependency on admin-only endpoints

---

## OBSERVABILITY INTEGRATION

### Adding Tracing to a New Function
```python
from app.core.observability.tracing import traced_operation

async with traced_operation("my_module.operation", attributes={"key": "value"}):
    # your code here
```

### Adding Metrics
```python
from app.core.observability.metrics import get_metrics

m = get_metrics()
m.tool_calls_total.labels(tool_name="file.read", status="success").inc()
m.active_agents.labels(agent_type="executor").set(5)
```

### Structured Logging
```python
from app.core.observability.logs import get_logger
logger = get_logger(__name__, agent_id=str(agent_id))

logger.info("operation.complete", result="success", duration_ms=120)
logger.warning("operation.degraded", error="timeout")
logger.error("operation.failed", error=str(exc), trace_id=trace_id)
```

---

## ENTERPRISE FEATURES STATUS

| Feature | Status | Notes |
|---|---|---|
| Multi-tenancy | ✅ | `tenant_id` on User + JWT claims |
| RBAC (5 roles, 30+ perms) | ✅ | Full implementation |
| Human approval gates | ✅ | Risk 86+ auto-blocked |
| Docker sandbox isolation | ✅ | 4 tiers |
| JWT authentication | ✅ | 15min access + 7d refresh |
| Rate limiting | ✅ | 60/min per IP |
| Audit logs | ✅ | Immutable PostgreSQL |
| Prometheus metrics | ✅ | Defined, endpoint stub |
| OpenTelemetry tracing | ✅ | Configured, endpoint stub |
| Structured logging | ✅ | structlog + in-memory buffer |
| Kubernetes manifests | ⚠️ | Scaffolded |
| HashiCorp Vault | ⚠️ | hvac installed, not wired |
| JWT token blacklist | ❌ | Phase 3 |
| Email verification | ❌ | Phase 2 |
| SSO/SAML | ❌ | Phase 3 |
| Multi-region | ❌ | Phase 3 |

---

## QUICK START (LOCAL DEVELOPMENT)

```bash
# 1. Start infrastructure
docker-compose -f deploy/docker-compose.dev.yml up -d

# 2. Install dependencies
cd backend && pip install -r requirements.txt

# 3. Run migrations
alembic upgrade head

# 4. Start API server
uvicorn app.main:app --reload --port 8000

# 5. Start Celery worker (separate terminal)
celery -A app.workers.celery_app worker --loglevel=info \
  -Q planning_queue,execution_queue,validation_queue,reflection_queue,high_priority_queue

# 6. API docs (only available when DEBUG=true)
open http://localhost:8000/docs
```

---

## COMMON GOTCHAS

1. **`db.flush()` vs `db.commit()`** — Use `flush()` inside handlers to get auto-generated IDs. The `get_db()` dependency handles `commit()` after the handler returns successfully.

2. **Neo4j path expressions** — Never use parameterized values in `*min..max` range expressions. Always interpolate as `f"*1..{int(depth)}"`.

3. **Async inside sync** — Never call `asyncio.run()` inside FastAPI handlers or Celery tasks already running in an event loop. Use `await` or `asyncio.run_coroutine_threadsafe`.

4. **Model router at import time** — `model_router = ModelRouter()` at module level means API key env vars must be set before the module is imported.

5. **Qdrant embedding dimension** — All vectors must be exactly 384 dimensions (all-MiniLM-L6-v2 output). Mismatched dims cause Qdrant to reject points silently.

6. **`agent_id` type** — In knowledge graph methods, `agent_id` is `UUID` (Python). In Neo4j, it's stored as `str(agent_id)`. In PostgreSQL columns, it's `UUID(as_uuid=True)`.

7. **Trust scores** — Agent `trust_score` is `float` (0.0–1.0). Tool risk scores are `float` (0–100). Don't confuse the scales.

8. **`is_active == True` in SQLAlchemy** — Always use `== True` with SQLAlchemy (not `is True`) or use `.where(Model.is_active)` directly. The `== True` form generates the correct SQL.

---

*Maintained by [Amit Chandra](https://theamitchandra.github.io/My-Portfolio) | amit.vervebot@gmail.com | Updated: 2026-06-06*
