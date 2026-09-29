"""Settings loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


def _list(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = "postgresql://memorybus:memorybus@localhost:5432/memorybus"

    # Public HTTPS base URL, e.g. https://memorybus.example.com
    public_base_url: str = "http://localhost:8000"

    # REST entry point (Muse and other simple clients)
    api_token: str | None = None

    # MCP entry point OAuth (ChatGPT): GitHub OAuth App credentials
    github_client_id: str | None = None
    github_client_secret: str | None = None
    allowed_github_logins: list[str] = field(default_factory=list)
    jwt_signing_key: str | None = None

    # Embeddings (OpenAI-compatible API, SiliconFlow by default)
    embedding_api_key: str | None = None
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "Qwen/Qwen3-VL-Embedding-8B"
    embedding_dimensions: int = 1024
    embedding_timeout_seconds: float = 10.0

    @property
    def oauth_enabled(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)


def load_settings() -> Settings:
    load_dotenv()
    env = os.environ.get
    defaults = Settings()
    return Settings(
        database_url=env("DATABASE_URL", defaults.database_url),
        public_base_url=env("PUBLIC_BASE_URL", defaults.public_base_url).rstrip("/"),
        api_token=env("MEMORYBUS_API_TOKEN") or None,
        github_client_id=env("GITHUB_CLIENT_ID") or None,
        github_client_secret=env("GITHUB_CLIENT_SECRET") or None,
        allowed_github_logins=[x.lower() for x in _list(env("ALLOWED_GITHUB_LOGINS"))],
        jwt_signing_key=env("JWT_SIGNING_KEY") or None,
        embedding_api_key=env("EMBEDDING_API_KEY") or None,
        embedding_base_url=env("EMBEDDING_BASE_URL", defaults.embedding_base_url),
        embedding_model=env("EMBEDDING_MODEL", defaults.embedding_model),
        embedding_dimensions=int(env("EMBEDDING_DIMENSIONS", str(defaults.embedding_dimensions))),
        embedding_timeout_seconds=float(
            env("EMBEDDING_TIMEOUT_SECONDS", str(defaults.embedding_timeout_seconds))
        ),
    )
