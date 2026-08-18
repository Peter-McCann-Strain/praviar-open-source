from __future__ import annotations

from pathlib import Path

import pytest

PROMPT_DIR = Path(__file__).resolve().parents[1] / "src" / "praviar_pipeline" / "prompts"

LEGAL_PROMPT_NAMES = (
    "claim_analysis_system.txt",
    "claim_analysis_agent_system.txt",
    "critic_system.txt",
    "critic_agent_system.txt",
    "doe_fwr_system.txt",
    "doe_fwr_screening_system.txt",
    "invalidity_screening_system.txt",
    "invalidity_system.txt",
    "multi_perspective_section.txt",
    "patent_narrative_system.txt",
    "perspective_business_analyst_system.txt",
    "perspective_patent_attorney_system.txt",
    "prior_art_agent_system.txt",
    "prosecution_agent_system.txt",
    "report_agent_system.txt",
    "report_judge_system.txt",
    "report_s1_executive.txt",
    "report_s2_key_patents.txt",
    "report_s3_damages_injunction.txt",
    "report_s4_invalidity.txt",
    "report_s5_recommendations.txt",
    "report_s6_data_quality.txt",
    "report_summary_system.txt",
    "report_verification_system.txt",
    "triage_system.txt",
)


def _read_prompts(names: tuple[str, ...]) -> dict[str, str]:
    return {name: (PROMPT_DIR / name).read_text(encoding="utf-8") for name in names}


@pytest.fixture(scope="module")
def claim_prompts() -> dict[str, str]:
    return _read_prompts(
        (
            "claim_analysis_system.txt",
            "claim_analysis_agent_system.txt",
        )
    )


@pytest.fixture(scope="module")
def legal_prompts() -> dict[str, str]:
    return _read_prompts(LEGAL_PROMPT_NAMES)


@pytest.mark.parametrize(
    "forbidden",
    (
        "PRESUMPTIVELY encompass prodrugs",
        "A prodrug IS a composition of the base compound",
        "Infringed by identical product regardless of process",
        "Infringed by manufacturing/selling for the claimed use",
        "Method claims infringed by manufacturing/selling",
        "Apply BROADEST reasonable claim construction",
        "If target enters scope only via dependent claim",
        'Single-agent does NOT infringe unless "comprising" covers',
    ),
)
def test_active_claim_prompts_exclude_overbroad_legal_rules(
    claim_prompts: dict[str, str],
    forbidden: str,
) -> None:
    for name, prompt in claim_prompts.items():
        assert forbidden not in prompt, f"{name} retained: {forbidden}"


def test_active_claim_prompts_preserve_current_infringement_contract(
    claim_prompts: dict[str, str],
) -> None:
    for _name, prompt in claim_prompts.items():
        assert "Phillips district-court claim-construction standard" in prompt
        assert "Hikma v. Amarin (2026)" in prompt
        assert "direct infringement by a third party" in prompt
        assert "affirmative steps that actively encourage" in prompt
        assert "Abbott Laboratories v. Sandoz" in prompt
        assert "every recited process limitation is limiting" in prompt
        assert "A dependent claim incorporates every" in prompt
        assert "does not erase" in prompt


def test_active_claim_prompts_keep_infringement_and_validity_distinct(
    claim_prompts: dict[str, str],
) -> None:
    for _name, prompt in claim_prompts.items():
        assert "For infringement" in prompt
        assert "For validity/patentability" in prompt
        assert "MPEP § 2113" in prompt


def test_patent_attorney_perspective_does_not_broaden_dependent_claims() -> None:
    prompt = (PROMPT_DIR / "perspective_patent_attorney_system.txt").read_text(encoding="utf-8")

    assert "It can never broaden the parent claim" in prompt
    assert "If the target fails any limitation of the parent claim" in prompt
    assert "may avoid an independent claim's broad genus" not in prompt


