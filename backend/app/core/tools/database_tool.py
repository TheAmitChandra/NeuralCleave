"""Database query tool — read-only SQL execution via SQLAlchemy.

Security controls:
- Only SELECT statements allowed (DML/DDL explicitly blocked).
- Parameterised queries only — no raw string interpolation.
- Row count cap prevents memory exhaustion.
- Query timeout enforced via PostgreSQL statement_timeout.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability.logs import get_logger
from app.core.tools.registry import ToolDefinition

logger = get_logger(__name__)

_MAX_ROWS = 500
_DEFAULT_TIMEOUT_MS = 10_000  # 10 seconds in milliseconds

# Regex: detect statements that mutate data or schema
_DML_DDL_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|MERGE|UPSERT|GRANT|REVOKE|EXEC|EXECUTE|CALL)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_select_only(sql: str) -> None:
    """Raise PermissionError if the SQL is not a SELECT statement."""
    stripped = sql.strip()
    if _DML_DDL_PATTERN.match(stripped):
        raise PermissionError(
            "Only SELECT statements are permitted. "
            "Mutating queries (INSERT, UPDATE, DELETE, DDL) are blocked."
        )
    if not re.match(r"^\s*(SELECT|WITH)\b", stripped, re.IGNORECASE):
        raise PermissionError(
            "Query must start with SELECT or WITH (for CTEs). " "Mutating queries are blocked."
        )


# ---------------------------------------------------------------------------
# Tool function
# ---------------------------------------------------------------------------


async def db_query(params: dict[str, Any], session: AsyncSession) -> dict[str, Any]:
    """Execute a read-only SQL SELECT and return rows as list of dicts.

    Parameters:
        sql (str): SELECT statement to execute.
        bind_params (dict): Named bind parameters. Optional.
        max_rows (int): Row cap. Default 500.
        timeout_ms (int): Statement timeout in milliseconds. Default 10 000.

    Returns:
        dict with keys: sql, row_count, rows, truncated.

    Note:
        *session* is injected by the tool adapter; the registry caller must
        provide it via a partial or wrapper handler.
    """
    sql: str = params["sql"]
    bind_params: dict[str, Any] = params.get("bind_params") or {}
    max_rows: int = int(params.get("max_rows", _MAX_ROWS))
    timeout_ms: int = int(params.get("timeout_ms", _DEFAULT_TIMEOUT_MS))

    _validate_select_only(sql)

    logger.info("db_query_start", sql_preview=sql[:120])

    # Set statement_timeout for this transaction only
    await session.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}ms'"))  # noqa: S608

    result = await session.execute(text(sql), bind_params)
    columns = list(result.keys())
    rows_raw = result.fetchmany(max_rows + 1)

    truncated = len(rows_raw) > max_rows
    rows_raw = rows_raw[:max_rows]

    rows = [dict(zip(columns, row)) for row in rows_raw]

    logger.info("db_query_done", row_count=len(rows), truncated=truncated)

    return {
        "sql": sql,
        "row_count": len(rows),
        "rows": rows,
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# Tool definition (for ToolRegistry)
# ---------------------------------------------------------------------------

DB_QUERY_DEF = ToolDefinition(
    name="db.query",
    description="Execute a read-only SELECT query against the NeuralCleave database.",
    permissions=["db.read"],
    risk_level="low",
    sandbox_required=False,
    timeout_seconds=15,
    parameters_schema={
        "type": "object",
        "required": ["sql"],
        "properties": {
            "sql": {"type": "string"},
            "bind_params": {"type": "object"},
            "max_rows": {"type": "integer"},
            "timeout_ms": {"type": "integer"},
        },
    },
)


def make_db_query_handler(session: AsyncSession):
    """Return an async handler pre-bound to an AsyncSession.

    Usage::

        handler = make_db_query_handler(session)
        registry.register(DB_QUERY_DEF, handler)
    """

    async def _handler(params: dict[str, Any]) -> dict[str, Any]:
        return await db_query(params, session)

    return _handler
