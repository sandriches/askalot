"""Step 0: check that config, the database and both Azure model deployments work.

uv run python scripts/00_check_setup.py
"""

import sys
from collections.abc import Callable

import psycopg

from rag.clients import get_openai_client
from rag.config import get_settings


def check_config() -> str:
    s = get_settings()
    auth = "API key" if s.azure_openai_api_key else "Entra ID (az login)"
    return f"endpoint={s.azure_openai_endpoint} auth={auth}"


def check_database() -> str:
    with psycopg.connect(get_settings().database_url, connect_timeout=3) as conn:
        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
    if row is None:
        raise RuntimeError("connected, but the pgvector extension is not installed")
    return f"pgvector {row[0]}"


def check_embedding() -> str:
    s = get_settings()
    resp = get_openai_client().embeddings.create(
        model=s.azure_openai_embedding_deployment,
        input="Het spoor moet voldoen aan de geluidseisen.",
    )
    return f"{s.azure_openai_embedding_deployment}: {len(resp.data[0].embedding)} dimensions"


def check_chat() -> str:
    s = get_settings()
    resp = get_openai_client().responses.create(
        model=s.azure_openai_chat_deployment,
        input="Antwoord met precies één woord: wat is de hoofdstad van Nederland?",
    )
    return f"{s.azure_openai_chat_deployment}: {resp.output_text.strip()!r}"


CHECKS: list[tuple[str, Callable[[], str], str]] = [
    ("config", check_config, "copy .env.example to .env and fill it in"),
    ("database", check_database, "is Docker running? then: docker compose up -d"),
    ("embedding", check_embedding, "check the deployment name, role assignment, and az login"),
    ("chat", check_chat, "check the deployment name, role assignment, and az login"),
]


def main() -> int:
    failed = 0
    for name, check, hint in CHECKS:
        try:
            print(f"  OK    {name:<10} {check()}")
        except Exception as e:  # noqa: BLE001 - report every failure, keep going
            failed += 1
            print(f"  FAIL  {name:<10} {type(e).__name__}: {e}\n        hint: {hint}")
    print("\nAll checks passed." if not failed else f"\n{failed} check(s) failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
