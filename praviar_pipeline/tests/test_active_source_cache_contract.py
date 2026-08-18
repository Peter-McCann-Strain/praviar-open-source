"""Exact-replay contract for every active direct external evidence path."""

from __future__ import annotations

import inspect

from praviar_pipeline.clients import (
    epo_ops_search,
    orange_book,
    paragraph_iv,
    pte_data,
    purple_book,
    tavily,
)


def test_all_active_direct_evidence_paths_use_response_cache() -> None:
    contracts = {
        tavily: "cached_request",
        epo_ops_search: "cached_request",
        orange_book: "cached_bytes_request",
        paragraph_iv: "cached_bytes_request",
        pte_data: "cached_request",
        purple_book: "cached_bytes_request",
    }

    for module, helper in contracts.items():
        source = inspect.getsource(module)
        assert f"await {helper}(" in source, module.__name__


def test_purple_book_uses_bounded_stream_before_cache() -> None:
    source = inspect.getsource(purple_book.fetch_purple_book_data)
    assert 'client.stream("GET", url)' in source
    assert "read_bounded_response_body(" in source
    assert "PURPLE_BOOK_MAX_CSV_BYTES" in source
