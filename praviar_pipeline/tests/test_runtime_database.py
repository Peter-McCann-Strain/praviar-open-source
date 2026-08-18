from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import OperationalError

from praviar_pipeline.pipeline.runtime import (
    sync_pipeline_to_database as exported_sync_pipeline_to_database,
)
from praviar_pipeline.pipeline.runtime.database import sync_pipeline_to_database
from praviar_pipeline.run import _sync_to_database


def test_runtime_database_sync_skips_without_database_url(monkeypatch):
    captured = []

    def fake_warning(event, **kwargs):
        captured.append((event, kwargs))

    monkeypatch.setattr(
        "praviar_pipeline.pipeline.runtime.database.get_settings",
        lambda: SimpleNamespace(database_url=None),
    )
    monkeypatch.setattr("praviar_pipeline.pipeline.runtime.database.logger.warning", fake_warning)

    sync_pipeline_to_database({"compound": {"name": "aspirin"}}, "aspirin", 1.25)

    assert captured == [("db_sync_skipped", {})]
    assert "DATABASE_URL" not in repr(captured)
    assert ".env" not in repr(captured)


def test_runtime_package_reexports_database_sync():
    assert exported_sync_pipeline_to_database is sync_pipeline_to_database


def test_run_module_reexports_database_sync():
    assert _sync_to_database is sync_pipeline_to_database


def test_database_connection_error_never_logs_dsn_or_customer_structure(monkeypatch):
    sentinel = "database-dsn-and-customer-smiles-sentinel"
    recording_logger = MagicMock()
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.runtime.database.get_settings",
        lambda: SimpleNamespace(database_url=f"postgresql://user:{sentinel}@db/app"),
    )
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.runtime.database.logger",
        recording_logger,
    )

    with patch(
        "sqlalchemy.create_engine",
        side_effect=OSError(f"could not connect using {sentinel}"),
    ):
        sync_pipeline_to_database(
            {"compound": {"name": "private", "canonical_smiles": sentinel}},
            "private",
            1.0,
        )

    for call in recording_logger.method_calls:
        assert sentinel not in repr((call.args, call.kwargs))


def test_compound_upsert_error_never_logs_sql_parameters(monkeypatch):
    sentinel = "compound-upsert-smiles-sentinel"
    recording_logger = MagicMock()
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.runtime.database.get_settings",
        lambda: SimpleNamespace(database_url="postgresql://localhost/app"),
    )
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.runtime.database.logger",
        recording_logger,
    )

    row_result = MagicMock()
    row_result.mappings.return_value.first.return_value = {"id": "user-1", "org_id": "org-1"}
    connection = MagicMock()
    connection.execute.side_effect = [
        row_result,
        MagicMock(),
        OperationalError(
            "INSERT INTO compounds",
            {"smiles": sentinel},
            OSError(f"driver echoed {sentinel}"),
        ),
    ]
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    engine = MagicMock()
    engine.connect.return_value = connection_context

    with patch("sqlalchemy.create_engine", return_value=engine):
        sync_pipeline_to_database(
            {
                "compound": {
                    "name": "private compound",
                    "canonical_smiles": sentinel,
                    "inchi_key": "SAFE-INCHI-KEY",
                }
            },
            "private compound",
            1.0,
        )

    connection.rollback.assert_called_once()
    for call in recording_logger.method_calls:
        assert sentinel not in repr((call.args, call.kwargs))
