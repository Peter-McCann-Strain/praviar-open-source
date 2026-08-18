from __future__ import annotations

import hashlib

import structlog

from praviar_pipeline.logging_config import bind_compound_context, bind_pipeline_context


def test_bind_pipeline_context_redacts_compound_input() -> None:
    raw = "secret customer compound"

    run_id = bind_pipeline_context(compound_input=raw)
    context = structlog.contextvars.get_contextvars()

    assert context["run_id"] == run_id
    assert "compound_input" not in context
    assert context["compound_input_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert context["compound_input_length"] == len(raw)
    assert context["compound_input_type"] == "text_identifier"


def test_bind_compound_context_omits_resolved_identifiers() -> None:
    raw_name = "secret resolved compound"
    raw_cid = 987654

    bind_compound_context(name=raw_name, cid=raw_cid)
    context = structlog.contextvars.get_contextvars()

    assert raw_name not in context.values()
    assert raw_cid not in context.values()
    assert "compound_name" not in context
    assert "compound_cid" not in context
    assert context["resolved_compound_name_length"] == len(raw_name)
    assert context["resolved_compound_cid_present"] is True