@pytest.mark.parametrize(
    "forbidden",
    (
        "Presumptively equivalent",
        "All FWR prongs pass unless",
        "estoppel blocks the DoE",
        "Salt form / polymorph equivalence → +0.1",
        "claims_unverifiable MUST be 0",
        "CLEAR risk with any MET",
        "Expired patents MUST be rated CLEAR",
        ("If an independent claim is NOT_MET but a dependent claim adds limitations that ARE met"),
        "defines the outer boundary",
        "amendments define scope boundary",
        "strengthens a CLEAR",
        "strengthens a HIGH",
        "This analysis constitutes notice",
        "This FTO analysis constitutes notice",
        "creates Halo willfulness exposure",
        "defensible against the willful-infringement standard",
        "defensible under the willful-infringement standard",
        "For pharmaceuticals, typical ranges are",
        "automatic stay of FDA approval",
        "automatic injunction-equivalent",
        '"renders obvious" not "may render obvious"',
        '"infringement probable" not "may infringe"',
        "Risk based on patent category",
        "Element-by-Element Analysis (inferred from title/abstract)",
        "Lost profits remedy available",
        "Reasonable royalty ceiling",
        "can elect lost profits",
        "practicing entity = higher",
        "NPE = lower",
        "patent is stronger on those grounds",
        "suggests willingness to license",
        "structural similarity creates a prima facie case",
        "Any narrowing arguments or amendments create",
        "resolve genuine ambiguity in favor of finding risk",
        "ALL FORESEEABLE",
        "coordinated scope extension",
        "individual patents may be weaker",
        "effect on patent scope",
        "3+ generic versions are already approved",
        "definitively non-blocking",
        "A new manufacturer would develop their own formulation",
        "FDA-recognized patent protection",
        "Use them with confidence",
        "The data has been verified upstream",
        "canonical risk levels in your context are the authoritative",
    ),
)
def test_active_legal_suite_excludes_discredited_cross_surface_rules(
    legal_prompts: dict[str, str],
    forbidden: str,
) -> None:
    for name, prompt in legal_prompts.items():
        assert forbidden not in prompt, f"{name} retained: {forbidden}"


def test_doe_prompts_require_case_specific_science_and_all_festo_routes() -> None:
    prompts = _read_prompts(("doe_fwr_system.txt", "doe_fwr_screening_system.txt"))

    for _name, prompt in prompts.items():
        lowered = prompt.lower()
        assert "no chemical or biologic class is presumptively equivalent" in lowered
        assert "eli lilly v. hospira" in lowered
        assert "all-limitations" in lowered
        assert "disclosure-dedication" in lowered
        assert "prior-art ensnarement" in lowered or "ensnare prior art" in lowered
        assert "unforeseeab" in lowered
        assert "tangential" in lowered
        assert "another reason" in lowered or "other reason" in lowered
        assert "uncertain" in lowered
        assert "never default to equivalent" in lowered


def test_claim_prompts_do_not_launder_prosecution_or_range_evidence(
    claim_prompts: dict[str, str],
) -> None:
    for _name, prompt in claim_prompts.items():
        assert "do not presume routine optimization" in prompt
        assert "full Graham analysis" in prompt
        assert "count or existence alone does not define scope" in prompt
        assert "number of narrowing amendments" in prompt


def test_critic_prompts_preserve_coverage_and_dependent_claim_logic() -> None:
    prompts = _read_prompts(("critic_system.txt", "critic_agent_system.txt"))

    for _name, prompt in prompts.items():
        assert "coverage separate from" in prompt
        assert "may retain MET elements" in prompt
        assert "inherited parent limitation is NOT_MET" in prompt
        assert "added MET limitation cannot cure" in prompt


def test_verification_fails_closed_on_unverifiable_customer_claims() -> None:
    prompt = _read_prompts(("report_verification_system.txt",))["report_verification_system.txt"]

    assert "Record every material attempted factual claim" in prompt
    assert "Never relabel an" in prompt
    assert "zero material unverifiable customer-visible claims" in prompt
    assert "overall_assessment to FAIL" in prompt
    output_schema = prompt.split("ASSESSMENT THRESHOLDS:", maxsplit=1)[0]
    assert (
        '"claims_unverifiable": <number the available authoritative evidence cannot confirm>'
    ) in output_schema
    assert "claims_unverifiable = 0 for all material customer-visible claims" in prompt


