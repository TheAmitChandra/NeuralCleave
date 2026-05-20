<div align="center">

<!-- Logo -->
<img src="cortexflow.png" alt="CortexFlow Banner" width="100%" />

<br/>

# ⚡ CortexFlow

### Autonomous Cognitive Operating System for AI Agents

<br/>

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14+-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-Native-326CE5?style=for-the-badge&logo=kubernetes&logoColor=white)](https://kubernetes.io)

<br/>

[![CI](https://img.shields.io/github/actions/workflow/status/TheAmitChandra/CortexFlow/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/TheAmitChandra/CortexFlow/actions)
[![Coverage](https://img.shields.io/badge/coverage-80%25+-brightgreen?style=flat-square)](https://github.com/TheAmitChandra/CortexFlow)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](CONTRIBUTING.md)
[![Stars](https://img.shields.io/github/stars/TheAmitChandra/CortexFlow?style=flat-square)](https://github.com/TheAmitChandra/CortexFlow/stargazers)

<br/>

> **"The Kubernetes for Autonomous AI Agents."**

<br/>

[🚀 Get Started](#-quick-start) · [📖 Documentation](#-documentation) · [🏗️ Architecture](#️-architecture) · [🧩 Modules](#-core-modules) · [🔒 Security](#-security) · [🤝 Contributing](#-contributing)

</div>

---

## 📌 What is CortexFlow?

CortexFlow is a **next-generation autonomous cognitive operating system** built to orchestrate intelligent AI agents at enterprise scale. It is not a chatbot. It is not a prompt wrapper. It is a **production-grade cognitive infrastructure platform**.

Where existing AI agent frameworks fall short — weak sandboxing, primitive memory, chaotic workflows, no governance — CortexFlow provides a **complete, secure, observable, deterministic runtime** for autonomous AI operations.

```
Traditional AI Systems          CortexFlow
━━━━━━━━━━━━━━━━━━━━━          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Prompt → Response        →     Input → Cognition → Safe Execution → Memory → Learning
Stateless                →     Persistent Intelligence Runtime
Prompt-driven            →     Deterministic DAG Orchestration
Single model             →     Multi-model Routing & Cost Optimization
No sandboxing            →     Zero-Trust Execution + Docker Isolation
No observability         →     Prometheus + OpenTelemetry + Audit Logs
No governance            →     RBAC + Approval Chains + Policy Engine
No learning              →     Reinforcement-based Behavioral Optimization
```

---

## ✨ Key Features

<table>
<tr>
<td width="50%">

### 🧠 Cognitive Architecture
- 11-stage structured cognitive pipeline
- Intent → Decomposition → Planning → Execution → Reflection
- Hallucination detection & multi-agent consensus
- Persistent agent sessions across restarts

</td>
<td width="50%">

### 🔒 Zero-Trust Security
- Risk-scored execution pipeline (0–100)
- Docker sandbox isolation for every tool call
- Prompt injection defense (pattern + LLM-based)
- Human approval layer for critical actions

</td>
</tr>
<tr>
<td width="50%">

### 🗄️ 4-Tier Memory System
- **Short-term**: Redis (active context, TTL-based)
- **Semantic**: Qdrant (vector search + reranking)
- **Episodic**: PostgreSQL (workflow history)
- **Knowledge Graph**: Neo4j (entity relationships)

</td>
<td width="50%">

### ⚙️ Deterministic Workflows
- DAG-based execution via Celery
- Checkpoint persistence & rollback
- Parallel execution for independent tasks
- Workflow versioning & diff inspection

</td>
</tr>
<tr>
<td width="50%">

### 👥 Multi-Agent Orchestration
- 8 specialized agent types (Planner, Router, Executor, Validator, Critic, Memory, Security, Observer)
- Redis pub/sub event bus
- Trust-scored agent identities
- Cross-node distributed coordination

</td>
<td width="50%">

### 📊 Enterprise Observability
- Prometheus metrics (token usage, costs, latency)
- OpenTelemetry distributed tracing
- Live agent execution graph (React Flow)
- Full immutable audit log trail

</td>
</tr>
<tr>
<td width="50%">

### 🤖 Adaptive Learning
- Reinforcement-based behavioral optimization
- Failure pattern detection
- Workflow outcome prediction
- Execution quality scoring

</td>
<td width="50%">

### 🌐 Model-Agnostic Routing
- Primary: Gemini Pro/Flash
- Secondary: DeepSeek Coder
- Local: Ollama (offline/air-gapped)
- Automatic fallback chain + cost budgeting

</td>
</tr>
</table>

---

## 🏗️ Architecture

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Frontend Dashboard                              │
│                    Next.js · shadcn/ui · React Flow                     │
│         Dashboard │ Agents │ Workflows │ Memory │ Security │ Observ.    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ REST / WebSocket
┌────────────────────────────────▼────────────────────────────────────────┐
│                           API Gateway                                    │
│                    FastAPI · JWT Auth · Rate Limiting                   │
│              /api/v1/agents  /workflows  /memory  /tools  /auth         │
└──────────────┬─────────────────┬──────────────────┬─────────────────────┘
               │                 │                  │
┌──────────────▼──┐  ┌───────────▼──────┐  ┌────────▼────────────────────┐
│  Agent Runtime  │  │  Workflow Engine  │  │      Event Engine           │
│  Lifecycle Mgmt │  │  DAG Execution   │  │  Cron │ Webhook │ GitHub     │
│  Heartbeats     │  │  Checkpoints     │  │  Email │ DB │ Monitoring     │
└──────────────┬──┘  └───────────┬──────┘  └────────┬────────────────────┘
               │                 │                  │
┌──────────────▼─────────────────▼──────────────────▼─────────────────────┐
│                        Orchestration Layer                               │
│                                                                          │
│  PlannerAgent  │  RouterAgent  │  ExecutorAgent  │  ValidatorAgent      │
│  CriticAgent   │  MemoryAgent  │  SecurityAgent  │  ObserverAgent       │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────┐
│                  Zero-Trust Security Pipeline                             │
│                                                                           │
│   Input → Risk Analysis → Policy Check → Permission → Sandbox → Execute │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
┌────────────────┬──────────────────▼──────────────────┬───────────────────┐
│                │      Intelligence Layer               │                  │
│    Gemini Pro  │   DeepSeek Coder  │   Ollama Local   │  sentence-trans. │
└────────────────┴──────────────────┴──────────────────┴───────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────┐
│                          Tool System                                      │
│   Browser(Playwright) │ Files │ Shell(sandboxed) │ APIs │ DB │ ML Tools │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
┌──────────────┬────────────────────▼──────────┬────────────────────────────┐
│  PostgreSQL  │         Qdrant                │  Neo4j        │   Redis    │
│  Relational  │     Vector Memory             │  Knowledge    │   Cache +  │
│  Episodic    │     Semantic Search           │  Graph        │   Broker   │
└──────────────┴───────────────────────────────┴───────────────┴────────────┘
```

---

### Cognitive Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    11-Stage Cognitive Pipeline                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. INPUT RECEPTION      Validate · Sanitize · Classify          │
│          │                                                       │
│  2. INTENT UNDERSTANDING  LLM-based extraction · Structured out │
│          │                                                       │
│  3. TASK DECOMPOSITION    Break into atomic subtasks · Build DAG │
│          │                                                       │
│  4. MEMORY RETRIEVAL      Semantic + Episodic + Graph lookup     │
│          │                                                       │
│  5. PLANNING              Generate plan · Select tools           │
│          │                                                       │
│  6. RISK ANALYSIS         Score each action · Flag high-risk ops │
│          │                                                       │
│  7. TOOL SELECTION        Match tools to task + permissions      │
│          │                                                       │
│  8. EXECUTION             Run in sandbox · Collect results       │
│          │                                                       │
│  9. VALIDATION            Verify results · Consensus check       │
│          │                                                       │
│ 10. REFLECTION            Score quality · Detect hallucinations  │
│          │                                                       │
│ 11. MEMORY CONSOLIDATION  Store outcomes · Update embeddings     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### Multi-Agent Coordination Flow

```
User Request
     │
     ▼
┌─────────────┐     decomposes     ┌──────────────────────────┐
│ PlannerAgent│ ─────────────────► │   Task Graph (DAG)       │
└─────────────┘                    └─────────┬────────────────┘
                                             │ assigns
                                             ▼
                                    ┌─────────────────┐
                                    │   RouterAgent   │
                                    └────────┬────────┘
                            ┌───────────────┼───────────────┐
                            ▼               ▼               ▼
                     ┌────────────┐ ┌────────────┐ ┌────────────┐
                     │ Executor 1 │ │ Executor 2 │ │ Executor 3 │
                     └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
                            └───────────────┼───────────────┘
                                            │ results
                                            ▼
                                   ┌─────────────────┐
                                   │ ValidatorAgent  │
                                   └────────┬────────┘
                                            │ verified
                                            ▼
                                   ┌─────────────────┐
                                   │   CriticAgent   │
                                   └────────┬────────┘
                                            │ reviewed
                                            ▼
                                   ┌─────────────────┐
                                   │  MemoryAgent    │ ◄── SecurityAgent monitors
                                   └─────────────────┘ ◄── ObserverAgent tracks
```

---

### Security Pipeline

```
Every Tool Execution

  Tool Call Request
        │
        ▼
  ┌─────────────────┐
  │ Schema Validate │  ← Pydantic validation
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ Permission Check│  ← Agent scope verification
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │  Risk Scoring   │  ← 0–100 score calculation
  └────────┬────────┘
           │
     ┌─────┴──────┐
  Score < 60   Score ≥ 60
     │             │
     ▼             ▼
  ┌──────┐   ┌──────────────┐
  │ Low  │   │ Policy Check │
  │ ISO  │   └──────┬───────┘
  └──┬───┘          │
     │         Score ≥ 86
     │              │
     │              ▼
     │        ┌───────────────┐
     │        │Human Approval │  ← Operator must approve
     │        └──────┬────────┘
     │               │
     └───────────────┘
                │
                ▼
        ┌───────────────┐
        │Sandbox Alloc. │  ← Docker container
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │   EXECUTE     │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │ Audit Log     │  ← Immutable record
        └───────────────┘
```

---

## 🧩 Core Modules

| # | Module | Branch | Status |
|---|--------|--------|--------|
| 1 | [Agent Runtime](#1-agent-runtime) | `feature/agent-runtime` | 🔲 Planned |
| 2 | [Multi-Agent Orchestration](#2-multi-agent-orchestration) | `feature/multi-agent-orchestration` | 🔲 Planned |
| 3 | [Memory Architecture](#3-memory-architecture) | `feature/memory-system` | 🔲 Planned |
| 4 | [Workflow Engine](#4-workflow-engine) | `feature/workflow-engine` | 🔲 Planned |
| 5 | [Security Architecture](#5-security-architecture) | `feature/security` | 🔲 Planned |
| 6 | [Tool Execution System](#6-tool-execution-system) | `feature/tool-system` | 🔲 Planned |
| 7 | [Reflection Engine](#7-reflection-engine) | `feature/reflection-engine` | 🔲 Planned |
| 8 | [Event System](#8-event-system) | `feature/event-system` | 🔲 Planned |
| 9 | [Adaptive Learning](#9-adaptive-learning) | `feature/adaptive-learning` | 🔲 Planned |
| 10 | [Observability](#10-observability) | `feature/observability` | 🔲 Planned |
| 11 | [Model Router](#11-model-router) | `feature/model-router` | 🔲 Planned |
| 12 | [Governance & Policy](#12-governance--policy) | `feature/governance` | 🔲 Planned |

### 1. Agent Runtime
The heart of CortexFlow. Each agent runs a persistent autonomous execution loop, survives crashes and restarts, and maintains full context awareness.

```python
async def run(self):
    while not self.task_completed:
        context  = await self.memory.retrieve()
        plan     = await self.planner.generate(context)
        action   = await self.executor.execute(plan)
        result   = await self.validator.verify(action)
        await self.memory.store(result)
        await self.reflection.review(result)
```

**States:** `IDLE → PLANNING → EXECUTING → VALIDATING → REFLECTING → PAUSED → TERMINATED`

---

### 2. Multi-Agent Orchestration
Eight specialized agent types work in coordination through a Redis pub/sub event bus.

| Agent | Class | Responsibility |
|---|---|---|
| Planner | `PlannerAgent` | Decomposes tasks into DAG subtask graphs |
| Router | `RouterAgent` | Assigns subtasks to optimal worker agents |
| Executor | `ExecutorAgent` | Executes actions via the tool system |
| Validator | `ValidatorAgent` | Verifies action correctness + consensus |
| Critic | `CriticAgent` | Reviews output quality, flags issues |
| Memory | `MemoryAgent` | Manages all memory tier operations |
| Security | `SecurityAgent` | Monitors risks, enforces policies |
| Observer | `ObserverAgent` | Tracks runtime state, feeds metrics |

---

### 3. Memory Architecture
A 4-tier hierarchical memory system designed for long-running agent sessions.

```
┌─────────────────────────────────────────────────────────┐
│                    Memory Tiers                          │
├────────────────┬─────────────┬─────────────┬────────────┤
│  SHORT-TERM    │  SEMANTIC   │  EPISODIC   │  GRAPH     │
│  Redis         │  Qdrant     │  PostgreSQL │  Neo4j     │
│  TTL: 1 hour   │  Vectors    │  History    │  Relations │
│  Active ctx    │  Embeddings │  Workflows  │  Entities  │
└────────────────┴─────────────┴─────────────┴────────────┘
```

Retrieval pipeline: `Query → Embedding → ANN Search → Reranking → Hybrid Merge → Assembly`

---

### 4. Workflow Engine
DAG-based deterministic execution using Celery. Every workflow is versionable, checkpointed, and rollback-capable.

```
PENDING → RUNNING → VALIDATING → REFLECTING → COMPLETED
                │
                └──► FAILED → RETRYING (×3) → ROLLED_BACK
```

---

### 5. Security Architecture
Zero-trust by design. No action executes without passing through the full security pipeline.

- **Execution Isolation:** Low (shared) → Medium (ephemeral Docker) → High (network-isolated) → Critical (human approval)
- **Prompt Injection Defense:** Pattern matching + LLM-based adversarial analysis
- **Secret Management:** HashiCorp Vault + short-lived scoped tokens
- **Audit Trail:** Every action logged immutably with agent ID + trace ID

---

### 6. Tool Execution System
A registry-based tool system where every tool declares its permissions, risk level, and isolation requirements.

```json
{
  "name": "browser.navigate",
  "permissions": ["web_access"],
  "risk_level": "medium",
  "requires_approval": false,
  "sandbox_required": true,
  "allowed_domains": ["*.example.com"]
}
```

**Tool Categories:** `browser.*` · `file.*` · `shell.*` · `api.*` · `db.*` · `ml.*` · `comms.*`

---

### 7. Reflection Engine
Continuously evaluates agent behavior, detects hallucinations, scores execution quality, and drives adaptive improvement.

- Execution quality scoring (0–100)
- Hallucination detection via confidence thresholding
- Retry strategy recommendations: `retry | rethink | escalate`
- Feeds the adaptive learning system

---

### 8. Event System
CortexFlow is fully event-driven. Agents can be triggered by any external or internal event.

| Trigger Source | Technology | Example |
|---|---|---|
| Email | IMAP / Gmail API | New inbox message |
| GitHub | Webhooks | PR opened or merged |
| Database | PostgreSQL LISTEN/NOTIFY | Row inserted/updated |
| Webhook | FastAPI endpoint | External system event |
| Cron | Celery Beat | Scheduled recurring job |
| Monitoring | Prometheus Alertmanager | Infrastructure alert |

---

### 9. Adaptive Learning
Agents improve over time through reinforcement-based behavioral optimization.

```
Action → Execution → Outcome → Feedback Score → Reward Calculation
    → Behavior Weight Update → Future Actions Influenced
```

---

### 10. Observability
Full enterprise visibility stack — no black boxes.

- **Prometheus** — metrics: token usage, API costs, execution times, memory pressure
- **OpenTelemetry** — distributed traces across all agents and tools
- **Live Agent Graph** — React Flow visualization of active agent network
- **Audit Logs** — immutable record of every tool execution and approval

---

### 11. Model Router
Intelligent routing to the right model for each task type, with automatic fallback and cost budgeting.

```
Task Type              Model Selected
─────────────────────  ──────────────────────────────
Complex reasoning   →  Gemini Pro
Code generation     →  DeepSeek Coder
Summarization       →  Gemini Flash
Embeddings          →  sentence-transformers (local)
Cheap inference     →  Ollama (local)

Fallback chain:  Gemini → DeepSeek → Ollama → Degraded Mode
```

---

### 12. Governance & Policy
Enterprise-grade governance with RBAC, dynamic policy engine, and escalation chains.

**RBAC Roles:** `admin | developer | operator | viewer | auditor`

**Escalation Chain:**
```
Risk Score 61–85  →  Operator notified (15 min SLA)
Risk Score 86–100 →  Admin notified (5 min SLA)
Policy Violation  →  Security Auditor (immediate)
```

---

## 🛠️ Technology Stack

<table>
<tr>
<th>Layer</th>
<th>Technology</th>
<th>Purpose</th>
</tr>
<tr>
<td rowspan="6"><b>Backend</b></td>
<td><img src="https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white" /></td>
<td>Main API gateway, REST + WebSocket</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/Python%203.12-3776AB?style=flat&logo=python&logoColor=white" /></td>
<td>Core runtime, AsyncIO</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/Celery-37814A?style=flat&logo=celery&logoColor=white" /></td>
<td>Distributed task queue, DAG execution</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white" /></td>
<td>Message broker, short-term memory, cache</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/SQLAlchemy-D71F00?style=flat&logo=sqlalchemy&logoColor=white" /></td>
<td>Async ORM for PostgreSQL</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/Pydantic-E92063?style=flat&logo=pydantic&logoColor=white" /></td>
<td>Data validation, settings, schemas</td>
</tr>
<tr>
<td rowspan="5"><b>Frontend</b></td>
<td><img src="https://img.shields.io/badge/Next.js%2014-000000?style=flat&logo=nextdotjs&logoColor=white" /></td>
<td>App Router, SSR, command center UI</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/Tailwind%20CSS-06B6D4?style=flat&logo=tailwindcss&logoColor=white" /></td>
<td>Styling</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/shadcn/ui-000000?style=flat&logo=shadcnui&logoColor=white" /></td>
<td>UI component library</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/React%20Flow-FF4154?style=flat&logo=react&logoColor=white" /></td>
<td>Live agent graph visualization</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/Zustand-000000?style=flat&logo=react&logoColor=white" /></td>
<td>State management</td>
</tr>
<tr>
<td rowspan="5"><b>AI & ML</b></td>
<td><img src="https://img.shields.io/badge/Gemini%20API-4285F4?style=flat&logo=google&logoColor=white" /></td>
<td>Primary reasoning model</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/DeepSeek-0B0B0B?style=flat&logoColor=white" /></td>
<td>Code generation, secondary LLM</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/Ollama-000000?style=flat&logoColor=white" /></td>
<td>Local inference, air-gapped mode</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/HuggingFace-FFD21E?style=flat&logo=huggingface&logoColor=black" /></td>
<td>sentence-transformers, embeddings</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/LlamaIndex-7C3AED?style=flat&logoColor=white" /></td>
<td>RAG pipelines</td>
</tr>
<tr>
<td rowspan="4"><b>Databases</b></td>
<td><img src="https://img.shields.io/badge/PostgreSQL%2016-4169E1?style=flat&logo=postgresql&logoColor=white" /></td>
<td>Relational data, episodic memory, event store</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/Qdrant-DC244C?style=flat&logoColor=white" /></td>
<td>Vector search, semantic memory</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/Neo4j-4581C3?style=flat&logo=neo4j&logoColor=white" /></td>
<td>Knowledge graph memory</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white" /></td>
<td>Cache, session store, pub/sub</td>
</tr>
<tr>
<td rowspan="5"><b>Infrastructure</b></td>
<td><img src="https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white" /></td>
<td>Containerization, sandbox execution</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/Kubernetes-326CE5?style=flat&logo=kubernetes&logoColor=white" /></td>
<td>Production orchestration, autoscaling</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/Prometheus-E6522C?style=flat&logo=prometheus&logoColor=white" /></td>
<td>Metrics collection & alerting</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/OpenTelemetry-000000?style=flat&logo=opentelemetry&logoColor=white" /></td>
<td>Distributed tracing</td>
</tr>
<tr>
<td><img src="https://img.shields.io/badge/GitHub%20Actions-2088FF?style=flat&logo=githubactions&logoColor=white" /></td>
<td>CI/CD pipeline</td>
</tr>
</table>

---

## 🚀 Quick Start

### Prerequisites

- Docker Desktop (with Docker Compose)
- Python 3.12+
- Node.js 20+ with pnpm
- Git

### 1. Clone the repository

```bash
git clone https://github.com/TheAmitChandra/CortexFlow.git
cd CortexFlow
```

### 2. Configure environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` with your credentials:

```env
# Required
GEMINI_API_KEY=your_gemini_api_key_here
SECRET_KEY=your_jwt_secret_here_minimum_32_chars

# Pre-filled for local Docker setup
DATABASE_URL=postgresql+asyncpg://cortex:cortex@localhost:5432/cortexflow
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=cortexflow
ALLOWED_ORIGINS=http://localhost:3000
```

### 3. Start all infrastructure services

```bash
docker-compose -f deploy/docker-compose.dev.yml up -d
```

This starts: PostgreSQL · Qdrant · Neo4j · Redis

### 4. Set up and run the backend

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload --port 8000

# In a separate terminal: start the Celery worker
celery -A app.workers.celery_app worker --loglevel=info -Q planning_queue,execution_queue,validation_queue,reflection_queue,high_priority_queue
```

### 5. Set up and run the frontend

```bash
cd frontend
pnpm install
pnpm dev
```

### 6. Open the dashboard

Navigate to **http://localhost:3000** — you should see the CortexFlow command center.

The API documentation is available at **http://localhost:8000/docs**

---

## 📁 Project Structure

```
CortexFlow/
├── .github/
│   ├── skills/cortexflow/SKILL.md     ← Master knowledge base
│   ├── workflows/                      ← CI/CD pipelines
│   └── AGENTS.md
├── backend/
│   ├── app/
│   │   ├── main.py                     ← FastAPI entry point
│   │   ├── config.py                   ← Settings (pydantic-settings)
│   │   ├── api/v1/                     ← REST API endpoints
│   │   ├── core/
│   │   │   ├── agent_runtime/          ← Module 1: Agent lifecycle
│   │   │   ├── orchestration/          ← Module 2: Multi-agent coordination
│   │   │   ├── memory/                 ← Module 3: 4-tier memory
│   │   │   ├── workflow_engine/        ← Module 4: DAG execution
│   │   │   ├── security/               ← Module 5: Zero-trust
│   │   │   ├── tools/                  ← Module 6: Tool registry
│   │   │   ├── reflection/             ← Module 7: Quality scoring
│   │   │   ├── events/                 ← Module 8: Event bus
│   │   │   ├── learning/               ← Module 9: RL optimization
│   │   │   ├── observability/          ← Module 10: Metrics + tracing
│   │   │   ├── model_router/           ← Module 11: LLM routing
│   │   │   └── governance/             ← Module 12: RBAC + policies
│   │   ├── db/                         ← Database clients + ORM models
│   │   ├── schemas/                    ← Pydantic request/response schemas
│   │   └── workers/                    ← Celery task workers
│   ├── tests/unit/
│   ├── tests/integration/
│   ├── alembic/                        ← DB migration scripts
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── dashboard/                  ← System health overview
│   │   ├── agents/                     ← Agent management
│   │   ├── workflows/                  ← Workflow builder + history
│   │   ├── memory/                     ← Memory explorer
│   │   ├── security/                   ← Approvals + policies
│   │   └── observability/              ← Metrics + audit logs
│   └── components/
├── deploy/
│   ├── docker-compose.yml              ← Production
│   ├── docker-compose.dev.yml          ← Local development
│   └── k8s/                            ← Kubernetes manifests
└── docs/
    ├── IDEA.md                         ← Original vision document
    └── assets/                         ← Images and diagrams
```

---

## 🔒 Security

Security is CortexFlow's primary differentiator. The system is built **zero-trust by design**.

### Non-Negotiable Security Rules

| # | Rule |
|---|------|
| 1 | All user inputs validated with Pydantic schemas before any processing |
| 2 | All tool executions pass through risk analysis pipeline |
| 3 | SQL queries use parameterized queries only — no string interpolation |
| 4 | Secrets stored in environment variables or HashiCorp Vault — never in code |
| 5 | JWT access tokens expire in 15 minutes; refresh tokens in 7 days |
| 6 | Shell and browser tools always sandboxed in Docker containers |
| 7 | Rate limiting enforced on all API endpoints |
| 8 | CORS configured to allowlist only known frontend origins |
| 9 | Every tool execution, approval, and permission change is audit logged |
| 10 | All LLM inputs scanned for prompt injection patterns before sending |
| 11 | HTTPS enforced in production via NGINX TLS termination |
| 12 | No agent can escalate its own permissions |

### Threat Model

CortexFlow explicitly defends against:

- 🎯 Prompt injection & adversarial instructions
- 🧪 Memory poisoning attacks
- 🏃 Sandbox escape attempts
- 🔑 Credential leakage
- ⬆️ Privilege escalation
- 🔀 Adversarial workflow hijacking
- 🚫 Unauthorized API access
- 🕵️ Cross-tenant data access

---

## 📊 Frontend Dashboard

The CortexFlow frontend is a **command center** — not a chat UI.

| Page | URL | Purpose |
|---|---|---|
| Dashboard | `/dashboard` | System health, active agents, recent events |
| Agents | `/agents` | Create, monitor, control, and inspect agents |
| Workflows | `/workflows` | Drag-and-drop DAG builder, execution history |
| Memory Explorer | `/memory` | Search semantic memory, browse knowledge graph |
| Security Center | `/security` | Approval queue, permission manager, policy editor |
| Observability | `/observability` | Live agent graph, metrics, audit logs, traces |
| Settings | `/settings` | API keys, model routing config, integrations |

---

## 🗄️ Database Design

### PostgreSQL Core Tables

```
users           → Authentication and RBAC
agents          → Agent registry and lifecycle state
tasks           → Atomic task units with risk scores
workflows       → DAG definitions (versioned, immutable)
tool_calls      → Every tool execution with full context
reasoning_steps → All 11 cognitive pipeline stages per task
memory_entries  → Episodic memory with Qdrant vector IDs
audit_logs      → Immutable record of all system events
feedback        → Learning signals for adaptive optimization
approvals       → Human-in-the-loop approval records
permissions     → Granular agent permission scopes
cost_ledger     → Per-tenant resource usage and costs
event_store     → Append-only event sourcing log
```

### Knowledge Graph (Neo4j)

```cypher
(:User)-[:OWNS]->(:Agent)
(:Agent)-[:EXECUTES]->(:Workflow)
(:Agent)-[:USES]->(:Tool)
(:Workflow)-[:CONTAINS]->(:Task)
(:Task)-[:DEPENDS_ON]->(:Task)
(:Agent)-[:LEARNS_FROM]->(:Feedback)
(:Agent)-[:COMMUNICATES_WITH]->(:Agent)
```

---

## 🧪 Testing

```bash
# Run all unit tests
cd backend && pytest tests/unit/ -v

# Run integration tests (requires running services)
pytest tests/integration/ -v

# Run with coverage report
pytest tests/ -v --cov=app --cov-report=html

# Security scan
bandit -r app/ -f screen

# Frontend tests
cd frontend && pnpm test
```

**Coverage requirement:** minimum 80% before merging any branch.

---

## 📈 Development Roadmap

```
Phase 1 — Foundation          [🔲 In Progress]
  ├── Project scaffold & FastAPI setup
  ├── PostgreSQL integration + Alembic
  ├── JWT authentication
  ├── Gemini API integration
  └── Frontend dashboard shell

Phase 2 — Memory & Tools      [🔲 Planned]
  ├── Qdrant vector memory
  ├── Neo4j knowledge graph
  ├── Memory retrieval pipeline
  ├── Tool registry
  ├── Browser automation (Playwright)
  └── Workflow engine (DAG)

Phase 3 — Security & Reliability  [🔲 Planned]
  ├── Zero-trust security pipeline
  ├── Sandbox execution
  ├── Prompt injection defense
  ├── Human approval layer
  ├── Reflection engine
  ├── Hallucination mitigation
  └── Observability stack

Phase 4 — Multi-Agent Intelligence  [🔲 Planned]
  ├── All 8 specialized agent types
  ├── Agent communication bus
  └── Distributed orchestration

Phase 5 — Adaptive Learning    [🔲 Planned]
  ├── Feedback loop
  ├── Reinforcement optimizer
  └── Behavioral prediction

Phase 6 — Enterprise Infrastructure  [🔲 Planned]
  ├── Kubernetes deployment
  ├── Autoscaling workers
  ├── Enterprise observability
  └── Multi-tenant isolation
```

---

## ⚔️ CortexFlow vs. The Competition

| Capability | OpenClaw | CrewAI | AutoGen | LangChain | CortexFlow |
|---|:---:|:---:|:---:|:---:|:---:|
| Enterprise Multi-tenancy | ❌ | ❌ | ❌ | ❌ | ✅ |
| Zero-Trust Sandboxing | ❌ | ❌ | ❌ | ❌ | ✅ |
| Deterministic DAG Workflows | ❌ | ⚠️ | ❌ | ⚠️ | ✅ |
| 4-Tier Memory Architecture | ❌ | ❌ | ❌ | ⚠️ | ✅ |
| RBAC + Governance | ❌ | ❌ | ❌ | ❌ | ✅ |
| Hallucination Mitigation | ❌ | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Full Observability Stack | ❌ | ❌ | ❌ | ⚠️ | ✅ |
| Adaptive Learning | ❌ | ❌ | ❌ | ❌ | ✅ |
| Multi-Model Cost Routing | ❌ | ❌ | ⚠️ | ⚠️ | ✅ |
| Human-in-the-Loop UX | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ |
| Air-Gapped Local Mode | ❌ | ❌ | ❌ | ❌ | ✅ |
| Kubernetes-Native Scale | ❌ | ❌ | ❌ | ❌ | ✅ |
| Knowledge Graph Memory | ❌ | ❌ | ❌ | ❌ | ✅ |
| Risk-Scored Execution | ❌ | ❌ | ❌ | ❌ | ✅ |
| MCP Compatibility | ✅ | ❌ | ❌ | ⚠️ | ✅ |

> ✅ Full support · ⚠️ Partial / plugin-based · ❌ Not supported

---

## 🤝 Contributing

CortexFlow follows a strict **branch-per-module** development workflow.

### Workflow

```bash
# 1. Create a feature branch
git checkout -b feature/<module-name>

# 2. Implement the module
# ... write code ...

# 3. Commit immediately after each logical change
git add -A
git commit -m "feat(<scope>): <description>"
git push origin feature/<module-name>

# 4. Run tests (must pass before merge)
pytest tests/ -v --cov=app

# 5. Merge to main after tests pass
git checkout main
git merge feature/<module-name> --no-ff
git push origin main
```

### Commit Format

```
<type>(<scope>): <short description>

Types:  feat | fix | refactor | test | docs | chore | security
Scopes: agent-runtime | memory | workflow | security | tools |
        frontend | db | api | observability | learning
```

### Before Opening a PR

- [ ] Tests pass with ≥ 80% coverage
- [ ] `bandit` security scan clean
- [ ] No secrets in code
- [ ] Branch is up to date with `main`
- [ ] Commit messages follow the format above

---

## 📖 Documentation

| Document | Description |
|---|---|
| [IDEA.md](docs/IDEA.md) | Original vision and full system design |
| [SKILL.md](.github/skills/cortexflow/SKILL.md) | Complete implementation knowledge base |
| [API Docs](http://localhost:8000/docs) | Auto-generated OpenAPI documentation (when running) |

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🚀 Mission

> *"To build the most secure, intelligent, and reliable autonomous cognitive operating system for the next generation of AI-driven automation."*

---

<div align="center">

**CortexFlow** — Built for the AI-native enterprise.

<br/>

[![GitHub](https://img.shields.io/badge/GitHub-TheAmitChandra%2FCortexFlow-181717?style=for-the-badge&logo=github)](https://github.com/TheAmitChandra/CortexFlow)

</div>
