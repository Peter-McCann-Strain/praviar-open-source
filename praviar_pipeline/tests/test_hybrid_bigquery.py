"""Focused tests for fail-closed hybrid BigQuery retrieval."""

from __future__ import annotations

import sys
from datetime import date
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.pipeline.search.hybrid_bigquery import (
    _build_hybrid_sql,
    _qualified_table,
    _row_to_canonical_bigquery_row,
    _search_phrase,
    _validated_query_vector,
    search_bigquery_hybrid,
)


class FakeRow(dict):
    """Minimal BigQuery Row-compatible mapping."""


def _fake_row(**overrides) -> FakeRow:
    row = FakeRow(
        publication_number="US1234567B2",
        rrf_score=0.02,
        title="Test patent",
        abstract="Test abstract",
        assignee_harmonized="ACME Corp",
        filing_date=date(2010, 1, 1),
        expiry_date=date(2030, 1, 1),
        jurisdiction="US",
        cpc_codes="A61K31/00",
    )
    row.update(overrides)
    return row


class _BqPatch:
    """Install a small google.cloud.bigquery test module."""

    def __init__(self) -> None:
        self._saved: dict[str, object | None] = {}
        self.scalar_parameter = MagicMock(
            side_effect=lambda name, parameter_type, value: (
                "scalar",
                name,
                parameter_type,
                value,
            )
        )
        self.array_parameter = MagicMock(
            side_effect=lambda name, parameter_type, values: (
                "array",
                name,
                parameter_type,
                values,
            )
        )
        self.job_config = MagicMock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))

    def __enter__(self):
        bq_mod = ModuleType("google.cloud.bigquery")
        bq_mod.ScalarQueryParameter = self.scalar_parameter
        bq_mod.ArrayQueryParameter = self.array_parameter
        bq_mod.QueryJobConfig = self.job_config

        cloud_mod = ModuleType("google.cloud")
        cloud_mod.bigquery = bq_mod
        google_mod = ModuleType("google")
        google_mod.cloud = cloud_mod

        for name, module in (
            ("google", google_mod),
            ("google.cloud", cloud_mod),
            ("google.cloud.bigquery", bq_mod),
        ):
            self._saved[name] = sys.modules.get(name)
            sys.modules[name] = module
        return self

    def __exit__(self, *_args) -> None:
        for name, original in self._saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _settings(maximum_bytes_billed: int = 123456) -> SimpleNamespace:
    return SimpleNamespace(bigquery_max_bytes_billed=maximum_bytes_billed)


def _stub_embed(_text: str) -> list[float]:
    return [0.1, 0.2, 0.3]


class TestHybridSql:
    def test_uses_parameterized_embedding_and_query_terms(self) -> None:
        sql = _build_hybrid_sql(
            "project-1",
            "patents",
            "hybrid_index",
            200,
            60,
            query_term_count=2,
            filter_jurisdictions=True,
        )

        assert "VECTOR_SEARCH" in sql
        assert "@query_embedding" in sql
        assert "SEARCH(patents, @query_term_0)" in sql
        assert "SEARCH(patents, @query_term_1)" in sql
        assert "SCORE()" not in sql
        assert "lexical_score" in sql
        assert "@jurisdictions" in sql
        assert "AS publication_number" in sql

    def test_search_phrase_escapes_reserved_term_characters(self) -> None:
        assert _search_phrase("110-15-6") == '"110-15-6"'
        assert _search_phrase('alpha "beta"') == '"alpha \\"beta\\""'

    def test_omits_jurisdiction_filter_when_scope_is_empty(self) -> None:
        sql = _build_hybrid_sql(
            "project-1",
            "patents",
            "hybrid_index",
            20,
            60,
            query_term_count=1,
            filter_jurisdictions=False,
        )

        assert "@jurisdictions" not in sql

    @pytest.mark.parametrize(
        ("project", "dataset", "table"),
        [
            ("", "patents", "index"),
            ("project`x", "patents", "index"),
            ("project-1", "bad-dataset", "index"),
            ("project-1", "patents", "bad.table"),
        ],
    )
    def test_rejects_untrusted_identifiers(
        self,
        project: str,
        dataset: str,
        table: str,
    ) -> None:
        with pytest.raises(ValueError, match="identifier"):
            _qualified_table(project, dataset, table)


class TestCanonicalRows:
    def test_maps_to_step2_dictionary_contract(self) -> None:
        row = _row_to_canonical_bigquery_row(_fake_row())

        assert row["publication_number"] == "US1234567B2"
        assert row["assignee_harmonized"] == ["ACME Corp"]
        assert row["cpc_codes"] == ["A61K31/00"]
        assert row["filing_date"] == date(2010, 1, 1)
        assert row["expiry_date"] == date(2030, 1, 1)
        assert row["rrf_score"] == pytest.approx(0.02)

    def test_preserves_list_assignees_and_cpc_codes(self) -> None:
        row = _row_to_canonical_bigquery_row(
            _fake_row(
                assignee_harmonized=[{"name": "ACME"}, {"name": "Roche"}],
                cpc_codes=["A61K31/00", "C07D"],
            )
        )

        assert row["assignee_harmonized"] == [
            {"name": "ACME"},
            {"name": "Roche"},
        ]
        assert row["cpc_codes"] == ["A61K31/00", "C07D"]

    def test_missing_publication_number_is_not_silently_skipped(self) -> None:
        with pytest.raises(ValueError, match="publication_number"):
            _row_to_canonical_bigquery_row(_fake_row(publication_number=""))

    @pytest.mark.parametrize("score", [None, "bad", float("nan"), -0.1])
    def test_invalid_rrf_score_fails(self, score: object) -> None:
        with pytest.raises(ValueError, match="rrf_score"):
            _row_to_canonical_bigquery_row(_fake_row(rrf_score=score))


