"""Neo4j async graph database client."""

from typing import LiteralString

import structlog
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

_driver: AsyncDriver | None = None


async def init_neo4j() -> None:
    global _driver
    _driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        max_connection_pool_size=50,
    )
    await _driver.verify_connectivity()

    # Create uniqueness constraints on first run
    async with _driver.session() as session:
        constraints: list[LiteralString] = [
            "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE CONSTRAINT agent_id IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT workflow_id IF NOT EXISTS FOR (w:Workflow) REQUIRE w.id IS UNIQUE",
            "CREATE CONSTRAINT tool_id IF NOT EXISTS FOR (t:Tool) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT task_id IF NOT EXISTS FOR (t:Task) REQUIRE t.id IS UNIQUE",
        ]
        for cypher in constraints:
            await session.run(cypher)

    logger.info("neo4j_connected", uri=settings.NEO4J_URI)


async def close_neo4j() -> None:
    global _driver
    if _driver:
        await _driver.close()
    logger.info("neo4j_disconnected")


def get_neo4j() -> AsyncDriver:
    global _driver
    if _driver is None:
        raise RuntimeError("Neo4j not initialised — call init_neo4j() first")
    assert _driver is not None
    return _driver


async def get_neo4j_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        await init_neo4j()
    assert _driver is not None
    return _driver
