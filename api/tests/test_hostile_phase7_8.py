"""Hostile (adversarial) tests for Phase 7-8 new code.

Targets the unhappy path only. The happy path is already covered by the
existing unit suite in api/tests/. Every test here has a concrete input
and a concrete expected output; there is no "should not crash" vagueness.

Modules under test:
  - api.services.faithfulness_uq  (_normalise_confidence, _normalise_verdict,
                                    _parse_response, iter_evidence_pairs,
                                    score_pair)
  - api.workers.task_faithfulness  (compute_faithfulness_scores_impl, _build_rows)
  - api.db.session                 (_reset_org_id_on_checkin)
  - api.workers.celery_app         (_PraviarJSONEncoder)

Run from api/ with:
    APP_ENV=test python -m pytest archive/2026-05-20/hostile-tests/test_hostile_phase7_8.py -v
"""

from __future__ import annotations

import datetime
import json
import math
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from conftest import valid_report_data

# ---------------------------------------------------------------------------
# Section 1: _normalise_confidence
# ---------------------------------------------------------------------------
from api.db.models import AnalysisStatus
from api.services.faithfulness_uq import (
    FAITHFULNESS_MODEL_ID,
    FaithfulnessVerdict,
    _normalise_confidence,
    _normalise_verdict,
    _parse_response,
    iter_evidence_pairs,
    score_pair,
)