class TestEmbeddingValidation:
    def test_numeric_vector_is_normalized(self) -> None:
        assert _validated_query_vector([1, 2.5]) == [1.0, 2.5]

    @pytest.mark.parametrize("vector", [[], [float("nan")], [float("inf")], [True]])
    def test_invalid_vector_fails_closed(self, vector: list[float]) -> None:
        with pytest.raises(ValueError, match="embedding"):
            _validated_query_vector(vector)


class TestSearchBigQueryHybrid:
    @pytest.mark.asyncio
    async def test_success_returns_canonical_rows_and_parameterizes_scope(self) -> None:
        client = MagicMock()
        client.query_and_wait.return_value = iter([_fake_row(publication_number="US1000001B2")])
        embed_calls: list[str] = []

        def embed(text: str) -> list[float]:
            embed_calls.append(text)
            return [0.1, 0.2, 0.3]

        with _BqPatch() as bq:
            rows = await search_bigquery_hybrid(
                client=client,
                settings=_settings(),
                query_terms=["aspirin", "acetylsalicylic acid", "aspirin"],
                jurisdictions=["us", "EP", "US"],
                project="project-1",
                dataset="patents",
                table="hybrid_index",
                embed_fn=embed,
            )

        assert rows[0]["publication_number"] == "US1000001B2"
        assert isinstance(rows[0], dict)
        assert embed_calls == ["aspirin ; acetylsalicylic acid"]
        client.query_and_wait.assert_called_once()
        sql = client.query_and_wait.call_args.args[0]
        job_config = client.query_and_wait.call_args.kwargs["job_config"]
        assert "0.1" not in sql
        assert job_config.maximum_bytes_billed == 123456
        assert (
            "scalar",
            "query_term_0",
            "STRING",
            '"aspirin"',
        ) in job_config.query_parameters
        assert (
            "array",
            "query_embedding",
            "FLOAT64",
            [0.1, 0.2, 0.3],
        ) in job_config.query_parameters
        assert (
            "array",
            "jurisdictions",
            "STRING",
            ["US", "EP"],
        ) in job_config.query_parameters
        bq.job_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_terms_return_without_client_or_embedding_work(self) -> None:
        client = MagicMock()
        embed = MagicMock()

        with _BqPatch():
            rows = await search_bigquery_hybrid(
                client=client,
                settings=_settings(),
                query_terms=["", "  "],
                jurisdictions=["US"],
                project="project-1",
                dataset="patents",
                table="hybrid_index",
                embed_fn=embed,
            )

        assert rows == []
        embed.assert_not_called()
        client.query_and_wait.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_embedding_schema_fails_without_bm25_retry(self) -> None:
        client = MagicMock()
        client.query_and_wait.side_effect = RuntimeError("Unrecognized name: embedding")

        with _BqPatch():
            with pytest.raises(SourceUnavailableError) as exc_info:
                await search_bigquery_hybrid(
                    client=client,
                    settings=_settings(),
                    query_terms=["aspirin"],
                    jurisdictions=["US"],
                    project="project-1",
                    dataset="patents",
                    table="hybrid_index",
                    embed_fn=_stub_embed,
                )

        assert str(exc_info.value) == "bigquery unavailable: hybrid patent search failed"
        client.query_and_wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_argument_never_launches_alternate_retrieval(self) -> None:
        client = MagicMock()
        client.query_and_wait.side_effect = RuntimeError(
            "INVALID_ARGUMENT: vector dimension mismatch"
        )

        with _BqPatch():
            with pytest.raises(SourceUnavailableError):
                await search_bigquery_hybrid(
                    client=client,
                    settings=_settings(),
                    query_terms=["aspirin"],
                    jurisdictions=None,
                    project="project-1",
                    dataset="patents",
                    table="hybrid_index",
                    embed_fn=_stub_embed,
                )

        client.query_and_wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_malformed_result_row_becomes_source_failure(self) -> None:
        client = MagicMock()
        client.query_and_wait.return_value = iter([_fake_row(publication_number="")])

        with _BqPatch():
            with pytest.raises(SourceUnavailableError):
                await search_bigquery_hybrid(
                    client=client,
                    settings=_settings(),
                    query_terms=["aspirin"],
                    jurisdictions=["US"],
                    project="project-1",
                    dataset="patents",
                    table="hybrid_index",
                    embed_fn=_stub_embed,
                )

    @pytest.mark.asyncio
    async def test_invalid_embedding_fails_before_bigquery_call(self) -> None:
        client = MagicMock()

        with _BqPatch():
            with pytest.raises(SourceUnavailableError):
                await search_bigquery_hybrid(
                    client=client,
                    settings=_settings(),
                    query_terms=["aspirin"],
                    jurisdictions=["US"],
                    project="project-1",
                    dataset="patents",
                    table="hybrid_index",
                    embed_fn=lambda _text: [float("nan")],
                )

        client.query_and_wait.assert_not_called()