def test_willfulness_prompts_preserve_knowledge_intent_and_section_298() -> None:
    prompts = _read_prompts(
        (
            "perspective_business_analyst_system.txt",
            "report_agent_system.txt",
            "report_s3_damages_injunction.txt",
            "report_summary_system.txt",
        )
    )

    for _name, prompt in prompts.items():
        assert "knowledge and continued activity alone do not establish willfulness" in prompt
        assert "intentionally infringed" in prompt or "intentional infringement" in prompt
        assert "discretionary" in prompt
        assert "35 U.S.C. § 298" in prompt


def test_paragraph_iv_prompts_require_timely_qualifying_suit() -> None:
    prompts = _read_prompts(
        (
            "perspective_business_analyst_system.txt",
            "report_s3_damages_injunction.txt",
        )
    )

    for _name, prompt in prompts.items():
        assert "qualifying infringement action within 45 days" in prompt
        assert "Paragraph IV" in prompt
        assert "patent expiry" in prompt


def test_report_prompts_retain_material_uncertainty() -> None:
    executive = _read_prompts(("report_s1_executive.txt",))["report_s1_executive.txt"]
    invalidity = _read_prompts(("report_s4_invalidity.txt",))["report_s4_invalidity.txt"]

    assert "Never stylistically erase genuine uncertainty" in executive
    assert "Literal infringement cannot be concluded" in executive
    assert "calibrate invalidity language" in invalidity
    assert "complete Graham record" in invalidity


def test_missing_claim_text_blocks_coverage_in_every_report_layer() -> None:
    prompts = _read_prompts(
        (
            "report_s1_executive.txt",
            "report_s2_key_patents.txt",
            "report_summary_system.txt",
        )
    )

    assert (
        "title, abstract, or category cannot substitute for the claims"
        in prompts["report_s1_executive.txt"]
    )
    assert (
        "No element status, literal-coverage finding, DoE theory"
        in prompts["report_s2_key_patents.txt"]
    )
    assert "Claim-Level Decision: BLOCKED" in prompts["report_s2_key_patents.txt"]
    assert "claim text is unavailable" in prompts["report_summary_system.txt"]
    assert (
        "risk, DoE, and design-around conclusions are therefore unavailable"
        in prompts["report_summary_system.txt"]
    )


def test_market_entry_and_pct_opinions_never_replace_claim_analysis() -> None:
    prompts = _read_prompts(("critic_system.txt", "critic_agent_system.txt"))

    for _name, prompt in prompts.items():
        assert "Generic or biosimilar entry is market-history evidence" in prompt or (
            "Generic/biosimilar entry is market history" in prompt
        )
        assert "not a" in prompt
        assert "nonbinding" in prompt
        assert "never convert" in prompt or "never translate" in prompt


def test_damages_and_injunction_prompts_reject_entity_shortcuts() -> None:
    prompts = _read_prompts(
        (
            "perspective_business_analyst_system.txt",
            "report_s3_damages_injunction.txt",
            "report_summary_system.txt",
        )
    )

    for _name, prompt in prompts.items():
        assert "but-for causation" in prompt
        assert "reasonable royalty is" in prompt
        assert "statutory" in prompt and "floor" in prompt
        assert "categorical rules" in prompt
        assert "balance of equities" in prompt
        assert "public interest" in prompt


def test_ptab_prompts_preserve_scope_finality_and_discretionary_denial() -> None:
    invalidity = _read_prompts(("report_s4_invalidity.txt",))["report_s4_invalidity.txt"]
    summary = _read_prompts(("report_summary_system.txt",))["report_summary_system.txt"]
    critic = _read_prompts(("critic_system.txt",))["critic_system.txt"]

    assert "35 U.S.C. § 311(b)" in invalidity
    assert "only §§ 102/103 grounds" in invalidity
    assert "Director review/rehearing" in invalidity
    assert "Discretionary denial may be unrelated to merits" in invalidity
    assert "35 U.S.C. § 311(b)" in summary
    assert "discretionary denial may be unrelated to merits" in summary
    assert "Discretionary denial may be unrelated to merits" in critic


