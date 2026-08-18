from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("check-migration-expand-contract.py")
SPEC = importlib.util.spec_from_file_location("migration_expand_contract", SCRIPT)
assert SPEC and SPEC.loader
migration_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = migration_gate
SPEC.loader.exec_module(migration_gate)

PREVIOUS_IMAGE = "registry.example/praviar/api@sha256:" + "a" * 64
SUBJECT_SHA = "b" * 40


def _migration(
    root: Path,
    *,
    body: str,
    down_revision: str | None,
    revision: str,
) -> None:
    rendered_down = "None" if down_revision is None else repr(down_revision)
    (root / f"{revision}_migration.py").write_text(
        "\n".join(
            [
                "from alembic import op",
                "import sqlalchemy as sa",
                f"revision = {revision!r}",
                f"down_revision = {rendered_down}",
                "",
                "def upgrade():",
                *(f"    {line}" for line in body.splitlines()),
                "",
                "def downgrade():",
                "    pass",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    previous = tmp_path / "previous"
    candidate = tmp_path / "candidate"
    previous.mkdir()
    candidate.mkdir()
    _migration(
        previous,
        revision="base",
        down_revision=None,
        body='op.create_table("analyses", sa.Column("id", sa.String(), nullable=False))',
    )
    _migration(
        candidate,
        revision="base",
        down_revision=None,
        body='op.create_table("analyses", sa.Column("id", sa.String(), nullable=False))',
    )
    return previous, candidate


def _custom_introduced_migration(root: Path, module_body: str) -> None:
    (root / "custom_migration.py").write_text(
        "\n".join(
            [
                "from alembic import op",
                "import sqlalchemy as sa",
                "revision = 'custom'",
                "down_revision = 'base'",
                "",
                module_body,
                "",
                "def downgrade():",
                "    pass",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _evidence(previous: Path, candidate: Path) -> dict[str, object]:
    return migration_gate.build_evidence(
        candidate_root=candidate,
        previous_api_image=PREVIOUS_IMAGE,
        previous_root=previous,
        subject_git_sha=SUBJECT_SHA,
    )


def test_additive_nullable_column_emits_digest_bound_n_minus_one_evidence(
    tmp_path: Path,
) -> None:
    previous, candidate = _roots(tmp_path)
    _migration(
        candidate,
        revision="expand",
        down_revision="base",
        body='op.add_column("analyses", sa.Column("release_note", sa.String(), nullable=True))',
    )

    evidence = _evidence(previous, candidate)

    assert evidence["status"] == "pass"
    assert evidence["n_minus_one_head"] == "base"
    assert evidence["candidate_head"] == "expand"
    assert evidence["n_minus_one_api_image"] == PREVIOUS_IMAGE
    assert evidence["subject_git_sha"] == SUBJECT_SHA
    assert evidence["policy"] == {
        "contract_changes_permitted": False,
        "expand_only": True,
        "n_minus_one_schema_compatibility": "expand_only_static",
    }
    introduced = evidence["introduced_migrations"]
    assert isinstance(introduced, list) and len(introduced) == 1
    assert introduced[0]["revision"] == "expand"
    assert len(introduced[0]["sha256"]) == 64


def test_required_column_without_server_default_fails_closed(tmp_path: Path) -> None:
    previous, candidate = _roots(tmp_path)
    _migration(
        candidate,
        revision="bad",
        down_revision="base",
        body='op.add_column("analyses", sa.Column("required", sa.String(), nullable=False))',
    )

    with pytest.raises(
        migration_gate.MigrationSafetyError,
        match="required column lacks a server_default",
    ):
        _evidence(previous, candidate)


def test_batch_nullable_column_is_recognized_as_expand_only(tmp_path: Path) -> None:
    previous, candidate = _roots(tmp_path)
    _migration(
        candidate,
        revision="expand",
        down_revision="base",
        body=(
            'with op.batch_alter_table("analyses") as batch_op:\n'
            '    batch_op.add_column(sa.Column("note", sa.String(), nullable=True))'
        ),
    )

    assert _evidence(previous, candidate)["status"] == "pass"


@pytest.mark.parametrize(
    "body",
    [
        'op.drop_column("analyses", "legacy")',
        'op.alter_column("analyses", "legacy", new_column_name="current")',
        'op.alter_column("analyses", "required", server_default=None)',
        'op.drop_index("ix_analyses_status", table_name="analyses")',
        'op.create_index("uq_users_email", "users", ["email"], unique=True)',
        'op.bulk_insert(sa.table("users"), [{"role": "admin"}])',
        'op.execute("ALTER TABLE analyses DROP COLUMN legacy")',
        'op.execute(sa.text("DELETE FROM analyses"))',
        "op.execute(\"UPDATE users SET role = 'admin'\")",
        "op.execute(\"INSERT INTO users (role) VALUES ('admin')\")",
        'op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")',
        'op.execute("GRANT SELECT ON users TO PUBLIC")',
        'op.execute("CREATE OR REPLACE VIEW users_public AS SELECT * FROM users")',
        'op.execute("CREATE TRIGGER enforce_state BEFORE INSERT ON analyses")',
        (
            "connection = op.get_bind()\n"
            'connection.execute(sa.text("DROP TABLE analyses"))'
        ),
        "op.run_async(lambda connection: None)",
    ],
)
def test_contract_operations_fail_closed(tmp_path: Path, body: str) -> None:
    previous, candidate = _roots(tmp_path)
    _migration(
        candidate,
        revision="bad",
        down_revision="base",
        body=body,
    )

    with pytest.raises(
        migration_gate.MigrationSafetyError,
        match="not expand-only",
    ):
        _evidence(previous, candidate)


def test_dynamic_sql_fails_closed(tmp_path: Path) -> None:
    previous, candidate = _roots(tmp_path)
    _migration(
        candidate,
        revision="bad",
        down_revision="base",
        body=(
            'table = "analyses"\nop.execute(f"UPDATE {table} SET status = \'pending\'")'
        ),
    )

    with pytest.raises(
        migration_gate.MigrationSafetyError,
        match="dynamic op.execute SQL",
    ):
        _evidence(previous, candidate)


def test_recursive_local_helper_is_analyzed(tmp_path: Path) -> None:
    previous, candidate = _roots(tmp_path)
    _custom_introduced_migration(
        candidate,
        "\n".join(
            [
                "def destructive_helper():",
                '    op.execute("DROP TABLE analyses")',
                "",
                "def upgrade():",
                "    destructive_helper()",
            ]
        ),
    )

    with pytest.raises(
        migration_gate.MigrationSafetyError,
        match="raw SQL is forbidden",
    ):
        _evidence(previous, candidate)


def test_recursive_local_additive_helper_is_permitted(tmp_path: Path) -> None:
    previous, candidate = _roots(tmp_path)
    _custom_introduced_migration(
        candidate,
        "\n".join(
            [
                "def add_note():",
                '    op.add_column("analyses", sa.Column("note", sa.String(), nullable=True))',
                "",
                "def upgrade():",
                "    add_note()",
            ]
        ),
    )

    assert _evidence(previous, candidate)["status"] == "pass"


def test_module_level_database_call_fails_closed(tmp_path: Path) -> None:
    previous, candidate = _roots(tmp_path)
    _custom_introduced_migration(
        candidate,
        "\n".join(
            [
                'op.execute("DROP TABLE analyses")',
                "",
                "def upgrade():",
                "    pass",
            ]
        ),
    )

    with pytest.raises(
        migration_gate.MigrationSafetyError,
        match="executable module-level Expr",
    ):
        _evidence(previous, candidate)


def test_import_time_decorator_call_fails_closed(tmp_path: Path) -> None:
    previous, candidate = _roots(tmp_path)
    _custom_introduced_migration(
        candidate,
        "\n".join(
            [
                "def dangerous():",
                "    return lambda function: function",
                "",
                "@dangerous()",
                "def helper():",
                "    pass",
                "",
                "def upgrade():",
                "    pass",
            ]
        ),
    )

    with pytest.raises(
        migration_gate.MigrationSafetyError,
        match="import-time decorators",
    ):
        _evidence(previous, candidate)


def test_import_time_default_call_fails_closed(tmp_path: Path) -> None:
    previous, candidate = _roots(tmp_path)
    _custom_introduced_migration(
        candidate,
        "\n".join(
            [
                "def dangerous():",
                '    op.execute("DROP TABLE analyses")',
                "",
                "def helper(value=dangerous()):",
                "    return value",
                "",
                "def upgrade():",
                "    pass",
            ]
        ),
    )

    with pytest.raises(
        migration_gate.MigrationSafetyError,
        match="defaults must be literal and inert",
    ):
        _evidence(previous, candidate)


def test_unused_arbitrary_import_fails_closed(tmp_path: Path) -> None:
    previous, candidate = _roots(tmp_path)
    _custom_introduced_migration(
        candidate,
        "\n".join(
            [
                "import arbitrary_migration_side_effects",
                "",
                "def upgrade():",
                "    pass",
            ]
        ),
    )

    with pytest.raises(
        migration_gate.MigrationSafetyError,
        match="unproved import",
    ):
        _evidence(previous, candidate)


def test_narrow_type_import_and_inert_annotations_are_permitted(
    tmp_path: Path,
) -> None:
    previous, candidate = _roots(tmp_path)
    _custom_introduced_migration(
        candidate,
        "\n".join(
            [
                "from collections.abc import Sequence",
                "SAFE_LABELS: tuple[str, ...] = ('one', 'two')",
                "",
                "def labels(value: Sequence[str] = ('one',)) -> Sequence[str]:",
                "    return value",
                "",
                "def upgrade():",
                '    op.add_column("analyses", sa.Column("note", sa.String(), nullable=True))',
            ]
        ),
    )

    assert _evidence(previous, candidate)["status"] == "pass"


@pytest.mark.parametrize(
    "module_body",
    [
        "\n".join(
            [
                "from dangerous_migrations import run_migration",
                "",
                "def upgrade():",
                "    run_migration()",
            ]
        ),
        "\n".join(
            [
                "def upgrade():",
                "    operations = op",
                '    operations.drop_table("analyses")',
            ]
        ),
        "\n".join(
            [
                "def upgrade():",
                "    drop = op.drop_table",
                '    drop("analyses")',
            ]
        ),
        "\n".join(
            [
                "def upgrade():",
                '    getattr(op, "drop_table")("analyses")',
            ]
        ),
        "\n".join(
            [
                "from alembic import op as operations",
                "",
                "def upgrade():",
                '    operations.drop_table("analyses")',
            ]
        ),
    ],
)
def test_imported_aliased_and_dynamic_call_paths_fail_closed(
    tmp_path: Path,
    module_body: str,
) -> None:
    previous, candidate = _roots(tmp_path)
    _custom_introduced_migration(candidate, module_body)

    with pytest.raises(
        migration_gate.MigrationSafetyError,
        match="unproved|dynamic callable",
    ):
        _evidence(previous, candidate)


def test_rewritten_n_minus_one_history_fails_closed(tmp_path: Path) -> None:
    previous, candidate = _roots(tmp_path)
    (candidate / "base_migration.py").unlink()
    _migration(
        candidate,
        revision="replacement",
        down_revision=None,
        body='op.create_table("replacement", sa.Column("id", sa.String(), nullable=True))',
    )

    with pytest.raises(
        migration_gate.MigrationSafetyError,
        match="rewrites N-1 history",
    ):
        _evidence(previous, candidate)


def test_modified_n_minus_one_migration_bytes_fail_closed(tmp_path: Path) -> None:
    previous, candidate = _roots(tmp_path)
    candidate_path = candidate / "base_migration.py"
    candidate_path.write_text(
        candidate_path.read_text(encoding="utf-8") + "\n# rewritten\n",
        encoding="utf-8",
    )

    with pytest.raises(
        migration_gate.MigrationSafetyError,
        match="rewrites N-1 history bytes",
    ):
        _evidence(previous, candidate)


def test_cli_writes_canonical_evidence(tmp_path: Path) -> None:
    previous, candidate = _roots(tmp_path)
    output = tmp_path / "evidence" / "migration.json"

    result = migration_gate.main(
        [
            "--previous-versions",
            str(previous),
            "--candidate-versions",
            str(candidate),
            "--previous-api-image",
            PREVIOUS_IMAGE,
            "--subject-git-sha",
            SUBJECT_SHA,
            "--evidence-out",
            str(output),
        ]
    )

    assert result == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "pass"
