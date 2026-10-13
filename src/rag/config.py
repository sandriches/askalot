"""Central configuration, loaded from environment variables / `.env`.

Every setting lives here so the rest of the code never reads `os.environ`
directly. Field names map to env vars case-insensitively, e.g.
`azure_openai_endpoint` <- `AZURE_OPENAI_ENDPOINT`.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Azure OpenAI (via the Foundry resource) ---
    azure_openai_endpoint: str
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_chat_deployment: str = "gpt-5.4-mini"
    # Optional. If unset we authenticate with Entra ID (az login locally,
    # managed identity when deployed) — no secrets in config.
    azure_openai_api_key: SecretStr | None = None

    # --- Document Intelligence (same Foundry resource, cognitiveservices.azure.com host) ---
    azure_docintel_endpoint: str | None = None

    # --- Postgres + pgvector ---
    database_url: str = "postgresql://rag:rag@localhost:5433/rag"

    # --- Paths ---
    data_dir: Path = PROJECT_ROOT / "data"

    @property
    def openai_base_url(self) -> str:
        """Base URL for the OpenAI SDK, using Azure's v1 (OpenAI-compatible) API."""
        return self.azure_openai_endpoint.rstrip("/") + "/openai/v1/"


@lru_cache
def get_settings() -> Settings:
    return Settings()
