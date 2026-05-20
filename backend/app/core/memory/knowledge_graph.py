"""Knowledge graph memory backed by Neo4j.

Models relationships between agents, tools, workflows, tasks, and users.
Provides graph-traversal queries that semantic/relational stores cannot.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db.neo4j import get_neo4j_driver


class KnowledgeGraphMemory:
    """Neo4j-backed graph memory for relational knowledge.

    All write operations use ``MERGE`` to be idempotent — re-running the
    same ingestion pipeline does not create duplicate nodes.
    """

    # ------------------------------------------------------------------
    # Node upserts
    # ------------------------------------------------------------------

    async def upsert_agent(self, agent_id: UUID, name: str, agent_type: str) -> None:
        """Create or update an Agent node."""
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                """
                MERGE (a:Agent {id: $id})
                SET a.name = $name, a.type = $type
                """,
                id=str(agent_id),
                name=name,
                type=agent_type,
            )

    async def upsert_workflow(self, workflow_id: UUID, name: str, status: str) -> None:
        """Create or update a Workflow node."""
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                """
                MERGE (w:Workflow {id: $id})
                SET w.name = $name, w.status = $status
                """,
                id=str(workflow_id),
                name=name,
                status=status,
            )

    async def upsert_tool(self, tool_name: str, risk_level: str) -> None:
        """Create or update a Tool node."""
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                """
                MERGE (t:Tool {name: $name})
                SET t.risk_level = $risk_level
                """,
                name=tool_name,
                risk_level=risk_level,
            )

    async def upsert_task(self, task_id: UUID, title: str, status: str) -> None:
        """Create or update a Task node."""
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                """
                MERGE (t:Task {id: $id})
                SET t.title = $title, t.status = $status
                """,
                id=str(task_id),
                title=title,
                status=status,
            )

    async def upsert_user(self, user_id: UUID, email: str, role: str) -> None:
        """Create or update a User node."""
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                """
                MERGE (u:User {id: $id})
                SET u.email = $email, u.role = $role
                """,
                id=str(user_id),
                email=email,
                role=role,
            )

    # ------------------------------------------------------------------
    # Relationship upserts
    # ------------------------------------------------------------------

    async def agent_owns_workflow(self, agent_id: UUID, workflow_id: UUID) -> None:
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                """
                MATCH (a:Agent {id: $agent_id}), (w:Workflow {id: $workflow_id})
                MERGE (a)-[:EXECUTES]->(w)
                """,
                agent_id=str(agent_id),
                workflow_id=str(workflow_id),
            )

    async def agent_uses_tool(
        self, agent_id: UUID, tool_name: str, count: int = 1
    ) -> None:
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                """
                MATCH (a:Agent {id: $agent_id}), (t:Tool {name: $tool_name})
                MERGE (a)-[r:USES]->(t)
                ON CREATE SET r.count = $count
                ON MATCH  SET r.count = r.count + $count
                """,
                agent_id=str(agent_id),
                tool_name=tool_name,
                count=count,
            )

    async def workflow_contains_task(
        self, workflow_id: UUID, task_id: UUID
    ) -> None:
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                """
                MATCH (w:Workflow {id: $workflow_id}), (t:Task {id: $task_id})
                MERGE (w)-[:CONTAINS]->(t)
                """,
                workflow_id=str(workflow_id),
                task_id=str(task_id),
            )

    async def task_depends_on(self, task_id: UUID, depends_on_id: UUID) -> None:
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                """
                MATCH (t:Task {id: $task_id}), (d:Task {id: $depends_on_id})
                MERGE (t)-[:DEPENDS_ON]->(d)
                """,
                task_id=str(task_id),
                depends_on_id=str(depends_on_id),
            )

    async def agent_learns_from_feedback(
        self, agent_id: UUID, feedback_id: UUID, score: float
    ) -> None:
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                """
                MATCH (a:Agent {id: $agent_id})
                MERGE (f:Feedback {id: $feedback_id})
                ON CREATE SET f.score = $score
                MERGE (a)-[:LEARNS_FROM]->(f)
                """,
                agent_id=str(agent_id),
                feedback_id=str(feedback_id),
                score=score,
            )

    async def user_owns_agent(self, user_id: UUID, agent_id: UUID) -> None:
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                """
                MATCH (u:User {id: $user_id}), (a:Agent {id: $agent_id})
                MERGE (u)-[:OWNS]->(a)
                """,
                user_id=str(user_id),
                agent_id=str(agent_id),
            )

    async def agent_communicates_with(
        self, source_id: UUID, target_id: UUID
    ) -> None:
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                """
                MATCH (s:Agent {id: $source_id}), (t:Agent {id: $target_id})
                MERGE (s)-[:COMMUNICATES_WITH]->(t)
                """,
                source_id=str(source_id),
                target_id=str(target_id),
            )

    # ------------------------------------------------------------------
    # Graph queries
    # ------------------------------------------------------------------

    async def get_agent_tools(self, agent_id: UUID) -> list[dict[str, Any]]:
        """Return all tools used by an agent with usage counts."""
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (a:Agent {id: $agent_id})-[r:USES]->(t:Tool)
                RETURN t.name AS name, t.risk_level AS risk_level, r.count AS count
                ORDER BY r.count DESC
                """,
                agent_id=str(agent_id),
            )
            return [dict(record) async for record in result]

    async def get_workflow_graph(
        self, workflow_id: UUID
    ) -> list[dict[str, Any]]:
        """Return the full task dependency graph for a workflow."""
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (w:Workflow {id: $workflow_id})-[:CONTAINS]->(t:Task)
                OPTIONAL MATCH (t)-[:DEPENDS_ON]->(dep:Task)
                RETURN t.id AS task_id, t.title AS title, t.status AS status,
                       collect(dep.id) AS depends_on
                """,
                workflow_id=str(workflow_id),
            )
            return [dict(record) async for record in result]

    async def get_collaborating_agents(
        self, agent_id: UUID, depth: int = 2
    ) -> list[dict[str, Any]]:
        """Return agents reachable from *agent_id* via COMMUNICATES_WITH edges."""
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH path = (a:Agent {id: $agent_id})-[:COMMUNICATES_WITH*1..$depth]->(other:Agent)
                RETURN DISTINCT other.id AS id, other.name AS name, other.type AS type,
                               length(path) AS hops
                ORDER BY hops
                """,
                agent_id=str(agent_id),
                depth=depth,
            )
            return [dict(record) async for record in result]

    async def get_high_risk_tools(
        self, min_usage: int = 1
    ) -> list[dict[str, Any]]:
        """Return tools with risk_level='high' or 'critical' and their using agents."""
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (a:Agent)-[r:USES]->(t:Tool)
                WHERE t.risk_level IN ['high', 'critical'] AND r.count >= $min_usage
                RETURN t.name AS tool, t.risk_level AS risk_level,
                       collect(a.id) AS agent_ids, sum(r.count) AS total_uses
                ORDER BY total_uses DESC
                """,
                min_usage=min_usage,
            )
            return [dict(record) async for record in result]

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    async def delete_agent_graph(self, agent_id: UUID) -> None:
        """Remove the Agent node and all its relationships."""
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run(
                "MATCH (a:Agent {id: $id}) DETACH DELETE a",
                id=str(agent_id),
            )
