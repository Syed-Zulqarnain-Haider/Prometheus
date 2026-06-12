"""Test configuration.

Sets safe placeholder env vars BEFORE the app/config modules are imported, so
tests that don't touch a real database can still import the application. The
DSN is parsed but never connected to in these scaffold tests.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("ENV", "test")
