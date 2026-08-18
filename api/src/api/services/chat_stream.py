"""Streaming event helpers for chat responses."""

from __future__ import annotations

import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol, cast

import anthropic
import structlog

from api.metrics import (
    chat_citation_validation_failures_total,
    chat_history_persist_failures_total,
    record_provider_call,
)
from api.observability.spans import record_span_exception, start_span

logger = structlog.get_logger()

CITATION_VALIDATION_ERROR_CODE = "citation_validation_failed"
_ASSERTION_BOUNDARY = re.compile(r"(?<=[.!?])(?:\s+|$)|[;\n]+")
_SUPPORT_TOKEN = re.compile(r"[A-Za-z0-9]+")
_POLARITY_AND_MODALITY_TOKENS = frozenset(
    {
        "cannot",
        "cant",
        "could",
        "may",
        "might",
        "never",
        "no",
        "not",
        "should",
        "unlikely",
        "without",
        "would",
    }
)


class ChatSettings(Protocol):
    anthropic_api_key: str
    chat_model: str
    chat_max_tokens: int


class PreparedChatRequest(Protocol):
    @property
    def conversation_id(self) -> str: ...

    @property
    def policy(self) -> Any: ...

    @property
    def system_prompt(self) -> str: ...

    @property
    def messages(self) -> list[dict[str, Any]]: ...

    @property
    def history(self) -> list[dict[str, Any]]: ...

    @property
    def history_scope(self) -> Any: ...


class ChatMessagesClient(Protocol):
    messages: Any


