"""Root conftest — adds the backend directory to sys.path so that
``import app.*`` works from any test file without installing the package.
Also seeds required environment variables so that pydantic-settings can
initialise ``Settings`` during test collection without a real .env file.
"""
import os
import sys
from pathlib import Path

# Seed required env vars BEFORE any app module is imported during collection.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/cortexflow_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "test-password")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")

# Insert backend/ at the front of sys.path
sys.path.insert(0, str(Path(__file__).parent))
