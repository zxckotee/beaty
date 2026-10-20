import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://beaty:beaty@localhost:5432/beaty")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "test-key")
os.environ.setdefault("JWT_SECRET", "test-jwt")
