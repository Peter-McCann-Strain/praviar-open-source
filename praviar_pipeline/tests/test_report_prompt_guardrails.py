"""Prompt guardrails for source scope, missing claims, and reliance language."""

from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parents[1] / "src" / "praviar_pipeline" / "prompts"


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def test_report_prompts_require_scope_and_reliance_tool() -> None:
    for name in (
        "report_s1_executive.txt",
        "report_s5_recommendations.txt",
        "report_s6_data_quality.txt",
    ):
        assert "get_report_scope_and_reliance" in _prompt(name)


def test_report_prompts_do_not_reintroduce_privilege_or_coverage_overclaims() -> None:
    text = "\n".join(_prompt(path.name) for path in PROMPT_DIR.glob("report_*.txt"))

    forbidden = (
        "PRIVILEGED AND CONFIDENTIAL",
        "ATTORNEY WORK PRODUCT",
        "jurisdictions covered",
        "covered jurisdictions",
        "List databases searched",
        "List jurisdictions covered",
        "infer likely claim scope",
        "compound likely falls within",
    )
    for phrase in forbidden:
        assert phrase not in text


def test_missing_claim_text_prompt_forbids_element_status_inference() -> None:
    s2 = _prompt("report_s2_key_patents.txt")
    assert "Do not infer MET/NOT_MET/AMBIGUOUS element statuses" in s2
    assert "Element-level analysis is unavailable in this artifact" in s2


def test_data_quality_prompt_never_upgrades_zero_claim_text_to_clear() -> None:
    s6 = _prompt("report_s6_data_quality.txt")
    assert "0 of 25 analyzed patents had claims text" in s6
    assert "this is acceptable" not in s6.lower()
    assert "CONFIDENCE: HIGH for CLEAR" not in s6
    assert "cannot support element-level infringement analysis or a CLEAR" in s6
