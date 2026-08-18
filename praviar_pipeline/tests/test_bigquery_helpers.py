from __future__ import annotations

from praviar_pipeline.clients.bigquery_helpers import (
    build_job_config,
    build_scalar_conditions,
    get_cached_result,
    put_cached_result,
    rows_to_dicts,
)


class _FakeScalarQueryParameter:
    def __init__(self, name: str, kind: str, value: str) -> None:
        self.name = name
        self.kind = kind
        self.value = value


class _FakeQueryJobConfig:
    def __init__(self, *, query_parameters, maximum_bytes_billed) -> None:
        self.query_parameters = query_parameters
        self.maximum_bytes_billed = maximum_bytes_billed


class _FakeCache:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.storage = {"search": [{"publication_number": "US1"}]}

    def get(self, key: str, **kwargs):
        self.calls.append(("get", (key,), kwargs))
        return self.storage.get(key)

    def put(self, key: str, results, **kwargs) -> None:
        self.calls.append(("put", (key, results), kwargs))


def test_build_scalar_conditions_creates_conditions_and_parameters() -> None:
    conditions, params = build_scalar_conditions(
        ["A01", "C07"],
        limit=10,
        param_prefix="cpc_prefix",
        condition_builder=lambda param_name: f"c.code LIKE @{param_name}",
        value_builder=lambda code: f"{code}%",
        scalar_query_parameter_cls=_FakeScalarQueryParameter,
    )

    assert conditions == ["c.code LIKE @cpc_prefix_0", "c.code LIKE @cpc_prefix_1"]
    assert [(param.name, param.kind, param.value) for param in params] == [
        ("cpc_prefix_0", "STRING", "A01%"),
        ("cpc_prefix_1", "STRING", "C07%"),
    ]


def test_build_job_config_uses_shared_maximum_bytes_limit() -> None:
    config = build_job_config(
        query_parameters=["param"],
        maximum_bytes_billed=123,
        query_job_config_cls=_FakeQueryJobConfig,
    )

    assert config.query_parameters == ["param"]
    assert config.maximum_bytes_billed == 123


def test_rows_to_dicts_normalizes_bigquery_rows() -> None:
    rows = [{"publication_number": "US1"}, {"publication_number": "US2"}]
    assert rows_to_dicts(rows) == rows


def test_cache_helpers_are_noops_without_cache() -> None:
    assert get_cached_result(None, "search", patent_id="US1") is None
    put_cached_result(None, "search", [{"publication_number": "US1"}], patent_id="US1")


def test_cache_helpers_delegate_when_cache_exists() -> None:
    cache = _FakeCache()

    cached = get_cached_result(cache, "search", patent_id="US1")
    put_cached_result(cache, "search", [{"publication_number": "US2"}], patent_id="US2")

    assert cached == [{"publication_number": "US1"}]
    assert cache.calls == [
        ("get", ("search",), {"patent_id": "US1"}),
        ("put", ("search", [{"publication_number": "US2"}]), {"patent_id": "US2"}),
    ]
