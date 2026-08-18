"""Tests for chat service helpers."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import bind_report_data, valid_report_data

from api.db.models import AnalysisStatus
from api.errors import APIError
from api.schemas.chat import ChatRequest
from api.services import chat_stream
from api.services.chat import (
    ChatConversationScope,
    PreparedChatRequest,
    build_chat_policy,
    build_patent_document,
    build_report_document,
    clear_conversation_history,
    extract_citations,
    get_analysis_report_for_chat,
    get_conversation_history,
    issue_or_validate_conversation_id,
    prepare_chat_request,
    save_conversation_history,
    stream_chat_events,
)


def _sample_report() -> dict:
    return {
        "generated_at": "2026-04-11T10:00:00+00:00",
        "praviar_pipeline_version": "1.2.3",
        "trust_mode": "counsel",
        "routing_profile": {
            "modality": "small_molecule",
            "matter_type": "small_molecule",
            "capability_profile": "core_certified",
            "claim_archetypes": ["composition"],
            "doctrine_packs": ["us", "epc"],
            "uncertainty_flags": [],
        },
        "opinion_readiness": {
            "trust_mode": "counsel",
            "attorney_supervision_required": True,
            "clearance_grade_ready": True,
            "approval_required": True,
            "export_ready": False,
            "summary": (
                "Attorney supervision is required before relying on a positive "
                "clearance conclusion."
            ),
        },
        "compound": {
            "name": "aspirin",
            "canonical_smiles": "CC(=O)Oc1ccccc1C(O)=O",
            "pubchem_cid": 2244,
            "molecular_weight": 180.16,
        },
        "risk_summary": {
            "overall_risk": "medium",
            "blocking_patents_count": 1,
            "executive_summary": "Moderate FTO risk.",
            "key_risks": ["US92000001A1 blocks the scaffold"],
        },
        "patent_analyses": [
            {
                "patent_id": "US92000001A1",
                "title": "Aspirin analogs",
                "assignee": "Praviar",
                "risk_level": "high",
                "expiry_date": "2032-01-01",
                "risk_summary": "Core scaffold coverage.",
                "claims_analyzed": [
                    {
                        "claim_number": "1",
                        "claim_type": "independent",
                        "overall_status": "potentially infringed",
                        "confidence": 0.8,
                        "preamble": "A compound comprising...",
                        "reasoning": "The scaffold overlaps.",
                        "elements": [
                            {
                                "element_number": "1.a",
                                "status": "matched",
                                "element_text": "an acetylated salicylate core",
                                "evidence": "Matches aspirin scaffold.",
                                "reasoning": "Direct structural overlap.",
                            }
                        ],
                    }
                ],
            }
        ],
        "patent_narratives": {"US92000001A1": "Narrative"},
        "doe_assessments": [
            {
                "patent_id": "US92000001A1",
                "overall_equivalent": True,
                "prosecution_estoppel_applies": False,
            }
        ],
        "invalidity_assessments": [],
        "analysis_failures": [],
        "audit_trail": {"patents_analyzed": 1},
        "patent_details": {"US92000001A1": {"abstract": "Patent abstract"}},
        "evidence_scope": {
            "mode": "external_evidence",
            "external_live_retrieval": True,
            "provider_capabilities": [
                {
                    "provider_name": "patentsview",
                    "provider_class": "public_open",
                    "live_retrieval_supported": True,
                    "jurisdiction_coverage": ["US", "EP"],
                    "modality_coverage": ["small_molecule"],
                    "governance_note": "Governed external retrieval is available.",
                }
            ],
        },
    }


def test_final_chat_citation_coverage_rejects_fabricated_source_text() -> None:
    assert (
        chat_stream.final_content_has_complete_citation_coverage(
            [
                SimpleNamespace(
                    text="The patent remains active.",
                    citations=[
                        SimpleNamespace(
                            cited_text="fabricated status",
                            document_index=0,
                            start_char_index=0,
                            end_char_index=13,
                        )
                    ],
                )
            ],
            source_documents=[
                {
                    "type": "document",
                    "source": {"type": "text", "data": "actual source text"},
                }
            ],
            streamed_text="The patent remains active.",
        )
        is False
    )


def test_streaming_chat_citation_coverage_rejects_two_assertions_per_citation() -> None:
    assert (
        chat_stream.streaming_assertions_have_individual_citations(
            ["The patent is active. It blocks the compound."],
            cited_source_groups=[["The patent is active and blocks the compound."]],
            trailing_text="",
            citations_valid=True,
        )
        is False
    )
    assert (
        chat_stream.streaming_assertions_have_individual_citations(
            ["The patent is active.", " It blocks the compound."],
            cited_source_groups=[
                ["The patent is active."],
                ["It blocks the compound."],
            ],
            trailing_text="",
            citations_valid=True,
        )
        is True
    )
    assert (
        chat_stream.streaming_assertions_have_individual_citations(
            ["No design-around exists."],
            cited_source_groups=[["Aspirin"]],
            trailing_text="",
            citations_valid=True,
        )
        is False
    )
    assert (
        chat_stream.streaming_assertions_have_individual_citations(
            ["Design-around exists."],
            cited_source_groups=[["No design-around exists."]],
            trailing_text="",
            citations_valid=True,
        )
        is False
    )
    assert (
        chat_stream.streaming_assertions_have_individual_citations(
            ["Aspirin blocks patent A."],
            cited_source_groups=[["Patent A blocks aspirin."]],
            trailing_text="",
            citations_valid=True,
        )
        is False
    )
    for conditional_source in (
        "If aspirin blocks patent A, damages follow.",
        "Whether aspirin blocks patent A remains unclear.",
        "Unless aspirin blocks patent A, launch remains clear.",
    ):
        assert (
            chat_stream.streaming_assertions_have_individual_citations(
                ["Aspirin blocks patent A."],
                cited_source_groups=[[conditional_source]],
                trailing_text="",
                citations_valid=True,
            )
            is False
        )


def _sample_scope() -> ChatConversationScope:
    return ChatConversationScope(
        org_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
        analysis_id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
        user_id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
    )


def test_issue_or_validate_conversation_id_accepts_server_uuid():
    conversation_id = str(uuid.uuid4())

    assert issue_or_validate_conversation_id(conversation_id) == conversation_id


def test_issue_or_validate_conversation_id_rejects_client_chosen_labels():
    with pytest.raises(APIError) as exc_info:
        issue_or_validate_conversation_id("conv-123")

    assert exc_info.value.status == 400


def test_build_report_document_includes_compound_and_patent_sections():
    document = build_report_document(_sample_report())

    assert document["title"] == "FTO Report: aspirin"
    assert "by Praviar FTO Analysis" in document["context"]
    assert "Praviar Pipeline" not in document["context"]
    section_text = "\n".join(
        block["text"] for block in document["source"]["content"] if block["type"] == "text"
    )
    assert "Executive Summary" in section_text
    assert "Patent: US92000001A1" in section_text
    assert "Pipeline Audit" in section_text


def test_build_patent_document_falls_back_to_full_report_when_missing_patent():
    report = _sample_report()

    document = build_patent_document("US92000003A1", report)

    assert document["title"] == "FTO Report: aspirin"


def test_extract_citations_supports_char_and_block_shapes():
    char_citation = SimpleNamespace(
        cited_text="risk summary",
        document_index=0,
        document_title="FTO Report",
        start_char_index=10,
        end_char_index=20,
    )
    block_citation = SimpleNamespace(
        cited_text="claim analysis",
        document_index=0,
        document_title="Patent Analysis",
        start_block_index=1,
        end_block_index=2,
    )
    blocks = [
        SimpleNamespace(citations=[char_citation]),
        SimpleNamespace(citations=[block_citation]),
    ]

    citations = extract_citations(blocks)

    assert citations == [
        {
            "cited_text": "risk summary",
            "document_index": 0,
            "document_title": "FTO Report",
            "type": "char",
            "start": 10,
            "end": 20,
        },
        {
            "cited_text": "claim analysis",
            "document_index": 0,
            "document_title": "Patent Analysis",
            "type": "block",
            "start_block": 1,
            "end_block": 2,
        },
    ]


def test_prepare_chat_request_builds_new_conversation_messages():
    conversation_id = str(uuid.uuid4())
    scope = _sample_scope()

    prepared = prepare_chat_request(
        ChatRequest(message="Summarize the risk", conversation_id=conversation_id),
        conversation_id=conversation_id,
        history_scope=scope,
        report_data=_sample_report(),
        history=[],
    )

    assert prepared.conversation_id == conversation_id
    assert prepared.history_scope == scope
    assert prepared.policy.trust_mode == "counsel"
    assert "export_summary" in prepared.policy.allowed_capabilities
    assert prepared.policy.tool_policy.external_retrieval_allowed is True
    assert "external_evidence_expand" in prepared.policy.allowed_capabilities
    assert "Governed Chat Policy" in prepared.system_prompt
    assert prepared.messages[0]["role"] == "user"
    assert prepared.messages[0]["content"][0]["title"] == "FTO Report: aspirin"
    assert prepared.messages[0]["content"][1]["text"] == "Summarize the risk"
    assert prepared.history[-1]["content"] == "Summarize the risk"


def test_prepare_chat_request_wraps_existing_history_with_patent_document():
    conversation_id = str(uuid.uuid4())
    history = [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
    ]

    prepared = prepare_chat_request(
        ChatRequest(
            message="Follow up",
            patent_id="US92000001A1",
            conversation_id=conversation_id,
        ),
        conversation_id=conversation_id,
        history_scope=_sample_scope(),
        report_data=_sample_report(),
        history=history,
    )

    assert prepared.messages[0]["content"][0]["title"] == "Patent Analysis: US92000001A1"
    assert prepared.messages[1] == {"role": "assistant", "content": "Earlier answer"}
    assert prepared.messages[-1] == {"role": "user", "content": "Follow up"}


def test_build_chat_policy_explorer_limits_capabilities():
    policy = build_chat_policy(
        {
            "trust_mode": "explorer",
            "routing_profile": {"capability_profile": "specialist_supervised"},
            "opinion_readiness": {
                "attorney_supervision_required": True,
                "export_ready": False,
            },
            "record_completeness": {"clearance_grade_ready": False},
        }
    )

    assert policy.trust_mode == "explorer"
    assert "screening_summary" in policy.allowed_capabilities
    assert "signable_opinion_summary" in policy.blocked_capabilities
    assert policy.tool_policy.external_retrieval_allowed is False
    assert policy.tool_policy.monitoring_actions_allowed is False


def test_build_chat_policy_monitor_surfaces_monitoring_controls():
    policy = build_chat_policy(
        {
            "trust_mode": "monitor",
            "routing_profile": {"capability_profile": "specialist_supervised"},
            "opinion_readiness": {
                "attorney_supervision_required": True,
                "export_ready": False,
            },
            "record_completeness": {"clearance_grade_ready": False},
            "search_loop_result": {"status": "ok"},
        }
    )

    assert policy.trust_mode == "monitor"
    assert "monitor_delta_summary" in policy.allowed_capabilities
    assert "watchlist_triage" in policy.allowed_capabilities
    assert "external_evidence_expand" in policy.blocked_capabilities
    assert policy.tool_policy.external_retrieval_allowed is False
    assert policy.tool_policy.monitoring_actions_allowed is True


def test_build_chat_policy_blocks_signable_summary_when_export_ready_is_malformed():
    report = _sample_report()
    report["trust_mode"] = "counsel"
    report["opinion_readiness"]["export_ready"] = "false"

    policy = build_chat_policy(report)

    assert "signable_opinion_summary" not in policy.allowed_capabilities
    assert "signable_opinion_summary" in policy.blocked_capabilities


def test_build_chat_policy_explorer_stays_report_grounded_even_with_external_scope_metadata():
    policy = build_chat_policy(
        {
            "trust_mode": "explorer",
            "routing_profile": {"capability_profile": "core_certified"},
            "opinion_readiness": {
                "attorney_supervision_required": True,
                "export_ready": False,
            },
            "record_completeness": {"clearance_grade_ready": False},
            "evidence_scope": {
                "mode": "external_evidence",
                "external_live_retrieval": True,
                "provider_capabilities": [
                    {
                        "provider_name": "patentsview",
                        "provider_class": "public_open",
                        "live_retrieval_supported": True,
                    }
                ],
            },
        }
    )

    assert policy.trust_mode == "explorer"
    assert policy.tool_policy.external_retrieval_allowed is False
    assert policy.tool_policy.monitoring_actions_allowed is False
    assert "screening_summary" in policy.allowed_capabilities


@pytest.mark.parametrize("trust_mode", ["counsel", "monitor"])
def test_build_chat_policy_blocks_external_retrieval_without_live_scope(
    trust_mode: str,
):
    report = _sample_report()
    report["trust_mode"] = trust_mode
    report["evidence_scope"] = {
        "mode": "report_evidence",
        "external_live_retrieval": False,
        "provider_capabilities": [
            {
                "provider_name": "Report-derived evidence layer",
                "provider_class": "report_derived",
                "live_retrieval_supported": False,
                "materialized_in_report": True,
            }
        ],
    }
    if trust_mode == "monitor":
        report["search_loop_result"] = {"status": "ok"}

    policy = build_chat_policy(report)

    assert policy.tool_policy.external_retrieval_allowed is False
    assert "external_evidence_expand" not in policy.allowed_capabilities
    assert "external_evidence_expand" in policy.blocked_capabilities
    assert {
        "field": "evidence_scope.live_provider_ready",
        "value": False,
    } in policy.evidence_basis


@pytest.mark.parametrize("trust_mode", ["counsel", "monitor"])
def test_build_chat_policy_permitted_trust_modes_can_expose_external_retrieval(
    trust_mode: str,
):
    report = _sample_report()
    report["trust_mode"] = trust_mode
    report["routing_profile"]["capability_profile"] = "core_certified"
    report["evidence_scope"] = {
        "mode": "external_evidence",
        "external_live_retrieval": True,
        "provider_capabilities": [
            {
                "provider_name": "patentsview",
                "provider_class": "public_open",
                "live_retrieval_supported": True,
                "jurisdiction_coverage": ["US", "EP"],
                "modality_coverage": ["small_molecule"],
                "governance_note": "Governed external retrieval is available.",
            }
        ],
    }
    if trust_mode == "monitor":
        report["search_loop_result"] = {"status": "ok"}

    policy = build_chat_policy(report)

    assert policy.tool_policy.external_retrieval_allowed is True
    assert "external_evidence_expand" in policy.allowed_capabilities
    assert any("external" in note.lower() for note in policy.tool_policy.notes)


@pytest.mark.asyncio
async def test_get_conversation_history_loads_json_payload():
    redis = AsyncMock()
    redis.get.return_value = json.dumps([{"role": "user", "content": "hello"}])
    scope = _sample_scope()
    conversation_id = str(uuid.uuid4())

    with patch("api.services.chat.get_redis", new=AsyncMock(return_value=redis)):
        history = await get_conversation_history(conversation_id, scope=scope)

    assert history == [{"role": "user", "content": "hello"}]
    redis.get.assert_awaited_once_with(
        f"chat:v2:{scope.org_id}:{scope.analysis_id}:{scope.user_id}:{conversation_id}"
    )


@pytest.mark.asyncio
async def test_conversation_history_key_is_scoped_to_org_analysis_and_user():
    redis = AsyncMock()
    redis.get.return_value = None
    conversation_id = str(uuid.uuid4())
    scope = _sample_scope()
    other_user_scope = ChatConversationScope(
        org_id=scope.org_id,
        analysis_id=scope.analysis_id,
        user_id=uuid.UUID("44444444-4444-4444-8444-444444444444"),
    )

    with patch("api.services.chat.get_redis", new=AsyncMock(return_value=redis)):
        await get_conversation_history(conversation_id, scope=scope)
        await get_conversation_history(conversation_id, scope=other_user_scope)

    first_key = redis.get.await_args_list[0].args[0]
    second_key = redis.get.await_args_list[1].args[0]
    assert first_key != second_key
    assert str(scope.user_id) in first_key
    assert str(other_user_scope.user_id) in second_key


@pytest.mark.asyncio
async def test_get_conversation_history_returns_empty_on_non_prod_redis_failure():
    redis = AsyncMock()
    redis.get.side_effect = RuntimeError("redis unavailable")
    settings = SimpleNamespace(app_env="dev")

    with patch("api.services.chat.get_redis", new=AsyncMock(return_value=redis)):
        history = await get_conversation_history(
            str(uuid.uuid4()),
            scope=_sample_scope(),
            settings=settings,  # type: ignore[arg-type]
        )

    assert history == []


@pytest.mark.asyncio
async def test_get_conversation_history_fails_closed_in_prod_on_redis_failure():
    redis = AsyncMock()
    redis.get.side_effect = RuntimeError("redis unavailable")
    settings = SimpleNamespace(app_env="prod")

    with (
        patch("api.services.chat.get_redis", new=AsyncMock(return_value=redis)),
        pytest.raises(APIError) as exc_info,
    ):
        await get_conversation_history(
            str(uuid.uuid4()),
            scope=_sample_scope(),
            settings=settings,  # type: ignore[arg-type]
        )

    assert exc_info.value.status == 503
    assert "Chat history backend is unavailable" in exc_info.value.detail


@pytest.mark.asyncio
async def test_save_conversation_history_trims_and_sets_ttl():
    redis = AsyncMock()
    settings = SimpleNamespace(app_env="test", chat_max_history=2, chat_history_ttl=600)
    messages = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]
    scope = _sample_scope()
    conversation_id = str(uuid.uuid4())

    with patch("api.services.chat.get_redis", new=AsyncMock(return_value=redis)):
        await save_conversation_history(
            conversation_id,
            messages,
            scope=scope,
            settings=settings,  # type: ignore[arg-type]
        )

    redis.set.assert_awaited_once()
    args, kwargs = redis.set.await_args
    assert (
        args[0] == f"chat:v2:{scope.org_id}:{scope.analysis_id}:{scope.user_id}:{conversation_id}"
    )
    assert json.loads(args[1]) == messages[-2:]
    assert kwargs == {"ex": 600}


@pytest.mark.asyncio
async def test_save_conversation_history_fails_closed_in_prod_on_redis_failure():
    redis = AsyncMock()
    redis.set.side_effect = RuntimeError("redis unavailable")
    settings = SimpleNamespace(app_env="prod", chat_max_history=2, chat_history_ttl=600)

    with (
        patch("api.services.chat.get_redis", new=AsyncMock(return_value=redis)),
        pytest.raises(APIError) as exc_info,
    ):
        await save_conversation_history(
            str(uuid.uuid4()),
            [{"role": "user", "content": "hello"}],
            scope=_sample_scope(),
            settings=settings,  # type: ignore[arg-type]
        )

    assert exc_info.value.status == 503
    assert "Chat history backend is unavailable" in exc_info.value.detail


@pytest.mark.asyncio
async def test_stream_chat_events_emits_stream_payloads_and_persists_history():
    class FakeStream:
        def __init__(self, events, final_message):
            self._events = events
            self._final_message = final_message

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            async def _iterate():
                for event in self._events:
                    yield event

            return _iterate()

        def get_final_message(self):
            return self._final_message

    class FakeClient:
        def __init__(self, stream):
            self.messages = self
            self._stream = stream

        def stream(self, **kwargs):
            self.kwargs = kwargs
            return self._stream

    stream = FakeStream(
        [
            SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(text="Risk summary."),
            ),
            SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(
                    type="citations_delta",
                    citation=SimpleNamespace(
                        cited_text="risk summary",
                        document_index=0,
                        start_char_index=0,
                        end_char_index=12,
                    ),
                ),
            ),
        ],
        SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=11,
                output_tokens=7,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=3,
            ),
            content=[
                SimpleNamespace(
                    text="Risk summary.",
                    citations=[
                        SimpleNamespace(
                            cited_text="risk summary",
                            document_index=0,
                            start_char_index=0,
                            end_char_index=12,
                        )
                    ],
                )
            ],
        ),
    )
    timeline: list[str] = []

    async def record_save(*_args, **_kwargs):
        timeline.append("history_saved")

    save_history = AsyncMock(side_effect=record_save)
    scope = _sample_scope()
    conversation_id = str(uuid.uuid4())
    prepared = PreparedChatRequest(
        conversation_id=conversation_id,
        history_scope=scope,
        system_prompt="system",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "text", "data": "risk summary"},
                    },
                    {"type": "text", "text": "Hello"},
                ],
            }
        ],
        history=[{"role": "user", "content": "Hello"}],
        policy=build_chat_policy(_sample_report()),
    )
    settings = SimpleNamespace(
        anthropic_api_key="test-key",
        chat_model="claude-sonnet-4-6",
        chat_max_tokens=2048,
        chat_history_ttl=600,
        chat_max_history=50,
    )

    with patch("api.services.chat_stream.record_provider_call") as provider_metric:
        events = []
        async for event in stream_chat_events(
            settings=settings,  # type: ignore[arg-type]
            prepared=prepared,
            client_factory=lambda **kwargs: FakeClient(stream),
            save_history_fn=save_history,
        ):
            events.append(event)
            timeline.append(event["type"])

    assert [event["type"] for event in events] == ["meta", "text", "citation", "done"]
    assert timeline == ["meta", "history_saved", "text", "citation", "done"]
    assert events[0]["capability_metadata"]["trust_mode"] == "counsel"
    assert "report_grounded_qna" in events[0]["capability_metadata"]["allowed_capabilities"]
    assert events[0]["capability_metadata"]["tool_policy"]["external_retrieval_allowed"] is True
    assert events[-1]["usage"]["cache_read_input_tokens"] == 3
    save_history.assert_awaited_once()
    assert save_history.await_args is not None
    args, kwargs = save_history.await_args
    assert args[0] == conversation_id
    assert args[1][-1]["content"] == "Risk summary."
    assert args[1][-1]["citations"][0]["cited_text"] == "risk summary"
    assert kwargs["scope"] == scope
    assert kwargs["settings"] is settings
    provider_metric.assert_called_once()
    assert provider_metric.call_args.kwargs["provider"] == "anthropic"
    assert provider_metric.call_args.kwargs["operation"] == "chat.stream"
    assert provider_metric.call_args.kwargs["errored"] is False


@pytest.mark.asyncio
async def test_stream_chat_events_blocks_uncited_assistant_answer_without_persisting():
    class FakeStream:
        def __init__(self, events, final_message):
            self._events = events
            self._final_message = final_message

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            async def _iterate():
                for event in self._events:
                    yield event

            return _iterate()

        def get_final_message(self):
            return self._final_message

    class FakeClient:
        def __init__(self, stream):
            self.messages = self
            self._stream = stream

        def stream(self, **kwargs):
            self.kwargs = kwargs
            return self._stream

    stream = FakeStream(
        [
            SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(text="Unsupported answer"),
            ),
        ],
        SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=11,
                output_tokens=7,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
            content=[],
        ),
    )
    save_history = AsyncMock()
    prepared = PreparedChatRequest(
        conversation_id=str(uuid.uuid4()),
        history_scope=_sample_scope(),
        system_prompt="system",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "text", "data": "support"},
                    },
                    {"type": "text", "text": "Hello"},
                ],
            }
        ],
        history=[{"role": "user", "content": "Hello"}],
        policy=build_chat_policy(_sample_report()),
    )
    settings = SimpleNamespace(
        anthropic_api_key="test-key",
        chat_model="claude-sonnet-4-6",
        chat_max_tokens=2048,
    )

    events = [
        event
        async for event in stream_chat_events(
            settings=settings,  # type: ignore[arg-type]
            prepared=prepared,
            client_factory=lambda **kwargs: FakeClient(stream),
            save_history_fn=save_history,
        )
    ]

    assert [event["type"] for event in events] == ["meta", "error"]
    assert events[-1]["code"] == "citation_validation_failed"
    assert (
        events[-1]["error"]
        == "Assistant response was blocked because it did not include citations."
    )
    save_history.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_chat_events_blocks_partially_cited_assistant_answer():
    class FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            async def _iterate():
                yield SimpleNamespace(
                    type="content_block_delta",
                    delta=SimpleNamespace(text="Support."),
                )
                yield SimpleNamespace(
                    type="content_block_delta",
                    delta=SimpleNamespace(
                        type="citations_delta",
                        citation=SimpleNamespace(
                            cited_text="support",
                            document_index=0,
                            start_char_index=0,
                            end_char_index=7,
                        ),
                    ),
                )
                yield SimpleNamespace(
                    type="content_block_delta",
                    delta=SimpleNamespace(text=" Unsupported conclusion."),
                )

            return _iterate()

        def get_final_message(self):
            return SimpleNamespace(
                usage=SimpleNamespace(
                    input_tokens=11,
                    output_tokens=7,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                ),
                content=[
                    SimpleNamespace(
                        text="Support.",
                        citations=[
                            SimpleNamespace(
                                cited_text="support",
                                document_index=0,
                                start_char_index=0,
                                end_char_index=7,
                            )
                        ],
                    ),
                    SimpleNamespace(
                        text=" Unsupported conclusion.",
                        citations=[],
                    ),
                ],
            )

    class FakeClient:
        def __init__(self):
            self.messages = self

        def stream(self, **kwargs):
            return FakeStream()

    save_history = AsyncMock()
    prepared = PreparedChatRequest(
        conversation_id=str(uuid.uuid4()),
        history_scope=_sample_scope(),
        system_prompt="system",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "text", "data": "support"},
                    },
                    {"type": "text", "text": "Hello"},
                ],
            }
        ],
        history=[{"role": "user", "content": "Hello"}],
        policy=build_chat_policy(_sample_report()),
    )

    events = [
        event
        async for event in stream_chat_events(
            settings=SimpleNamespace(
                anthropic_api_key="test-key",
                chat_model="claude-sonnet-4-6",
                chat_max_tokens=2048,
            ),
            prepared=prepared,
            client_factory=lambda **kwargs: FakeClient(),
            save_history_fn=save_history,
        )
    ]

    assert [event["type"] for event in events] == ["meta", "error"]
    assert events[-1]["code"] == "citation_validation_failed"
    assert "material assertions lacked valid citations" in events[-1]["error"]
    save_history.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_chat_events_redacts_provider_error_text_and_buffered_delta(
    monkeypatch,
):
    class FailingStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            async def _iterate():
                yield SimpleNamespace(
                    type="content_block_delta",
                    delta=SimpleNamespace(text="Unverified partial legal answer"),
                )
                raise RuntimeError("secret customer compound in provider failure")

            return _iterate()

    class FakeClient:
        def __init__(self):
            self.messages = self

        def stream(self, **kwargs):
            return FailingStream()

    monkeypatch.setattr(chat_stream.anthropic, "APIError", RuntimeError)
    prepared = PreparedChatRequest(
        conversation_id=str(uuid.uuid4()),
        history_scope=_sample_scope(),
        system_prompt="system",
        messages=[{"role": "user", "content": "Hello"}],
        history=[{"role": "user", "content": "Hello"}],
        policy=build_chat_policy(_sample_report()),
    )
    settings = SimpleNamespace(
        anthropic_api_key="test-key",
        chat_model="claude-sonnet-4-6",
        chat_max_tokens=2048,
    )

    events = [
        event
        async for event in stream_chat_events(
            settings=settings,  # type: ignore[arg-type]
            prepared=prepared,
            client_factory=lambda **kwargs: FakeClient(),
            save_history_fn=AsyncMock(),
        )
    ]

    assert [event["type"] for event in events] == ["meta", "error"]
    assert events[-1]["error"] == "Provider error while streaming chat"
    assert "secret customer compound" not in str(events)
    assert "Unverified partial legal answer" not in str(events)


@pytest.mark.asyncio
async def test_get_analysis_report_for_chat_returns_analysis(mock_db):
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    report_data = bind_report_data(
        valid_report_data(),
        analysis_id=analysis_id,
        org_id=org_id,
    )
    analysis = MagicMock(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report_data,
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = analysis

    result = await get_analysis_report_for_chat(
        mock_db,
        analysis_id=analysis_id,
        org_id=org_id,
    )

    assert result is analysis


@pytest.mark.asyncio
async def test_get_analysis_report_for_chat_raises_when_missing_report(mock_db):
    analysis = MagicMock(status=AnalysisStatus.COMPLETED, report_data=None)
    mock_db.execute.return_value.scalar_one_or_none.return_value = analysis

    with pytest.raises(APIError) as exc_info:
        await get_analysis_report_for_chat(
            mock_db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404


@pytest.mark.asyncio
async def test_get_analysis_report_for_chat_rejects_non_completed_report_payload(mock_db):
    analysis = MagicMock(status=AnalysisStatus.RUNNING, report_data={"ok": True})
    mock_db.execute.return_value.scalar_one_or_none.return_value = analysis

    with pytest.raises(APIError) as exc_info:
        await get_analysis_report_for_chat(
            mock_db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404
    assert exc_info.value.detail == "Report not found"


@pytest.mark.asyncio
async def test_clear_conversation_history_is_best_effort_outside_prod():
    redis = AsyncMock()
    redis.delete.side_effect = RuntimeError("redis unavailable")
    settings = SimpleNamespace(app_env="dev")

    with patch("api.services.chat.get_redis", new=AsyncMock(return_value=redis)):
        await clear_conversation_history(
            str(uuid.uuid4()),
            scope=_sample_scope(),
            settings=settings,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_clear_conversation_history_fails_closed_in_prod():
    redis = AsyncMock()
    redis.delete.side_effect = RuntimeError("redis unavailable")
    settings = SimpleNamespace(app_env="prod")

    with (
        patch("api.services.chat.get_redis", new=AsyncMock(return_value=redis)),
        pytest.raises(APIError) as exc_info,
    ):
        await clear_conversation_history(
            str(uuid.uuid4()),
            scope=_sample_scope(),
            settings=settings,  # type: ignore[arg-type]
        )

    assert exc_info.value.status == 503
    assert "Chat history backend is unavailable" in exc_info.value.detail
