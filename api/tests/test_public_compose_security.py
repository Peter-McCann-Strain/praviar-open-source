"""Security contracts for the repository's public Docker Compose defaults."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"


def test_all_compose_published_ports_are_loopback_only() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    published_ports = re.findall(
        r'^\s+-\s+"([^"\s]+:\d+)"\s*$',
        compose,
        flags=re.MULTILINE,
    )

    assert published_ports == [
        "127.0.0.1:5432:5432",
        "127.0.0.1:6379:6379",
    ]


def test_compose_is_truthfully_limited_to_local_infrastructure() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    services_block = compose.split("\nvolumes:\n", maxsplit=1)[0]
    service_names = re.findall(
        r"^  ([a-z][a-z0-9_-]+):$",
        services_block,
        flags=re.MULTILINE,
    )
    assert service_names == ["postgres", "redis"]
    assert "env_file:" not in compose
    assert "ALLOW_DEV_AUTH_BYPASS" not in compose
    assert "NEXT_PUBLIC_API_URL" not in compose


def test_deployment_guide_documents_fresh_clone_infrastructure_command() -> None:
    deployment_guide = (REPO_ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    assert "docker compose up --wait postgres redis" in deployment_guide
    assert "unvalidated design note" in deployment_guide
    assert "not part of the quick-start demo" in deployment_guide
    assert "not a supported deployment guide" in deployment_guide
    assert "pnpm@latest" not in deployment_guide