class AssistantMessageAppender(Protocol):
    def __call__(
        self,
        history: list[dict[str, Any]],
        *,
        content: str,
        citations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...


def extract_citations(content_blocks: list[Any]) -> list[dict[str, Any]]:
    """Extract citation metadata from Anthropic content blocks."""
    citations = []
    for block in content_blocks:
        if hasattr(block, "citations") and block.citations:
            for citation in block.citations:
                citation_value = cast(Any, citation)
                citation_info = {
                    "cited_text": getattr(citation, "cited_text", ""),
                    "document_index": getattr(citation, "document_index", 0),
                    "document_title": getattr(citation, "document_title", None),
                }
                if hasattr(citation_value, "start_char_index"):
                    citation_info["type"] = "char"
                    citation_info["start"] = citation_value.start_char_index
                    citation_info["end"] = citation_value.end_char_index
                elif hasattr(citation_value, "start_block_index"):
                    citation_info["type"] = "block"
                    citation_info["start_block"] = citation_value.start_block_index
                    citation_info["end_block"] = citation_value.end_block_index
                citations.append(citation_info)
    return citations


def _citation_is_structurally_valid(citation: object) -> bool:
    """Reject empty, malformed, or out-of-range provider citation metadata."""
    citation_value = cast(Any, citation)
    cited_text = getattr(citation_value, "cited_text", "")
    document_index = getattr(citation_value, "document_index", None)
    if (
        not isinstance(cited_text, str)
        or not cited_text.strip()
        or isinstance(document_index, bool)
        or not isinstance(document_index, int)
        or document_index < 0
    ):
        return False

    if hasattr(citation_value, "start_char_index"):
        start = getattr(citation_value, "start_char_index", None)
        end = getattr(citation_value, "end_char_index", None)
    elif hasattr(citation_value, "start_block_index"):
        start = getattr(citation_value, "start_block_index", None)
        end = getattr(citation_value, "end_block_index", None)
    else:
        return False

    return (
        not isinstance(start, bool)
        and isinstance(start, int)
        and not isinstance(end, bool)
        and isinstance(end, int)
        and 0 <= start < end
    )


def _prepared_source_documents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect provider document blocks in the same order used by citation indexes."""
    documents: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "document":
                documents.append(block)
    return documents


def _normalized_citation_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _material_assertion_count(text: str) -> int:
    count = 0
    for raw_segment in _ASSERTION_BOUNDARY.split(text):
        segment = raw_segment.strip()
        if not segment or segment.startswith("#"):
            continue
        segment = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", segment).strip()
        if any(character.isalnum() for character in segment):
            count += 1
    return count


def streaming_assertions_have_individual_citations(
    cited_segments: list[str],
    *,
    cited_source_groups: list[list[str]],
    trailing_text: str,
    citations_valid: bool,
) -> bool:
    """Require an immediate, source-supporting citation per material assertion."""
    if (
        not citations_valid
        or len(cited_segments) != len(cited_source_groups)
        or _material_assertion_count(trailing_text) != 0
    ):
        return False
    for segment, cited_sources in zip(
        cited_segments,
        cited_source_groups,
        strict=True,
    ):
        assertion_count = _material_assertion_count(segment)
        if assertion_count > 1:
            return False
        if assertion_count == 0:
            continue
        assertion_tokens = [token.lower() for token in _SUPPORT_TOKEN.findall(segment)]
        # Preserve the exact cited assertion, including every condition,
        # uncertainty qualifier, negation, and modal. Even contiguous matching
        # is unsafe: "if X blocks Y" contains "X blocks Y" but does not entail
        # it. Chat therefore releases only token-identical cited assertions.
        if not assertion_tokens or not any(
            _source_extractively_supports_assertion(
                assertion_tokens,
                cited_source,
            )
            for cited_source in cited_sources
        ):
            return False
    return True


def _source_extractively_supports_assertion(
    assertion_tokens: list[str],
    cited_source: str,
) -> bool:
    assertion_polarity = {
        token for token in assertion_tokens if token in _POLARITY_AND_MODALITY_TOKENS
    }
    for source_segment in _ASSERTION_BOUNDARY.split(cited_source):
        source_tokens = [token.lower() for token in _SUPPORT_TOKEN.findall(source_segment)]
        source_polarity = {
            token for token in source_tokens if token in _POLARITY_AND_MODALITY_TOKENS
        }
        if source_polarity == assertion_polarity and source_tokens == assertion_tokens:
            return True
    return False


def _citation_matches_prepared_source(
    citation: object,
    source_documents: list[dict[str, Any]],
) -> bool:
    """Bind a provider citation to the exact prepared document span."""
    citation_value = cast(Any, citation)
    document_index = citation_value.document_index
    if document_index >= len(source_documents):
        return False
    source = source_documents[document_index].get("source")
    if not isinstance(source, dict):
        return False

    cited_text = _normalized_citation_text(citation_value.cited_text)
    if hasattr(citation_value, "start_char_index"):
        source_text = source.get("data", source.get("text"))
        if not isinstance(source_text, str):
            return False
        start = citation_value.start_char_index
        end = citation_value.end_char_index
        if end > len(source_text):
            return False
        selected_text = source_text[start:end]
    else:
        source_content = source.get("content")
        if not isinstance(source_content, list):
            return False
        start = citation_value.start_block_index
        end = citation_value.end_block_index
        if end > len(source_content):
            return False
        selected_blocks = source_content[start:end]
        if not selected_blocks:
            return False
        selected_text = "\n".join(
            block.get("text", "")
            for block in selected_blocks
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )

    normalized_selected_text = _normalized_citation_text(selected_text)
    return bool(cited_text and normalized_selected_text and cited_text in normalized_selected_text)


def final_content_has_complete_citation_coverage(
    content_blocks: list[Any],
    *,
    source_documents: list[dict[str, Any]],
    streamed_text: str,
) -> bool:
    """Require valid citations on every substantive final response text block.

    A single citation anywhere in a response is insufficient for a legal-analysis
    surface. Anthropic associates citations with individual final text blocks, so
    the final provider message is the authoritative coverage record.
    """
    if not streamed_text.strip():
        return True

    substantive_blocks: list[Any] = []
    reconstructed_text: list[str] = []
    for block in content_blocks:
        text = getattr(block, "text", None)
        if not isinstance(text, str):
            continue
        reconstructed_text.append(text)
        if not any(character.isalnum() for character in text):
            continue
        substantive_blocks.append(block)
        citations = getattr(block, "citations", None)
        if not citations or not all(
            _citation_is_structurally_valid(citation)
            and _citation_matches_prepared_source(citation, source_documents)
            for citation in citations
        ):
            return False

    # Fail closed if the provider omits the final text blocks or if their text
    # does not match the response that was buffered from streaming deltas.
    if not substantive_blocks:
        return False
    return "".join(reconstructed_text) == streamed_text


def extract_delta_citation(citation: object) -> dict[str, Any]:
    """Normalize a streaming citation delta into the public response shape."""
    citation_value = cast(Any, citation)
    citation_info = {
        "cited_text": getattr(citation, "cited_text", ""),
        "document_index": getattr(citation, "document_index", 0),
    }
    if hasattr(citation_value, "start_block_index"):
        citation_info["type"] = "block"
        citation_info["start_block"] = citation_value.start_block_index
        citation_info["end_block"] = citation_value.end_block_index
    elif hasattr(citation_value, "start_char_index"):
        citation_info["type"] = "char"
        citation_info["start"] = citation_value.start_char_index
        citation_info["end"] = citation_value.end_char_index
    return citation_info


def build_usage(final_message: object) -> dict[str, Any]:
    """Normalize Anthropic usage metadata into the public response shape."""
    usage = cast(Any, final_message).usage
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
    }


def append_assistant_message(
    history: list[dict[str, Any]],
    *,
    content: str,
    citations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Append the assistant reply to persisted conversation history."""
    from datetime import UTC, datetime

    updated_history = list(history)
    updated_history.append(
        {
            "role": "assistant",
            "content": content,
            "citations": citations,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    return updated_history


async def stream_chat_events(
    *,
    settings: ChatSettings,
    prepared: PreparedChatRequest,
    client_factory: Callable[..., ChatMessagesClient] | None = None,
    save_history_fn: Callable[..., Awaitable[None]],
    extract_citations_fn: Callable[[list[Any]], list[dict[str, Any]]] = extract_citations,
    extract_delta_citation_fn: Callable[[object], dict[str, Any]] = extract_delta_citation,
    build_usage_fn: Callable[[object], dict[str, Any]] = build_usage,
    append_assistant_message_fn: AssistantMessageAppender = append_assistant_message,
) -> AsyncIterator[dict[str, Any]]:
    """Yield normalized chat stream events and persist the completed assistant reply."""
    from api.circuit_breaker import CircuitOpenError, anthropic_breaker

    resolved_client_factory = client_factory or cast(
        Callable[..., ChatMessagesClient],
        lambda api_key: anthropic.AsyncAnthropic(api_key=api_key, timeout=120.0),
    )
    client = resolved_client_factory(api_key=settings.anthropic_api_key)
    full_text = ""
    text_deltas: list[str] = []
    all_citations: list[dict[str, Any]] = []
    citation_deltas: list[dict[str, Any]] = []
    text_since_last_citation = ""
    cited_text_segments: list[str] = []
    cited_source_groups: list[list[str]] = []
    streaming_citations_valid = True
    source_documents = _prepared_source_documents(prepared.messages)
    started = time.perf_counter()
    span = None
    provider_call_succeeded = False

    # Acquire the bulkhead slot FIRST so that probe acquisition never blocks
    # with _probing=True visible to other callers (matching .call() ordering).
    # If the bulkhead is saturated under normal load, the probe waits here
    # without stalling recovery for other callers.
    try:
        await anthropic_breaker.bulkhead_acquire()
    except BaseException:
        raise  # probe not yet acquired; nothing to release

    try:
        # _check_and_maybe_probe drives OPEN→HALF_OPEN and raises CircuitOpenError
        # when the circuit is still open. Called AFTER bulkhead acquisition so that
        # probe ownership (_probing=True) is never held while waiting for a slot.
        try:
            anthropic_breaker._check_and_maybe_probe()
        except CircuitOpenError as exc:
            logger.warning(
                "chat_circuit_open_fast_fail",
                retry_after_s=exc.retry_after_s,
                conversation_id=prepared.conversation_id,
            )
            yield {
                "type": "error",
                "error": "AI provider is temporarily unavailable; please retry shortly",
            }
            return  # finally block releases the bulkhead slot
        try:
            with start_span(
                "provider.anthropic.chat_stream",
                {
                    "llm.provider": "anthropic",
                    "llm.request.type": "chat_stream",
                    "llm.request.model": settings.chat_model,
                    "chat.conversation_id": prepared.conversation_id,
                },
            ) as active_span:
                span = active_span
                yield {
                    "type": "meta",
                    "conversation_id": prepared.conversation_id,
                    "capability_metadata": prepared.policy.model_dump(mode="json"),
                }

                async with client.messages.stream(
                    model=settings.chat_model,
                    max_tokens=settings.chat_max_tokens,
                    system=prepared.system_prompt,
                    messages=prepared.messages,
                ) as stream:
                    async for event in stream:
                        if hasattr(event, "type") and event.type == "content_block_delta":
                            delta = event.delta
                            if hasattr(delta, "text"):
                                full_text += delta.text
                                text_deltas.append(delta.text)
                                text_since_last_citation += delta.text
                            elif hasattr(delta, "type") and delta.type == "citations_delta":
                                raw_citation = delta.citation
                                streaming_citations_valid = (
                                    streaming_citations_valid
                                    and _citation_is_structurally_valid(raw_citation)
                                    and _citation_matches_prepared_source(
                                        raw_citation,
                                        source_documents,
                                    )
                                )
                                if _material_assertion_count(text_since_last_citation) > 0:
                                    cited_text_segments.append(text_since_last_citation)
                                    cited_source_groups.append(
                                        [str(getattr(raw_citation, "cited_text", ""))]
                                    )
                                elif cited_source_groups:
                                    cited_source_groups[-1].append(
                                        str(getattr(raw_citation, "cited_text", ""))
                                    )
                                else:
                                    streaming_citations_valid = False
                                text_since_last_citation = ""
                                citation_info = extract_delta_citation_fn(delta.citation)
                                all_citations.append(citation_info)
                                citation_deltas.append(citation_info)

                    final = stream.get_final_message()
                    final_citations = extract_citations_fn(final.content)
                    if final_citations:
                        all_citations = final_citations
                    citation_coverage_complete = final_content_has_complete_citation_coverage(
                        final.content,
                        source_documents=source_documents,
                        streamed_text=full_text,
                    )
                    streaming_citation_coverage_complete = (
                        streaming_assertions_have_individual_citations(
                            cited_text_segments,
                            cited_source_groups=cited_source_groups,
                            trailing_text=text_since_last_citation,
                            citations_valid=streaming_citations_valid,
                        )
                    )
                    usage = build_usage_fn(final)
            anthropic_breaker.record_success()
            provider_call_succeeded = (
                True  # set before metric call so a metrics-layer raise can't mis-attribute
            )
            record_provider_call(
                provider="anthropic",
                operation="chat.stream",
                duration_s=time.perf_counter() - started,
                errored=False,
            )

            if full_text.strip() and not all_citations:
                chat_citation_validation_failures_total.labels(reason="missing_citations").inc()
                logger.warning(
                    "uncited_chat_response_blocked",
                    conversation_id=prepared.conversation_id,
                )
                yield {
                    "type": "error",
                    "code": CITATION_VALIDATION_ERROR_CODE,
                    "error": "Assistant response was blocked because it did not include citations.",
                }
                return

            if not (citation_coverage_complete and streaming_citation_coverage_complete):
                chat_citation_validation_failures_total.labels(
                    reason="incomplete_block_coverage"
                ).inc()
                logger.warning(
                    "incompletely_cited_chat_response_blocked",
                    conversation_id=prepared.conversation_id,
                )
                yield {
                    "type": "error",
                    "code": CITATION_VALIDATION_ERROR_CODE,
                    "error": (
                        "Assistant response was blocked because one or more "
                        "material assertions lacked valid citations."
                    ),
                }
                return

            updated_history = append_assistant_message_fn(
                prepared.history,
                content=full_text,
                citations=all_citations,
            )
            await save_history_fn(
                prepared.conversation_id,
                updated_history,
                scope=prepared.history_scope,
                settings=settings,
            )
            # Do not release legal-analysis text to the client until citation
            # validation and durable history persistence both succeed.
            for text_delta in text_deltas:
                yield {"type": "text", "text": text_delta}
            for citation_info in citation_deltas:
                yield {"type": "citation", "citation": citation_info}
            yield {"type": "done", "usage": usage, "citations": all_citations}
        except anthropic.APIError as exc:
            anthropic_breaker.record_failure(exc)
            record_span_exception(span, exc)
            record_provider_call(
                provider="anthropic",
                operation="chat.stream",
                duration_s=time.perf_counter() - started,
                errored=True,
            )
            logger.error("chat_api_error", error_type=type(exc).__name__, exc_info=True)
            yield {"type": "error", "error": "Provider error while streaming chat"}
        except Exception as exc:
            # Only attribute fault to the Anthropic circuit/metric if the provider call
            # itself failed. Post-stream DB/history errors must not trip the AI breaker
            # nor pollute the provider error counter.
            if not provider_call_succeeded:
                anthropic_breaker.record_failure(exc)
                record_provider_call(
                    provider="anthropic",
                    operation="chat.stream",
                    duration_s=time.perf_counter() - started,
                    errored=True,
                )
            else:
                chat_history_persist_failures_total.inc()
            record_span_exception(span, exc)
            logger.error("chat_stream_error", error_type=type(exc).__name__, exc_info=True)
            yield {"type": "error", "error": "An unexpected error occurred"}
        except BaseException:
            # GeneratorExit (SSE client disconnect) and asyncio.CancelledError are
            # BaseException subclasses, not Exception. Client cancellation is not a
            # provider fault — calling record_failure here would trip the Anthropic
            # circuit OPEN after 5 normal user disconnects, fast-failing all chat
            # even when Anthropic is healthy. Instead release the probe lock so the
            # HALF_OPEN state can be retried by the next caller.
            anthropic_breaker.record_cancelled()
            raise
    finally:
        anthropic_breaker.bulkhead_release()