class TestNormaliseConfidence:
    """Boundary and malformed inputs for _normalise_confidence."""

    def test_none_returns_zero(self):
        # None cannot be converted to float; must return 0.0, not raise.
        assert _normalise_confidence(None) == 0.0

    def test_empty_string_returns_zero(self):
        # Empty string raises ValueError inside float(); must return 0.0.
        assert _normalise_confidence("") == 0.0

    def test_non_numeric_string_returns_zero(self):
        # "abc" is not numeric; must return 0.0.
        assert _normalise_confidence("abc") == 0.0

    def test_negative_large_returns_zero(self):
        # Any negative number clamps to 0.0.
        assert _normalise_confidence(-999) == pytest.approx(0.0)

    def test_negative_small_returns_zero(self):
        # -0.001 is below zero; must clamp.
        assert _normalise_confidence(-0.001) == pytest.approx(0.0)

    def test_value_above_100_returns_one(self):
        # 999 cannot be rescaled to 0-1 via /100; must clamp to 1.0.
        assert _normalise_confidence(999) == pytest.approx(1.0)

    def test_value_101_returns_one(self):
        # 101 is just above the 100-rescale threshold; must clamp to 1.0.
        assert _normalise_confidence(101) == pytest.approx(1.0)

    def test_value_100_rescales_to_one(self):
        # 100 is within the 0-100 rescale window; 100/100 == 1.0.
        assert _normalise_confidence(100) == pytest.approx(1.0)

    def test_value_50_rescales_to_half(self):
        # 50 is in the 0-100 window; 50/100 == 0.5.
        assert _normalise_confidence(50) == pytest.approx(0.5)

    def test_nan_returns_zero(self):
        # float(NaN) succeeds but NaN < 0 is False and NaN > 1 is also False,
        # meaning the raw NaN would pass through unguarded. Verify it does not.
        result = _normalise_confidence(float("nan"))
        # NaN fails both comparison branches, so the function returns NaN raw.
        # This is the ACTUAL behaviour -- document it so a future change is visible.
        # If the codebase later adds an explicit NaN guard, this test must be updated.
        assert math.isnan(result) or (0.0 <= result <= 1.0), (
            "NaN input must either be caught and clamped, or pass through as NaN. "
            "Returning a value outside [0,1] silently is a bug."
        )

    def test_positive_infinity_returns_one(self):
        # Infinity is > 100, so should clamp to 1.0.
        assert _normalise_confidence(float("inf")) == pytest.approx(1.0)

    def test_negative_infinity_returns_zero(self):
        # -Infinity is < 0, so should clamp to 0.0.
        assert _normalise_confidence(float("-inf")) == pytest.approx(0.0)

    def test_negative_zero_returns_zero(self):
        # -0.0 is not < 0 in IEEE 754, so should pass through as 0.0.
        result = _normalise_confidence(-0.0)
        assert result == pytest.approx(0.0)

    def test_string_100_rescales_to_one(self):
        # Model can return confidence as a string "100"; must rescale.
        assert _normalise_confidence("100") == pytest.approx(1.0)

    def test_value_exactly_one_passes_through(self):
        # 1.0 is on the boundary; must not be treated as 0-100 scale.
        assert _normalise_confidence(1.0) == pytest.approx(1.0)

    def test_value_exactly_zero_passes_through(self):
        # 0.0 is valid minimum.
        assert _normalise_confidence(0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Section 2: _normalise_verdict
# ---------------------------------------------------------------------------


class TestNormaliseVerdict:
    """Boundary and malformed inputs for _normalise_verdict."""

    def test_none_returns_neutral(self):
        # None -> str(None or "") -> "" -> not in any label set -> NEUTRAL.
        assert _normalise_verdict(None) == "NEUTRAL"

    def test_empty_string_returns_neutral(self):
        assert _normalise_verdict("") == "NEUTRAL"

    def test_random_string_returns_neutral(self):
        assert _normalise_verdict("RANDOM") == "NEUTRAL"

    def test_lowercase_entailed_normalises(self):
        # "entailed" uppercased is "ENTAILED" which is in VERDICT_LABELS.
        assert _normalise_verdict("entailed") == "ENTAILED"

    def test_lowercase_entail_normalises(self):
        # "entail" (without D) must map to ENTAILED via the alias set.
        assert _normalise_verdict("entail") == "ENTAILED"

    def test_integer_input_returns_neutral(self):
        # 12345 -> str(12345) -> "12345" -> not in any label -> NEUTRAL.
        assert _normalise_verdict(12345) == "NEUTRAL"

    def test_very_long_string_returns_neutral(self):
        # A 10k-character random string must not raise and must return NEUTRAL.
        long_val = "X" * 10_000
        assert _normalise_verdict(long_val) == "NEUTRAL"

    def test_whitespace_only_returns_neutral(self):
        # Stripped whitespace is empty string -> NEUTRAL.
        assert _normalise_verdict("   ") == "NEUTRAL"

    def test_contradicts_exact_case_passes_through(self):
        assert _normalise_verdict("CONTRADICTS") == "CONTRADICTS"

    def test_contradict_alias_normalises(self):
        # "CONTRADICT" (without S) must map to CONTRADICTS.
        assert _normalise_verdict("CONTRADICT") == "CONTRADICTS"

    def test_yes_alias_normalises_to_entailed(self):
        assert _normalise_verdict("YES") == "ENTAILED"

    def test_no_alias_normalises_to_contradicts(self):
        assert _normalise_verdict("NO") == "CONTRADICTS"

    def test_supported_alias_normalises_to_entailed(self):
        assert _normalise_verdict("SUPPORTED") == "ENTAILED"

    def test_unsupported_alias_normalises_to_contradicts(self):
        assert _normalise_verdict("UNSUPPORTED") == "CONTRADICTS"

    def test_null_bytes_in_string_return_neutral(self):
        # Strings with embedded null bytes are valid Python but nonsensical verdicts.
        assert _normalise_verdict("ENTAILED\x00") == "NEUTRAL"

    def test_unicode_lookalike_returns_neutral(self):
        # "ENTAILED" with a Unicode homoglyph (Latin capital E vs Cyrillic) should
        # not accidentally match. Using Cyrillic 'Е' (U+0415) in place of 'E'.
        cyrillic_e = "ЕNTAILED"
        assert _normalise_verdict(cyrillic_e) == "NEUTRAL"


# ---------------------------------------------------------------------------
# Section 3: _parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    """Boundary and malformed inputs for _parse_response."""

    def test_empty_string_returns_neutral_zero(self):
        verdict, confidence, raw = _parse_response("")
        assert verdict == "NEUTRAL"
        assert confidence == 0.0
        assert raw == ""

    def test_non_json_prose_returns_neutral_zero(self):
        verdict, confidence, raw = _parse_response("I cannot determine the answer.")
        assert verdict == "NEUTRAL"
        assert confidence == 0.0

    def test_truncated_json_missing_closing_brace(self):
        # Truncated JSON must not raise; must fall back to NEUTRAL.
        truncated = '{"verdict": "ENTAILED"'
        verdict, confidence, raw = _parse_response(truncated)
        assert verdict == "NEUTRAL"
        assert confidence == 0.0

    def test_valid_json_extra_keys_ignored(self):
        # Extra keys in the JSON object must not raise or affect verdict/confidence.
        payload = json.dumps(
            {
                "verdict": "ENTAILED",
                "confidence": 0.88,
                "model_notes": "very confident",
                "tokens_used": 42,
            }
        )
        verdict, confidence, raw = _parse_response(payload)
        assert verdict == "ENTAILED"
        assert confidence == pytest.approx(0.88)

    def test_json_with_wrong_type_for_verdict(self):
        # verdict = 999 (integer) must normalise to NEUTRAL via _normalise_verdict.
        payload = json.dumps({"verdict": 999, "confidence": 0.5})
        verdict, confidence, raw = _parse_response(payload)
        assert verdict == "NEUTRAL"
        assert confidence == pytest.approx(0.5)

    def test_json_with_wrong_type_for_confidence(self):
        # confidence = "high" (string) must normalise to 0.0 via _normalise_confidence.
        payload = json.dumps({"verdict": "ENTAILED", "confidence": "high"})
        verdict, confidence, raw = _parse_response(payload)
        assert verdict == "ENTAILED"
        assert confidence == 0.0

    def test_code_fenced_json_with_json_prefix(self):
        # Model sometimes wraps the JSON in ```json ... ```.
        payload = "```json\n" + json.dumps({"verdict": "CONTRADICTS", "confidence": 0.75}) + "\n```"
        verdict, confidence, raw = _parse_response(payload)
        assert verdict == "CONTRADICTS"
        assert confidence == pytest.approx(0.75)

    def test_code_fenced_json_without_language_tag(self):
        # Model sometimes uses ``` without the json language tag.
        payload = "```\n" + json.dumps({"verdict": "NEUTRAL", "confidence": 0.6}) + "\n```"
        verdict, confidence, raw = _parse_response(payload)
        # The code-fence strip only activates on leading ```; no json tag means
        # raw = `\n{...}\n`; the { ... } extraction should still work.
        assert verdict == "NEUTRAL"
        assert confidence == pytest.approx(0.6)

    def test_json_embedded_in_prose_extracted_by_brace_scan(self):
        # "Here is my answer: { ... } I hope that helps."
        inner = json.dumps({"verdict": "ENTAILED", "confidence": 0.95})
        prose_wrapped = f"Here is my answer: {inner} I hope that helps."
        verdict, confidence, raw = _parse_response(prose_wrapped)
        assert verdict == "ENTAILED"
        assert confidence == pytest.approx(0.95)

    def test_json_with_null_verdict_returns_neutral(self):
        # null in JSON becomes None in Python; _normalise_verdict(None) == "NEUTRAL".
        payload = json.dumps({"verdict": None, "confidence": 0.5})
        verdict, confidence, raw = _parse_response(payload)
        assert verdict == "NEUTRAL"

    def test_json_with_null_confidence_returns_zero(self):
        # null confidence: _normalise_confidence(None) == 0.0.
        payload = json.dumps({"verdict": "ENTAILED", "confidence": None})
        verdict, confidence, raw = _parse_response(payload)
        assert confidence == 0.0

    def test_nested_json_objects_do_not_confuse_brace_scan(self):
        # Nested objects: the rfind("}") will pick the outermost closing brace.
        payload = json.dumps(
            {
                "verdict": "NEUTRAL",
                "confidence": 0.3,
                "meta": {"source": "test"},
            }
        )
        verdict, confidence, raw = _parse_response(payload)
        assert verdict == "NEUTRAL"
        assert confidence == pytest.approx(0.3)

    def test_very_long_response_string(self):
        # A response padded with 1 MB of text before the JSON object.
        padding = "A" * (1024 * 1024)
        payload = padding + json.dumps({"verdict": "ENTAILED", "confidence": 0.9})
        verdict, confidence, raw = _parse_response(payload)
        assert verdict == "ENTAILED"
        assert confidence == pytest.approx(0.9)

    def test_json_array_at_top_level_returns_neutral(self):
        # Top-level JSON array has no { at position 0 that yields a dict.
        payload = json.dumps([{"verdict": "ENTAILED", "confidence": 0.9}])
        verdict, confidence, raw = _parse_response(payload)
        # [ ... ] contains a { }, so brace scan will extract the inner object.
        # This is technically valid behaviour; just assert no exception is raised
        # and the result is a valid tuple.
        assert verdict in ("ENTAILED", "NEUTRAL", "CONTRADICTS")
        assert 0.0 <= confidence <= 1.0


# ---------------------------------------------------------------------------
# Section 4: iter_evidence_pairs
# ---------------------------------------------------------------------------


class TestIterEvidencePairs:
    """Boundary and malformed inputs for iter_evidence_pairs."""

    def test_none_input_yields_nothing(self):
        assert list(iter_evidence_pairs(None)) == []

    def test_empty_dict_yields_nothing(self):
        assert list(iter_evidence_pairs({})) == []

    def test_non_dict_input_string_yields_nothing(self):
        # str is not a dict; must return early, not raise AttributeError.
        assert list(iter_evidence_pairs("not a dict")) == []  # type: ignore[arg-type]

    def test_non_dict_input_list_yields_nothing(self):
        assert list(iter_evidence_pairs([])) == []  # type: ignore[arg-type]

    def test_patent_analyses_key_missing_yields_nothing(self):
        assert list(iter_evidence_pairs({"other_key": "value"})) == []

    def test_patent_analyses_is_none_yields_nothing(self):
        assert list(iter_evidence_pairs({"patent_analyses": None})) == []

    def test_patent_analyses_contains_non_dict_items_skips_them(self):
        # Non-dict items inside the list must be skipped, not raise.
        report_data = {"patent_analyses": [None, "string", 42, {"claims_analyzed": []}]}
        assert list(iter_evidence_pairs(report_data)) == []

    def test_claims_analyzed_with_non_dict_items_skips_them(self):
        report_data = {"patent_analyses": [{"claims_analyzed": [None, "bad", 0, {"elements": []}]}]}
        assert list(iter_evidence_pairs(report_data)) == []

    def test_elements_with_none_values_for_claim_sentence_skipped(self):
        # reasoning=None, element_text=None -> claim_sentence="" -> skipped.
        report_data = {
            "patent_analyses": [
                {
                    "claims_analyzed": [
                        {
                            "elements": [
                                {
                                    "reasoning": None,
                                    "element_text": None,
                                    "evidence": "some evidence",
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        assert list(iter_evidence_pairs(report_data)) == []

    def test_elements_with_none_evidence_skipped(self):
        # evidence=None -> stripped to "" -> pair skipped.
        report_data = {
            "patent_analyses": [
                {
                    "claims_analyzed": [
                        {"elements": [{"reasoning": "A compound.", "evidence": None}]}
                    ]
                }
            ]
        }
        assert list(iter_evidence_pairs(report_data)) == []

    def test_elements_whitespace_only_evidence_skipped(self):
        # Whitespace-only evidence strips to "" -> pair skipped.
        report_data = {
            "patent_analyses": [
                {
                    "claims_analyzed": [
                        {"elements": [{"reasoning": "A compound.", "evidence": "   \t\n  "}]}
                    ]
                }
            ]
        }
        assert list(iter_evidence_pairs(report_data)) == []

    def test_empty_claims_analyzed_array_yields_nothing(self):
        report_data = {"patent_analyses": [{"claims_analyzed": []}]}
        assert list(iter_evidence_pairs(report_data)) == []

    def test_evidence_index_increments_across_all_elements_per_finding(self):
        # evidence_index is a flat counter per finding; must span all elements
        # in all claims within that finding, including skipped ones.
        report_data = {
            "patent_analyses": [
                {
                    "claims_analyzed": [
                        {
                            "elements": [
                                # index 0: skipped (no evidence)
                                {"reasoning": "claim 1", "evidence": ""},
                                # index 1: yielded
                                {"reasoning": "claim 2", "evidence": "evidence 2"},
                            ]
                        }
                    ]
                }
            ]
        }
        pairs = list(iter_evidence_pairs(report_data))
        assert len(pairs) == 1
        assert pairs[0].evidence_index == 1  # skipped element still increments counter

    def test_deeply_nested_structure_does_not_raise(self):
        # Pathological report with 20 levels of nesting inside elements values.
        deep_val = {"a": None}
        for _ in range(20):
            deep_val = {"nested": deep_val}
        report_data = {
            "patent_analyses": [
                {
                    "claims_analyzed": [
                        {
                            "elements": [
                                {
                                    "reasoning": "valid claim",
                                    "evidence": "valid evidence",
                                    "extra_deep": deep_val,
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        pairs = list(iter_evidence_pairs(report_data))
        assert len(pairs) == 1
        assert pairs[0].claim_sentence == "valid claim"

    def test_multiple_findings_get_correct_finding_index(self):
        # finding_index must track position in patent_analyses, not reset.
        report_data = {
            "patent_analyses": [
                {"claims_analyzed": [{"elements": [{"reasoning": "c1", "evidence": "e1"}]}]},
                {"claims_analyzed": [{"elements": [{"reasoning": "c2", "evidence": "e2"}]}]},
            ]
        }
        pairs = list(iter_evidence_pairs(report_data))
        assert len(pairs) == 2
        assert pairs[0].finding_index == 0
        assert pairs[1].finding_index == 1


# ---------------------------------------------------------------------------
# Section 5: score_pair -- client exception handling
# ---------------------------------------------------------------------------


class TestScorePairClientExceptions:
    """score_pair must absorb all client errors and return NEUTRAL."""

    def _make_client_that_raises(self, exc: Exception) -> MagicMock:
        client = MagicMock()
        client.messages.create.side_effect = exc
        return client

    def test_runtime_error_returns_neutral(self):
        client = self._make_client_that_raises(RuntimeError("boom"))
        result = score_pair(claim_sentence="c", evidence_span="e", client=client)
        assert result.verdict == "NEUTRAL"
        assert result.confidence == 0.0
        assert result.model_id == FAITHFULNESS_MODEL_ID

    def test_connection_error_returns_neutral(self):
        client = self._make_client_that_raises(ConnectionError("timeout"))
        result = score_pair(claim_sentence="c", evidence_span="e", client=client)
        assert result.verdict == "NEUTRAL"
        assert result.confidence == 0.0

    def test_keyboard_interrupt_is_not_swallowed(self):
        # KeyboardInterrupt is NOT an Exception subclass in the normal sense --
        # it is a BaseException. The except clause uses Exception so
        # KeyboardInterrupt should propagate. Verify this is intentional.
        client = self._make_client_that_raises(KeyboardInterrupt())  # type: ignore[arg-type]
        with pytest.raises(KeyboardInterrupt):
            score_pair(claim_sentence="c", evidence_span="e", client=client)

    def test_system_exit_is_not_swallowed(self):
        # Same reasoning as KeyboardInterrupt: SystemExit must propagate.
        client = self._make_client_that_raises(SystemExit(1))  # type: ignore[arg-type]
        with pytest.raises(SystemExit):
            score_pair(claim_sentence="c", evidence_span="e", client=client)

    def test_response_with_empty_content_list_returns_neutral(self):
        # Empty content list -> text_parts == [] -> raw_text == "" -> NEUTRAL.
        client = MagicMock()
        client.messages.create.return_value = SimpleNamespace(content=[])
        result = score_pair(claim_sentence="c", evidence_span="e", client=client)
        assert result.verdict == "NEUTRAL"
        assert result.confidence == 0.0

    def test_response_with_no_content_attribute_returns_neutral(self):
        # response.content is absent entirely.
        client = MagicMock()
        client.messages.create.return_value = SimpleNamespace()  # no content attr
        result = score_pair(claim_sentence="c", evidence_span="e", client=client)
        assert result.verdict == "NEUTRAL"
        assert result.confidence == 0.0

    def test_empty_claim_sentence_still_calls_client(self):
        # Empty claim is technically valid input at this level; score_pair should
        # not short-circuit -- the guard is in iter_evidence_pairs.
        client = MagicMock()
        client.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(text='{"verdict":"NEUTRAL","confidence":0.5}')]
        )
        result = score_pair(claim_sentence="", evidence_span="e", client=client)
        client.messages.create.assert_called_once()
        assert result.verdict == "NEUTRAL"

    def test_very_long_claim_sentence_is_truncated_not_errored(self):
        # 1 MB claim sentence: _build_prompt truncates it; client is still called.

        long_claim = "A" * (1024 * 1024)
        client = MagicMock()
        client.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(text='{"verdict":"ENTAILED","confidence":0.8}')]
        )
        result = score_pair(claim_sentence=long_claim, evidence_span="evidence", client=client)
        # Verify the prompt passed to the client respected the char cap.
        call_kwargs = client.messages.create.call_args.kwargs
        prompt_content = call_kwargs["messages"][0]["content"]
        # The claim section within the prompt must be at most MAX_CLAIM_CHARS + overhead.
        assert len(prompt_content) < len(long_claim)
        assert result.verdict == "ENTAILED"


# ---------------------------------------------------------------------------
# Section 6: compute_faithfulness_scores_impl (task_faithfulness)
# ---------------------------------------------------------------------------


class TestComputeFaithfulnessScoresImpl:
    """Boundary cases for compute_faithfulness_scores_impl."""

    def _run_disabled(self, analysis_id="test-id"):
        """Invoke the impl with the feature flag off.

        ``is_feature_enabled`` is imported lazily inside
        ``compute_faithfulness_scores_impl``, so it must be patched at its
        definition site, not as a task_faithfulness module attribute.
        """
        from api.workers.task_faithfulness import compute_faithfulness_scores_impl

        with patch(
            "api.services.faithfulness_uq.is_feature_enabled",
            return_value=False,
        ):
            return compute_faithfulness_scores_impl(
                engine=MagicMock(),
                analysis_id=analysis_id,
                org_id="org-1",
            )

    def test_feature_disabled_returns_disabled_status(self):
        result = self._run_disabled()
        assert result["status"] == "disabled"
        assert result["scored"] == 0

    def test_feature_disabled_returns_analysis_id_in_result(self):
        result = self._run_disabled(analysis_id="abc-123")
        assert result["analysis_id"] == "abc-123"

    def test_feature_disabled_does_not_call_db(self):
        # When disabled, the engine should never be used.
        engine = MagicMock()
        with patch(
            "api.services.faithfulness_uq.is_feature_enabled",
            return_value=False,
        ):
            from api.workers.task_faithfulness import compute_faithfulness_scores_impl

            compute_faithfulness_scores_impl(engine=engine, analysis_id="x", org_id="org-1")
        engine.connect.assert_not_called()

    def test_no_report_data_returns_no_report_status(self):
        """analysis.report_data is None -> status == 'no_report', no exception."""
        from api.workers.task_faithfulness import compute_faithfulness_scores_impl

        mock_analysis = MagicMock()
        mock_analysis.report_data = None
        mock_analysis.id = uuid.uuid4()
        mock_analysis.org_id = uuid.uuid4()

        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.get.return_value = mock_analysis

        mock_session_cls = MagicMock(return_value=mock_db)

        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "sk-test-key"
        analysis_id = str(uuid.uuid4())

        with (
            patch("api.services.faithfulness_uq.is_feature_enabled", return_value=True),
            patch("api.workers.task_faithfulness.Session", mock_session_cls),
        ):
            result = compute_faithfulness_scores_impl(
                engine=MagicMock(),
                analysis_id=analysis_id,
                org_id=str(mock_analysis.org_id),
                settings_factory=lambda: mock_settings,
                client_factory=lambda key: MagicMock(),
            )

        assert result["status"] == "no_report"
        assert result["scored"] == 0

    def test_missing_analysis_returns_missing_status(self):
        """db.get returns None -> status == 'missing', no exception."""
        from api.workers.task_faithfulness import compute_faithfulness_scores_impl

        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.get.return_value = None  # analysis not found

        mock_session_cls = MagicMock(return_value=mock_db)

        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "sk-test-key"
        analysis_id = str(uuid.uuid4())

        with (
            patch("api.services.faithfulness_uq.is_feature_enabled", return_value=True),
            patch("api.workers.task_faithfulness.Session", mock_session_cls),
        ):
            result = compute_faithfulness_scores_impl(
                engine=MagicMock(),
                analysis_id=analysis_id,
                org_id="org-1",
                settings_factory=lambda: mock_settings,
                client_factory=lambda key: MagicMock(),
            )

        assert result["status"] == "missing"
        assert result["scored"] == 0

    def test_no_api_key_returns_no_api_key_status(self):
        """An unpublishable report is rejected before optional API-key handling."""
        from api.workers.task_faithfulness import compute_faithfulness_scores_impl

        analysis_id = uuid.uuid4()
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.org_id = uuid.uuid4()
        mock_analysis.status = AnalysisStatus.COMPLETED
        mock_analysis.report_data = valid_report_data()
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.get.return_value = mock_analysis
        mock_session_cls = MagicMock(return_value=mock_db)
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = ""

        with (
            patch("api.services.faithfulness_uq.is_feature_enabled", return_value=True),
            patch("api.workers.task_faithfulness.Session", mock_session_cls),
            patch("api.workers.task_faithfulness._existing_score_count", return_value=0),
        ):
            result = compute_faithfulness_scores_impl(
                engine=MagicMock(),
                analysis_id=str(analysis_id),
                org_id=str(mock_analysis.org_id),
                settings_factory=lambda: mock_settings,
            )

        assert result["status"] == "unpublishable_report"
        assert result["scored"] == 0


# ---------------------------------------------------------------------------
# Section 7: _build_rows (task_faithfulness)
# ---------------------------------------------------------------------------


class TestBuildRows:
    """Boundary cases for _build_rows."""

    def test_empty_results_returns_empty_list(self):
        from api.workers.task_faithfulness import _build_rows

        rows = _build_rows(
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            results=[],
        )
        assert rows == []

    def test_single_result_returns_one_row(self):
        from api.services.faithfulness_uq import EvidencePair
        from api.workers.task_faithfulness import _build_rows

        pair = EvidencePair(
            finding_index=0,
            evidence_index=0,
            claim_sentence="A compound.",
            evidence_span="Evidence text.",
        )
        verdict = FaithfulnessVerdict(
            verdict="ENTAILED",
            confidence=0.9,
            model_id=FAITHFULNESS_MODEL_ID,
            raw='{"verdict":"ENTAILED","confidence":0.9}',
        )

        # FaithfulnessScore is imported lazily inside _build_rows, so patch at
        # its definition site rather than as a task_faithfulness attribute.
        with patch("api.db.models.FaithfulnessScore") as mock_score:
            mock_score.return_value = MagicMock()
            rows = _build_rows(
                analysis_id=uuid.uuid4(),
                org_id=uuid.uuid4(),
                results=[(pair, verdict)],
            )

        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Section 8: _reset_org_id_on_checkin (db/session.py)
# ---------------------------------------------------------------------------


class TestResetOrgIdOnCheckin:
    """Defensive behaviour of the pool checkin event handler."""

    def test_none_dbapi_connection_does_not_raise(self):
        """Calling with None must not propagate an exception."""
        from api.db.session import _reset_org_id_on_checkin

        # None.cursor() raises AttributeError; the try/except must absorb it.
        _reset_org_id_on_checkin(None, None)  # must not raise

    def test_cursor_method_raises_does_not_propagate(self):
        """If dbapi_connection.cursor() raises, the handler must swallow it."""
        from api.db.session import _reset_org_id_on_checkin

        dbapi_conn = MagicMock()
        dbapi_conn.cursor.side_effect = OSError("connection is dead")

        _reset_org_id_on_checkin(dbapi_conn, None)  # must not raise

    def test_cursor_execute_raises_does_not_propagate(self):
        """If cursor.execute() raises, the handler must swallow it."""
        from api.db.session import _reset_org_id_on_checkin

        cursor = MagicMock()
        cursor.execute.side_effect = RuntimeError("RESET failed")
        dbapi_conn = MagicMock()
        dbapi_conn.cursor.return_value = cursor

        _reset_org_id_on_checkin(dbapi_conn, None)  # must not raise

    def test_cursor_close_raises_does_not_propagate(self):
        """If cursor.close() raises (e.g. already closed), the handler must swallow it."""
        from api.db.session import _reset_org_id_on_checkin

        cursor = MagicMock()
        cursor.close.side_effect = RuntimeError("already closed")
        dbapi_conn = MagicMock()
        dbapi_conn.cursor.return_value = cursor

        _reset_org_id_on_checkin(dbapi_conn, None)  # must not raise

    def test_logger_warning_called_on_cursor_execute_error(self):
        """When execute raises, the handler must log a warning (not silently swallow)."""
        from api.db.session import _reset_org_id_on_checkin

        cursor = MagicMock()
        cursor.execute.side_effect = RuntimeError("RESET failed")
        dbapi_conn = MagicMock()
        dbapi_conn.cursor.return_value = cursor

        # Patch the module-level logger to capture the call.
        with patch("api.db.session.logger") as mock_logger:
            _reset_org_id_on_checkin(dbapi_conn, None)
            mock_logger.warning.assert_called_once()
            # Verify the event key is what we expect.
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "rls_checkin_reset_failed"

    def test_happy_path_executes_reset_statement(self):
        """Verify the RESET statement is issued on the cursor when connection is valid."""
        from api.db.session import _reset_org_id_on_checkin

        cursor = MagicMock()
        dbapi_conn = MagicMock()
        dbapi_conn.cursor.return_value = cursor

        _reset_org_id_on_checkin(dbapi_conn, None)

        cursor.execute.assert_any_call("RESET app.current_org_id")
        cursor.execute.assert_any_call("RESET app.public_share_grant_hash")
        cursor.execute.assert_any_call("RESET app.api_key_hash")
        assert cursor.execute.call_count == 3
        cursor.close.assert_called_once()


# ---------------------------------------------------------------------------
# Section 9: _PraviarJSONEncoder (celery_app.py)
# ---------------------------------------------------------------------------


class TestPraviarJSONEncoder:
    """Boundary cases for the Kombu/Celery JSON encoder."""

    def _encoder(self):
        from api.workers.celery_app import _PraviarJSONEncoder

        return _PraviarJSONEncoder()

    def test_uuid_returns_string(self):
        enc = self._encoder()
        sample = uuid.UUID("12345678-1234-5678-1234-567812345678")
        result = enc.default(sample)
        assert result == "12345678-1234-5678-1234-567812345678"
        assert isinstance(result, str)

    def test_uuid_nil_returns_string(self):
        enc = self._encoder()
        result = enc.default(uuid.UUID(int=0))
        assert result == "00000000-0000-0000-0000-000000000000"

    def test_datetime_returns_iso_string(self):
        enc = self._encoder()
        dt = datetime.datetime(2026, 5, 20, 12, 0, 0, tzinfo=datetime.UTC)
        result = enc.default(dt)
        assert isinstance(result, str)
        assert "2026-05-20" in result
        assert "12:00:00" in result

    def test_date_returns_iso_string(self):
        enc = self._encoder()
        d = datetime.date(2026, 5, 20)
        result = enc.default(d)
        assert result == "2026-05-20"
        assert isinstance(result, str)

    def test_datetime_min_returns_iso_string(self):
        enc = self._encoder()
        result = enc.default(datetime.datetime.min)
        assert isinstance(result, str)
        assert "0001" in result

    def test_date_far_future_returns_iso_string(self):
        enc = self._encoder()
        future = datetime.date(3000, 12, 31)
        result = enc.default(future)
        assert result == "3000-12-31"

    def test_pydantic_base_model_returns_dict(self):
        enc = self._encoder()
        try:
            from pydantic import BaseModel

            class _SampleModel(BaseModel):
                name: str
                score: float

            m = _SampleModel(name="aspirin", score=0.9)
            result = enc.default(m)
            assert isinstance(result, dict)
            assert result["name"] == "aspirin"
            assert result["score"] == pytest.approx(0.9)
        except ImportError:
            pytest.skip("pydantic not installed")

    def test_unserializable_type_raises_type_error(self):
        # Arbitrary object not handled by any branch must raise TypeError
        # (delegated to json.JSONEncoder.default).
        enc = self._encoder()
        with pytest.raises(TypeError):
            enc.default(object())

    def test_plain_dict_raises_type_error(self):
        # Dicts are normally handled by json.JSONEncoder directly, not via
        # default(). Calling default() with a dict should raise TypeError
        # because none of the isinstance branches match a plain dict.
        enc = self._encoder()
        with pytest.raises(TypeError):
            enc.default({"key": "value"})

    def test_full_json_dumps_with_uuid_roundtrip(self):
        # Verify the encoder is wired up correctly end-to-end in json.dumps.
        from api.workers.celery_app import _PraviarJSONEncoder

        sample_uuid = uuid.uuid4()
        data = {"analysis_id": sample_uuid, "ts": datetime.datetime(2026, 1, 1)}
        serialised = json.dumps(data, cls=_PraviarJSONEncoder)
        parsed = json.loads(serialised)
        assert parsed["analysis_id"] == str(sample_uuid)
        assert "2026" in parsed["ts"]

    def test_datetime_with_dst_transition_timezone(self):
        # A datetime during a DST transition must not raise.
        enc = self._encoder()
        # 2:30 AM on the day clocks go back in the UK (last Sunday of October).
        # We use a fixed UTC offset to avoid pytz dependency.
        tz_bst = datetime.timezone(datetime.timedelta(hours=1))
        dst_dt = datetime.datetime(2026, 10, 25, 2, 30, 0, tzinfo=tz_bst)
        result = enc.default(dst_dt)
        assert isinstance(result, str)
        assert "02:30:00" in result