def test_prosecution_prompts_apply_complete_festo_record_without_class_rules() -> None:
    prompts = _read_prompts(
        (
            "multi_perspective_section.txt",
            "perspective_patent_attorney_system.txt",
            "prosecution_agent_system.txt",
        )
    )

    for _name, prompt in prompts.items():
        lowered = prompt.lower()
        assert "patentability-related narrowing amendment" in lowered
        assert "rebutt" in lowered
        assert "unforeseeab" in lowered
        assert "tangential" in lowered
        assert "other reason" in lowered or "every festo rebuttal route" in lowered

    prosecution = prompts["prosecution_agent_system.txt"]
    assert "No salt, counterion, excipient, polymorph" in prosecution
    assert "mere mention or a category label does not automatically trigger" in prosecution


def test_triage_fails_closed_before_claim_analysis() -> None:
    triage = _read_prompts(("triage_system.txt",))["triage_system.txt"]

    assert "do not discard an expressly claimed alternative" in triage
    assert "Generic approvals, competitor count, or market entry never make" in triage
    assert "do not use them to remove a claim from retrieval" in triage
    assert "Do not assume a future manufacturer will avoid" in triage
    assert (
        "Use NOT_RELEVANT only when authoritative claim evidence affirmatively excludes" in triage
    )


def test_terminal_disclaimer_surfaces_never_expand_scope_or_infer_weakness() -> None:
    prompts = _read_prompts(
        (
            "patent_narrative_system.txt",
            "perspective_business_analyst_system.txt",
            "perspective_patent_attorney_system.txt",
        )
    )

    assert "does not extend claim scope" in prompts["patent_narrative_system.txt"]
    assert "does not extend claim scope" in prompts["perspective_business_analyst_system.txt"]
    assert "does not by itself make invalidity" in prompts["perspective_patent_attorney_system.txt"]
    assert "Do not infer weakness" in prompts["perspective_business_analyst_system.txt"]


def test_data_quality_surfaces_treat_upstream_values_as_attributed_inputs() -> None:
    summary = _read_prompts(("report_summary_system.txt",))["report_summary_system.txt"]
    quality = _read_prompts(("report_s6_data_quality.txt",))["report_s6_data_quality.txt"]

    assert "attributed input, not proof of authoritative truth" in summary
    assert "Upstream presence is not proof of verification" in quality
    assert "mark the decision UNCLEAR/BLOCKED" in quality


def test_scenario_contracts_fail_closed_across_legal_surfaces() -> None:
    prompts = _read_prompts(
        (
            "claim_analysis_system.txt",
            "critic_system.txt",
            "doe_fwr_system.txt",
            "report_verification_system.txt",
        )
    )

    claim = prompts["claim_analysis_system.txt"]
    critic = prompts["critic_system.txt"]
    doe = prompts["doe_fwr_system.txt"]
    verification = prompts["report_verification_system.txt"]

    # Distinct salts with different dissolution or activation receive no
    # class-wide equivalence shortcut.
    assert "No chemical or biologic class is presumptively equivalent" in doe
    assert "dissolution" in doe
    assert "activation" in doe

    # A Festo tangentiality showing can rebut the presumption of surrender.
    assert "TANGENTIALITY" in doe
    assert "rebuttable presumption" in doe

    # Literal coverage survives verified expiry even when forward exposure does not.
    assert "retain the coverage finding" in claim
    assert "may retain MET elements" in critic

    # An unavailable material source is surfaced as a failed verification.
    assert "unverifiable" in verification
    assert "overall_assessment to FAIL" in verification

    # An added dependent limitation cannot rescue a failed inherited limitation.
    assert "added MET limitation cannot cure" in critic
