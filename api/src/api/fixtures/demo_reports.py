# ruff: noqa: E501
"""Legacy development and component-test reports.

Every organization, person, publication identifier, legal record, citation,
and conclusion below is synthetic. Real chemistry terms are neutral test inputs
only. The seed CLI uses :func:`showcase_report`; these legacy factories are not
the canonical showcase and are not release evidence.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime

from praviar_pipeline.models.patent import PatentSource, build_claim_text_provenance
from praviar_pipeline.models.report import (
    ClaimProgramDecision,
    ClaimProgramSummary,
    MatterEvidenceIndex,
)
from praviar_pipeline.pipeline.report.blocker_family_records import (
    build_blocker_family_records,
)
from praviar_pipeline.pipeline.runtime.evidence_policy import COMPONENT_TO_CATEGORY
from praviar_pipeline.showcase_fixture import (
    load_showcase_fixture,
    showcase_fixture_receipt,
    showcase_publication_id,
)
from praviar_pipeline.utils.patent_ids import publication_jurisdiction


def _verification_ok() -> dict:
    return {
        "checks": [
            {
                "check_name": "citations",
                "passed": True,
                "severity": "pass",
                "details": "All synthetic publication identifiers match the fixture matter record; no live register resolution is claimed.",
            },
            {
                "check_name": "claims_grounded",
                "passed": True,
                "severity": "pass",
                "details": "Synthetic claim excerpts remain internally consistent with the fixture source text.",
            },
            {
                "check_name": "risk_levels_justified",
                "passed": True,
                "severity": "pass",
                "details": "Risk labels remained consistent with element-level findings.",
            },
            {
                "check_name": "entity_validation",
                "passed": True,
                "severity": "pass",
                "details": "All fictional assignee and person labels satisfy the fixture schema.",
            },
        ],
        "all_citations_valid": True,
        "all_claims_grounded": True,
        "all_entities_valid": True,
        "dates_consistent": True,
        "risk_levels_justified": True,
        "issues": [],
    }


def _source_health(patent_ids: list[str]) -> dict:
    return {
        "entries": [
            {
                "source": "pubchem_sdq",
                "status": "ok",
                "patent_count": len(patent_ids),
                "error_message": "",
            },
            {
                "source": "bigquery",
                "status": "ok",
                "patent_count": len(patent_ids),
                "error_message": "",
            },
            {
                "source": "patentsview",
                "status": "ok",
                "patent_count": len(patent_ids),
                "error_message": "",
            },
            {
                "source": "epo_ops",
                "status": "failed",
                "patent_count": 0,
                "error_message": "Rate limit exceeded",
            },
        ]
    }


def _search_funnel(
    all_patent_ids: list[str], triage_ids: list[str], analysis_ids: list[str]
) -> dict:
    funnel = []
    for pid in all_patent_ids:
        in_triage = pid in triage_ids
        funnel.append(
            {
                "patent_id": pid,
                "sources_found_in": ["pubchem_sdq", "bigquery"],
                "passed_hard_filter": True,
                "filter_reason": "",
                "composite_score": round(0.45 + (0.5 if in_triage else 0.0), 3),
                "bm25_score": round(0.38 + (0.4 if in_triage else 0.0), 3),
                "final_blend_score": round(0.42 + (0.45 if in_triage else 0.0), 3),
                "final_rank": triage_ids.index(pid) + 1 if in_triage else None,
                "included_in_triage": in_triage,
            }
        )
    return {
        "search_funnel": funnel,
        "triage_audit": [
            {
                "patent_id": pid,
                "relevance": "high" if pid in analysis_ids else "medium",
                "reason": "Claim scope overlaps compound structure or production process."
                if pid in analysis_ids
                else "Tangential relevance; retained for completeness.",
                "confidence": 0.85 if pid in analysis_ids else 0.62,
                "passed_triage": True,
            }
            for pid in triage_ids
        ],
        "analysis_audit": [
            {
                "patent_id": pid,
                "selected_for_analysis": True,
                "selection_reason": "Top-ranked by composite score after triage.",
                "risk_level": None,
                "selected_for_doe": True,
                "selected_for_invalidity": True,
            }
            for pid in analysis_ids
        ],
        "timing_data": [],
        "total_patents_discovered": len(all_patent_ids),
        "patents_after_hard_filter": len(all_patent_ids),
        "patents_after_ranking": len(triage_ids),
        "patents_after_triage": len(triage_ids),
        "patents_analyzed": len(analysis_ids),
    }


def _demo_family_id(patent_id: str) -> str:
    return f"demo-family-{patent_id}"


def _matter_graph(compound_name: str, patent_ids: list[str]) -> dict:
    nodes = [
        {
            "node_id": f"compound:{compound_name}",
            "node_type": "compound_variant",
            "label": compound_name,
        }
    ]
    edges = []
    for pid in patent_ids:
        fam = _demo_family_id(pid)
        nodes.append(
            {
                "node_id": f"patent:{pid}",
                "node_type": "patent",
                "label": pid,
                "jurisdiction": "US" if pid.startswith("US") else "WO",
                "patent_id": pid,
                "family_id": fam,
                "application_number": "",
            }
        )
        nodes.append(
            {"node_id": f"family:{fam}", "node_type": "family", "label": fam, "family_id": fam}
        )
        edges.append(
            {
                "edge_type": "roots",
                "from_node_id": f"compound:{compound_name}",
                "to_node_id": f"patent:{pid}",
                "summary": "material patent",
            }
        )
        edges.append(
            {
                "edge_type": "belongs_to_family",
                "from_node_id": f"patent:{pid}",
                "to_node_id": f"family:{fam}",
                "summary": "family context",
            }
        )
    return {"nodes": nodes, "edges": edges}


def _matter_graph_summary(compound_name: str, patent_ids: list[str]) -> dict:
    return {
        "root_compound": compound_name,
        "node_count": 1 + len(patent_ids) * 2,
        "edge_count": len(patent_ids) * 2,
        "node_counts_by_type": {
            "compound_variant": 1,
            "patent": len(patent_ids),
            "family": len(patent_ids),
        },
        "edge_counts_by_type": {"roots": len(patent_ids), "belongs_to_family": len(patent_ids)},
        "patent_node_ids": [f"patent:{pid}" for pid in patent_ids],
        "family_node_ids": [f"family:{_demo_family_id(patent_id)}" for patent_id in patent_ids],
    }


def _jurisdiction_decision(
    decision: str, confidence: float, patent_ids: list[str], blocking_ids: list[str]
) -> dict:
    return {
        "jurisdiction": "US",
        "decision": decision,
        "decision_confidence": confidence,
        "evidence_quality": min(round(confidence + 0.05, 2), 1.0),
        "evidence_sufficient_for_clearance": decision == "clear",
        "gate_failures": [] if decision == "clear" else ["Evidence indicates blocking risk."],
        "reviewed_patent_ids": patent_ids,
        "blocking_patent_ids": blocking_ids,
        "reasoning": [f"Reviewed {len(patent_ids)} material US patent(s)."],
    }


def _clearance_decision(
    decision: str, confidence: float, patent_ids: list[str], blocking_ids: list[str]
) -> dict:
    return {
        "decision": decision,
        "decision_confidence": confidence,
        "evidence_quality": min(round(confidence + 0.05, 2), 1.0),
        "decision_reasoning": ["Evidence reviewed across all material patents."],
        "decision_audit": {
            "queried_sources_count": 3,
            "successful_sources_count": 3,
            "material_patents_reviewed": len(patent_ids),
            "material_us_patents": len(patent_ids),
            "material_ep_patents": 0,
            "patents_with_claims": len(patent_ids),
            "patents_with_family": len(patent_ids),
            "us_patents_with_prosecution_context": len(patent_ids),
            "ep_patents_with_register_context": 0,
            "analysis_failures_count": 0,
            "authoritative_sources_count": 1,
            "clearance_grade_ready_patents": len(patent_ids) if decision == "clear" else 0,
            "incomplete_material_patents": 0 if decision == "clear" else 1,
            "clearance_grade_ready_families": len(patent_ids) if decision == "clear" else 0,
            "incomplete_material_families": 0 if decision == "clear" else 1,
            "failed_sources": ["epo_ops"],
            "evidence_sufficient_for_clearance": decision == "clear",
            "insufficiency_reasons": []
            if decision == "clear"
            else ["Blocking risk detected in one or more claims."],
            "evidence_warnings": [],
            "search_iterations": 2,
            "coverage_summary": {
                "queried_source_names": ["pubchem_sdq", "bigquery", "patentsview"],
                "successful_source_names": ["pubchem_sdq", "bigquery", "patentsview"],
                "failed_source_names": ["epo_ops"],
                "authoritative_source_names": ["patentsview"],
                "supporting_source_names": ["bigquery", "pubchem_sdq"],
                "reviewed_patent_ids": patent_ids,
                "reviewed_us_patent_ids": patent_ids,
                "reviewed_ep_patent_ids": [],
                "patents_missing_claims": [],
                "patents_missing_claim_level_analysis": [],
                "patents_missing_authoritative_records": [],
                "patents_missing_family_context": [],
                "us_patents_missing_prosecution_context": [],
                "ep_patents_missing_register_context": [],
                "failed_analysis_patent_ids": [],
                "clearance_grade_ready_patent_ids": patent_ids if decision == "clear" else [],
                "incomplete_patent_ids": [] if decision == "clear" else blocking_ids,
                "clearance_grade_ready_family_ids": [],
                "incomplete_family_ids": (
                    []
                    if decision == "clear"
                    else [_demo_family_id(patent_id) for patent_id in blocking_ids]
                ),
                "verification_gaps": [],
                "required_record_components": [
                    "claims_text",
                    "claim_level_analysis",
                    "authoritative_records",
                    "family_context",
                    "us_file_wrapper_dossier",
                    "verification",
                ],
            },
            "claim_program_summary": {
                "total_claim_programs_reviewed": len(patent_ids),
                "patent_level_fallback_count": 0,
                "blocking_claim_ids": [f"{pid}#claim1" for pid in blocking_ids],
                "contested_claim_ids": [],
                "medium_risk_claim_ids": [],
                "claims_with_strong_invalidity": [],
                "claims_with_insufficient_evidence": [],
                "blocking_patent_ids": blocking_ids,
                "contested_patent_ids": [],
                "medium_risk_patent_ids": [],
            },
            "decisive_references": [],
        },
    }


# ── Succinic acid ──────────────────────────────────────────────────────────────
# 5-patent analysis. Data from web/tests/fixtures/report-fixture.ts.
# Every assignee and legal record in this legacy fixture is synthetic.

_SA_PATENTS = [
    "US0000000001A1",
    "US0000000002A1",
    "US0000000003A1",
    "US0000000013A1",
    "US0000000012A1",
]
_SA_BLOCKING = ["US0000000001A1", "US0000000002A1"]
_SA_TRIAGE = _SA_PATENTS  # all 5 passed triage
_SA_ALL = [f"US{i + 100:010d}A1" for i in range(2412)] + _SA_PATENTS

_SA_PATENT_ANALYSES = [
    {
        "patent_id": "US0000000001A1",
        "title": "Methods for producing C4 dicarboxylic acids using engineered prokaryotic microorganisms",
        "assignee": "Fictional Meridian Therapeutics",
        "expiry_date": "2035-06-14",
        "claims_analyzed": [
            {
                "claim_number": 1,
                "claim_type": "independent",
                "depends_on": None,
                "preamble": "A method for producing a C4 dicarboxylic acid",
                "transitional_phrase": "comprising",
                "elements": [
                    {
                        "element_number": 1,
                        "element_text": "A method for producing a C4 dicarboxylic acid comprising culturing a recombinant prokaryotic microorganism",
                        "status": "met",
                        "reasoning": "The production process uses a recombinant E. coli strain (prokaryotic) to produce succinic acid (a C4 dicarboxylic acid). This element is clearly met.",
                        "confidence": 0.95,
                        "evidence": "Succinic acid is by definition a C4 dicarboxylic acid. E. coli is a prokaryote.",
                    },
                    {
                        "element_number": 2,
                        "element_text": "wherein the microorganism has been genetically modified to overexpress at least one gene in the reductive TCA branch",
                        "status": "met",
                        "reasoning": "Standard bio-succinic strains overexpress ppc and mdh, both in the reductive TCA branch.",
                        "confidence": 0.88,
                        "evidence": "Published literature on FX060/FX073 confirms overexpression of reductive TCA genes (Fictional Reference Alpha, Biotechnol Bioeng, 2008).",
                    },
                    {
                        "element_number": 3,
                        "element_text": "in a culture medium comprising a carbon source selected from glucose, glycerol, or sucrose at a concentration of 20-200 g/L",
                        "status": "met",
                        "reasoning": "Process uses glucose at 100 g/L, within the claimed 20-200 g/L range.",
                        "confidence": 0.92,
                        "evidence": "Process specification: glucose feed at 100 g/L initial concentration.",
                    },
                    {
                        "element_number": 4,
                        "element_text": "recovering the C4 dicarboxylic acid at a yield of at least 0.8 mol/mol carbon source",
                        "status": "not_met",
                        "reasoning": "Actual yields of 0.65-0.72 mol/mol fall below the 0.8 mol/mol threshold. However, the gap is narrow enough that process optimisation or doctrine of equivalents may close it.",
                        "confidence": 0.73,
                        "evidence": "Three production runs show yields of 0.65, 0.69, and 0.72 mol/mol respectively.",
                    },
                ],
                "overall_status": "partially_met",
                "overall_confidence": 0.87,
                "reasoning": "Three of four elements are met. The yield limitation (element 4) requiring ≥0.8 mol/mol is the only unmet element. Current yields of 0.65-0.72 mol/mol fall short but are close enough that process optimisation or doctrine of equivalents could close the gap.",
            },
            {
                "claim_number": 2,
                "claim_type": "dependent",
                "depends_on": 1,
                "preamble": "The method of claim 1",
                "transitional_phrase": "wherein",
                "elements": [
                    {
                        "element_number": 1,
                        "element_text": "The method of claim 1",
                        "status": "partially_met",
                        "reasoning": "Dependent on partially satisfied claim 1.",
                        "confidence": 0.75,
                        "evidence": "See analysis of claim 1.",
                    },
                    {
                        "element_number": 2,
                        "element_text": "wherein the microorganism further comprises a deletion of the ldhA gene encoding lactate dehydrogenase",
                        "status": "met",
                        "reasoning": "The E. coli production strain has a confirmed ldhA deletion to eliminate lactate byproduct.",
                        "confidence": 0.91,
                        "evidence": "Strain genotype records confirm ΔldhA.",
                    },
                ],
                "overall_status": "partially_met",
                "overall_confidence": 0.83,
                "reasoning": "Dependent claim 2 adds ldhA deletion, which is met. Overall risk driven by claim 1.",
            },
        ],
        "risk_level": "high",
        "risk_summary": "Three of four elements of independent claim 1 are met. The yield limitation is currently not met but within reach of process optimisation. High risk if yields improve or doctrine of equivalents applies.",
        "design_around_suggestions": [
            {
                "element_avoided": 1,
                "suggestion": "Use a eukaryotic host (e.g., Saccharomyces cerevisiae or Yarrowia lipolytica) to fall outside the claim scope limited to prokaryotic hosts.",
                "feasibility": "Moderate. Yeast-based succinic acid production has been demonstrated at pilot scale by Fictional Riverglass (Fictional Orbit/River joint venture).",
            },
        ],
        "orange_book_info": None,
        "model_used": "claude-sonnet-4-6",
        "thinking_text": "This patent presents a significant FTO concern. Three of four elements are clearly satisfied. The yield limitation provides the primary basis for non-infringement, but current yields are close enough that optimisation or measurement variability could push into the infringing range.",
        "input_tokens": 8432,
        "output_tokens": 2187,
    },
    {
        "patent_id": "US0000000002A1",
        "title": "Process for purification and crystallisation of bio-based succinic acid from fermentation broth",
        "assignee": "Fictional Atlas Chemistry",
        "expiry_date": "2033-11-22",
        "claims_analyzed": [
            {
                "claim_number": 1,
                "claim_type": "independent",
                "depends_on": None,
                "preamble": "A process for purifying succinic acid",
                "transitional_phrase": "comprising",
                "elements": [
                    {
                        "element_number": 1,
                        "element_text": "acidifying a fermentation broth containing succinic acid to a pH below 2.5 using a mineral acid",
                        "status": "met",
                        "reasoning": "Process acidifies clarified broth to pH 2.0 using sulfuric acid (mineral acid).",
                        "confidence": 0.93,
                        "evidence": "DSP protocol specifies acidification to pH 2.0 ± 0.1 with H₂SO₄.",
                    },
                    {
                        "element_number": 2,
                        "element_text": "crystallising the succinic acid by cooling from at least 60°C to below 10°C at a controlled cooling rate of 0.5-5°C per minute",
                        "status": "met",
                        "reasoning": "Production uses cooling crystallisation from 70°C to 4°C at ~2°C/min, within the claimed range.",
                        "confidence": 0.86,
                        "evidence": "Crystalliser logs: cooling from 68-72°C to 3-5°C at 1.8-2.2°C/min across five batches.",
                    },
                    {
                        "element_number": 3,
                        "element_text": "recovering crystalline succinic acid having a purity of at least 99.5% by weight",
                        "status": "partially_met",
                        "reasoning": "Final product purity averages 99.2-99.6% across batches. Some batches meet 99.5%, others fall slightly below.",
                        "confidence": 0.68,
                        "evidence": "HPLC CoA for lots SA-2025-001 through SA-2025-012: purity range 99.18-99.62%.",
                    },
                ],
                "overall_status": "partially_met",
                "overall_confidence": 0.82,
                "reasoning": "Both key process parameters (acidification and crystallisation) are met. Purity threshold of 99.5% is inconsistently met.",
            },
        ],
        "risk_level": "high",
        "risk_summary": "The cooling crystallisation process closely matches the claimed process. All key parameters fall within claim limitations. Product purity is borderline.",
        "design_around_suggestions": [
            {
                "element_avoided": 2,
                "suggestion": "Switch to reactive extraction with tri-n-octylamine (TOA) in 1-octanol, avoiding the crystallisation step entirely.",
                "feasibility": "High. TOA reactive extraction of succinic acid is well-established and used commercially.",
            },
        ],
        "orange_book_info": None,
        "model_used": "claude-sonnet-4-6",
        "thinking_text": "The Fictional Atlas crystallisation patent is concerning because the parameters closely match standard industrial practice. The purity limitation provides breathing room but is not a reliable basis for non-infringement.",
        "input_tokens": 6218,
        "output_tokens": 1843,
    },
    {
        "patent_id": "US0000000003A1",
        "title": "Engineered fungal strains for enzymatic conversion of fumaric acid to succinic acid",
        "assignee": "Fictional Nova Enzymes",
        "expiry_date": "2034-03-08",
        "claims_analyzed": [
            {
                "claim_number": 1,
                "claim_type": "independent",
                "depends_on": None,
                "preamble": "An engineered Aspergillus niger strain",
                "transitional_phrase": "comprising",
                "elements": [
                    {
                        "element_number": 1,
                        "element_text": "one or more heterologous nucleic acid sequences encoding a fumarase variant having at least 90% sequence identity to SEQ ID NO: 1",
                        "status": "not_met",
                        "reasoning": "Process uses E. coli, not Aspergillus niger. No heterologous fumarase has been introduced.",
                        "confidence": 0.91,
                        "evidence": "Production strain is E. coli with native fumarase activity; no heterologous fumarase introduced.",
                    },
                    {
                        "element_number": 2,
                        "element_text": "wherein the strain produces succinic acid at a titer of at least 40 g/L when cultured with fumaric acid as a substrate",
                        "status": "not_met",
                        "reasoning": "Process uses glucose, not fumaric acid, as primary carbon source.",
                        "confidence": 0.95,
                        "evidence": "Process documentation confirms glucose as sole carbon source.",
                    },
                ],
                "overall_status": "not_met",
                "overall_confidence": 0.93,
                "reasoning": "Neither element is met. The process uses a completely different organism (E. coli vs A. niger) and does not involve heterologous fumarase or fumaric acid as substrate.",
            },
        ],
        "risk_level": "medium",
        "risk_summary": "Claims directed to a fundamentally different production approach. However, claim 8 covers broader C4 dicarboxylic acid precursor methods, creating interpretive ambiguity around fumarate as a reductive TCA intermediate.",
        "design_around_suggestions": [
            {
                "element_avoided": 1,
                "suggestion": "Ensure production pathway documentation clearly demonstrates that fumaric acid is not used as a deliberate substrate or intermediate.",
                "feasibility": "High. This is primarily a documentation and claim construction issue.",
            },
        ],
        "orange_book_info": None,
        "model_used": "claude-sonnet-4-6",
        "thinking_text": "The Fictional Nova patent covers a different paradigm. The risk is interpretive: could a court construe the reductive TCA pathway as proceeding through fumaric acid as a precursor?",
        "input_tokens": 5891,
        "output_tokens": 1562,
    },
    {
        "patent_id": "US0000000013A1",
        "title": "Low-pH yeast fermentation process for organic acid production with in situ product removal",
        "assignee": "Fictional Orbit Fermentation",
        "expiry_date": "2031-08-19",
        "claims_analyzed": [
            {
                "claim_number": 1,
                "claim_type": "independent",
                "depends_on": None,
                "preamble": "A continuous fermentation process for producing an organic acid",
                "transitional_phrase": "comprising",
                "elements": [
                    {
                        "element_number": 1,
                        "element_text": "culturing a yeast strain of Saccharomyces cerevisiae at a pH below 3.0",
                        "status": "not_met",
                        "reasoning": "Process uses E. coli at pH 6.8, not S. cerevisiae at pH < 3.0.",
                        "confidence": 0.97,
                        "evidence": "Production organism is E. coli; operating pH is 6.8.",
                    },
                    {
                        "element_number": 2,
                        "element_text": "continuously removing the organic acid product using an integrated membrane separation unit",
                        "status": "not_met",
                        "reasoning": "Process is batch/fed-batch with downstream recovery. No integrated membrane separation.",
                        "confidence": 0.96,
                        "evidence": "Process operates in fed-batch mode with downstream recovery after completion.",
                    },
                    {
                        "element_number": 3,
                        "element_text": "wherein the organic acid is selected from succinic acid, fumaric acid, malic acid, or itaconic acid",
                        "status": "met",
                        "reasoning": "Succinic acid is explicitly listed in the claim.",
                        "confidence": 0.99,
                        "evidence": "Claim language expressly recites succinic acid.",
                    },
                ],
                "overall_status": "not_met",
                "overall_confidence": 0.95,
                "reasoning": "Two of three elements are unmet. Process uses E. coli (not yeast) in batch mode (not continuous) at neutral pH. Only product identity matches.",
            },
        ],
        "risk_level": "low",
        "risk_summary": "Although the claim recites succinic acid, process limitations (S. cerevisiae, pH < 3.0, continuous membrane separation) are all unmet. Risk is low.",
        "design_around_suggestions": [],
        "orange_book_info": None,
        "model_used": "claude-sonnet-4-6",
        "thinking_text": "Clear non-infringement on two of three elements. No design-around needed.",
        "input_tokens": 4203,
        "output_tokens": 987,
    },
    {
        "patent_id": "US0000000012A1",
        "title": "Electrochemical reduction of CO2 to produce C2-C4 carboxylic acids",
        "assignee": "Fictional Myria Corporation",
        "expiry_date": "2030-02-11",
        "claims_analyzed": [
            {
                "claim_number": 1,
                "claim_type": "independent",
                "depends_on": None,
                "preamble": "An electrochemical process for producing a C2-C4 carboxylic acid",
                "transitional_phrase": "comprising",
                "elements": [
                    {
                        "element_number": 1,
                        "element_text": "reducing carbon dioxide at a cathode comprising a metal catalyst selected from copper, tin, or bismuth in an aqueous electrolyte",
                        "status": "not_met",
                        "reasoning": "Production is biological fermentation, not electrochemical reduction. No cathode, metal catalyst, or electrolyte involved.",
                        "confidence": 0.99,
                        "evidence": "Production method is microbial fermentation; no electrochemical components present.",
                    },
                ],
                "overall_status": "not_met",
                "overall_confidence": 0.99,
                "reasoning": "Complete non-overlap. Electrochemical CO2 reduction has zero common elements with biological fermentation.",
            },
        ],
        "risk_level": "clear",
        "risk_summary": "This patent covers an entirely different production modality (electrochemical CO2 reduction) with no overlap with biological fermentation.",
        "design_around_suggestions": [],
        "orange_book_info": None,
        "model_used": "claude-sonnet-4-6",
        "thinking_text": "No overlap whatsoever.",
        "input_tokens": 3102,
        "output_tokens": 654,
    },
]

_SA_DOE = [
    {
        "patent_id": "US0000000001A1",
        "claim_number": 1,
        "element_number": 4,
        "element_text": "recovering the C4 dicarboxylic acid at a yield of at least 0.8 mol/mol carbon source",
        "estoppel": {
            "amendments_found": [
                "Amendment A filed 2020-03-15: narrowed yield from 0.5 to 0.8 mol/mol in response to Fictional Reference Beta prior art rejection."
            ],
            "estoppel_applies": True,
            "surrendered_scope": "Applicant narrowed yield from 0.5 to 0.8 mol/mol during prosecution, surrendering coverage of processes with yields in the 0.5-0.8 range.",
            "file_wrapper_available": True,
            "rejections_found": [
                "Non-final rejection (2019-11-22) under 35 U.S.C. §103: Examiner combined Fictional Reference Beta (2002) with Fictional Reference Alpha (2008)."
            ],
            "prosecution_narrowing_count": 1,
        },
        "fwr": {
            "same_function": True,
            "function_reasoning": "Both claimed 0.8 mol/mol and actual 0.65-0.72 mol/mol serve the same function: producing succinic acid with high carbon efficiency.",
            "same_way": True,
            "way_reasoning": "Biological pathway is identical — reductive TCA branch in E. coli. Yield difference arises from process optimisation, not a different approach.",
            "same_result": False,
            "result_reasoning": "A yield of 0.65-0.72 mol/mol is 9-19% lower carbon efficiency. This difference is commercially significant.",
            "equivalent": False,
            "chemical_context": {
                "structural_relationship": "none",
                "relationship_reasoning": "The yield limitation is a process parameter, not a structural limitation.",
                "known_interchangeability": False,
                "interchangeability_evidence": "",
            },
        },
        "overall_equivalent": False,
        "confidence": 0.78,
        "confidence_band": "MODERATE",
        "reasoning": "Although function and way prongs are satisfied, the result prong fails because there is a meaningful quantitative yield difference. Prosecution history estoppel also bars application of DoE for yields below 0.8 mol/mol.",
    },
    {
        "patent_id": "US0000000002A1",
        "claim_number": 1,
        "element_number": 3,
        "element_text": "recovering crystalline succinic acid having a purity of at least 99.5% by weight",
        "estoppel": {
            "amendments_found": [],
            "estoppel_applies": False,
            "surrendered_scope": "",
            "file_wrapper_available": True,
            "rejections_found": [
                "Non-final rejection (2018-07-03) under 35 U.S.C. §102(a)(1): Examiner cited Fictional Reference Gamma (Chem Eng Technol, 2008). Applicant argued distinction without amending the purity element."
            ],
            "prosecution_narrowing_count": 0,
        },
        "fwr": {
            "same_function": True,
            "function_reasoning": "Both claimed (≥99.5%) and actual (99.2-99.6%) purity serve the same function: providing high-purity succinic acid for polymer-grade or pharmaceutical applications.",
            "same_way": True,
            "way_reasoning": "Purification achieved by the same crystallisation method. Minor purity difference reflects batch-to-batch variation.",
            "same_result": True,
            "result_reasoning": "Purity difference (99.2% vs 99.5%) is within normal analytical variability. Both values are suitable for the same downstream applications.",
            "equivalent": True,
            "chemical_context": {
                "structural_relationship": "none",
                "relationship_reasoning": "This is a process purity parameter, not a structural distinction.",
                "known_interchangeability": True,
                "interchangeability_evidence": "USP and EP monographs specify purity ≥99.0%, indicating both 99.2% and 99.5% are pharmaceutical grade.",
            },
        },
        "overall_equivalent": True,
        "confidence": 0.72,
        "confidence_band": "MODERATE",
        "reasoning": "Function-way-result test satisfied for the purity limitation. Difference between 99.2% and 99.5% is insubstantial. No prosecution history estoppel applies.",
    },
]

_SA_INVALIDITY = [
    {
        "patent_id": "US0000000001A1",
        "claim_numbers": [1, 2],
        "ptab": {
            "has_been_challenged": True,
            "proceedings": [
                {
                    "proceeding_number": "IPR0000-00001",
                    "type": "IPR",
                    "status": "Denied institution",
                    "filing_date": "2021-02-15",
                    "decision_date": "2021-08-22",
                    "claims_challenged": [1, 2, 3, 5],
                    "claims_cancelled": [],
                    "claims_survived": [1, 2, 3, 5],
                    "outcome_summary": "Board denied institution; petitioner (Fictional GreenChem LLC) did not demonstrate reasonable likelihood of prevailing. Board found Fictional Beta+Fictional Alpha combination did not disclose the 0.8 mol/mol yield limitation.",
                }
            ],
            "all_claims_cancelled": [],
        },
        "prior_art": [
            {
                "reference_id": "fictional-beta-2002",
                "title": "Fictional process-study scenario Beta",
                "publication_date": "2002-09-01",
                "relevance": "Discloses E. coli fermentation for succinate production with yields up to 0.66 mol/mol. Teaches overexpression of ppc in the reductive TCA branch.",
                "anticipation_score": 0.42,
                "obviousness_score": 0.71,
                "reference_type": "journal_article",
                "authors": [
                    "Fictional Researcher Beta",
                    "Fictional Researcher Beta-Two",
                    "Fictional Researcher Beta-Three",
                ],
                "journal": "Fictional Journal of Process Research",
                "doi": "",
                "url": "https://example.invalid/prior-art/fictional-beta",
                "abstract": "Maximum succinate yields of 0.66 mol/mol glucose were achieved when shift to anaerobic conditions was performed at OD600 of 15.",
                "source_database": "semantic_scholar",
            },
            {
                "reference_id": "fictional-alpha-2008",
                "title": "Fictional metabolic-engineering scenario Alpha",
                "publication_date": "2008-05-01",
                "relevance": "Describes E. coli strains FX060 and FX073 achieving succinate yields of 1.0-1.2 mol/mol. Teaches genetic modifications recited in claims 1 and 2.",
                "anticipation_score": 0.65,
                "obviousness_score": 0.82,
                "reference_type": "journal_article",
                "authors": [
                    "Fictional Researcher Alpha",
                    "Fictional Researcher Alpha-Two",
                    "Fictional Researcher Alpha-Three",
                    "Fictional Researcher Alpha-Four",
                    "Fictional Researcher Alpha-Five",
                    "Fictional Researcher Alpha-Six",
                    "Fictional Researcher Alpha-Seven",
                ],
                "journal": "Fictional Journal of Process Research",
                "doi": "",
                "url": "https://example.invalid/prior-art/fictional-alpha",
                "abstract": "FX073 achieved a yield of 1.2 mol succinate per mol glucose in mineral salts medium under anaerobic conditions.",
                "source_database": "semantic_scholar",
            },
        ],
        "written_description_issues": [
            "The specification provides only three working examples with yields of 0.82, 0.85, and 0.91 mol/mol. The claimed open-ended range 'at least 0.8 mol/mol' may lack written description support for very high yields exceeding the theoretical maximum.",
        ],
        "claim_charts": [
            {
                "patent_id": "US0000000001A1",
                "claim_number": 1,
                "prior_art_reference_id": "fictional-alpha-2008",
                "entries": [
                    {
                        "element_number": 1,
                        "element_text": "A method for producing a C4 dicarboxylic acid comprising culturing a recombinant prokaryotic microorganism",
                        "prior_art_reference_id": "fictional-alpha-2008",
                        "prior_art_disclosure": "Fictional Reference Alpha discloses metabolically engineered E. coli strains (recombinant prokaryotes) for producing succinate (a C4 dicarboxylic acid).",
                        "citation_location": "Abstract; Materials and Methods, p. 301",
                        "disclosed": "yes",
                        "notes": "",
                    },
                    {
                        "element_number": 2,
                        "element_text": "wherein the microorganism has been genetically modified to overexpress at least one gene in the reductive TCA branch",
                        "prior_art_reference_id": "fictional-alpha-2008",
                        "prior_art_disclosure": "FX073 was derived through metabolic evolution enhancing reductive TCA flux, though explicit overexpression of specific genes was not performed.",
                        "citation_location": "Results, p. 303-304; Table 1",
                        "disclosed": "partial",
                        "notes": "Whether metabolic-evolution-driven flux enhancement constitutes 'overexpression' is a claim construction question.",
                    },
                ],
            },
        ],
    },
    {
        "patent_id": "US0000000002A1",
        "claim_numbers": [1],
        "ptab": {
            "has_been_challenged": False,
            "proceedings": [],
            "all_claims_cancelled": [],
        },
        "prior_art": [
            {
                "reference_id": "fictional-gamma-2008",
                "title": "Fictional crystallization-review scenario Gamma",
                "publication_date": "2008-03-01",
                "relevance": "Describes substantially identical crystallisation conditions for bio-succinic acid purification, with cooling from 70°C to 5°C. May anticipate the Fictional Atlas crystallisation claims.",
                "anticipation_score": 0.72,
                "obviousness_score": 0.85,
                "reference_type": "journal_article",
                "authors": [
                    "Fictional Researcher Gamma",
                    "Fictional Researcher Gamma-Two",
                    "Fictional Researcher Gamma-Three",
                    "Fictional Researcher Gamma-Four",
                    "Fictional Researcher Gamma-Five",
                ],
                "journal": "Fictional Journal of Process Research",
                "doi": "",
                "url": "https://example.invalid/prior-art/fictional-gamma",
                "abstract": "Succinic acid crystallisation from fermentation broth using controlled cooling. Yields crystalline product with purity exceeding 99.0%.",
                "source_database": "semantic_scholar",
            },
        ],
        "written_description_issues": [],
        "claim_charts": [],
    },
]

_SA_PROSECUTION_FINDINGS = [
    {
        "patent_id": "US0000000001A1",
        "jurisdiction": "US",
        "application_number": "00/000001",
        "prosecution_history_available": True,
        "transaction_count": 6,
        "amendment_event_count": 2,
        "office_action_count": 2,
        "continuity_entry_count": 1,
        "narrowing_signal": True,
        "terminal_disclaimer": False,
        "terminal_disclaimer_linked_patent": "",
        "ptab_challenged": True,
        "ptab_proceeding_count": 1,
        "pending_family_signal": True,
        "pending_family_member_count": 2,
        "office_action_types": ["non_final_office_action", "final_office_action"],
        "amendment_types": ["after_final_response", "rce"],
        "continuity_types": ["continuation"],
        "rejection_bases": ["103", "prior_art"],
        "estoppel_risk_flags": [
            "after_final_response_history",
            "rce_history",
            "continuation_lineage",
            "prior_art_rejection_history",
        ],
        "continuation_parent_count": 1,
        "continuation_child_count": 0,
        "divisional_parent_count": 0,
        "divisional_child_count": 0,
        "cip_parent_count": 0,
        "cip_child_count": 0,
        "response_after_final_count": 1,
        "rce_count": 1,
        "interview_event_count": 1,
        "appeal_event_count": 0,
        "record_basis": ["application_number", "uspto_transactions", "family_members"],
        "summary": "File wrapper available. Yield claim narrowed from 0.5 to 0.8 mol/mol during prosecution. IPR denied institution (IPR0000-00001). 2 pending family members.",
    },
    {
        "patent_id": "US0000000002A1",
        "jurisdiction": "US",
        "application_number": "00/000002",
        "prosecution_history_available": True,
        "transaction_count": 4,
        "amendment_event_count": 1,
        "office_action_count": 1,
        "continuity_entry_count": 0,
        "narrowing_signal": False,
        "terminal_disclaimer": False,
        "terminal_disclaimer_linked_patent": "",
        "ptab_challenged": False,
        "ptab_proceeding_count": 0,
        "pending_family_signal": False,
        "pending_family_member_count": 0,
        "office_action_types": ["non_final_office_action"],
        "amendment_types": ["response_to_office_action"],
        "continuity_types": [],
        "rejection_bases": ["102"],
        "estoppel_risk_flags": [],
        "continuation_parent_count": 0,
        "continuation_child_count": 0,
        "divisional_parent_count": 0,
        "divisional_child_count": 0,
        "cip_parent_count": 0,
        "cip_child_count": 0,
        "response_after_final_count": 0,
        "rce_count": 0,
        "interview_event_count": 0,
        "appeal_event_count": 0,
        "record_basis": ["application_number", "uspto_transactions"],
        "summary": "File wrapper available. No claim narrowing during prosecution. No pending family members.",
    },
]

_SA_PROSECUTION_DOSSIERS = [
    {
        "patent_id": "US0000000001A1",
        "jurisdiction": "US",
        "application_number": "00/000001",
        "source_name": "uspto_odp",
        "sections_available": ["office_actions", "continuity", "amendments"],
        "office_actions_summary": "- [CTNF] Non-final rejection under §103 (2019-11-22)\n- [CTFR] Final rejection under §103 (2020-01-15)",
        "continuity_summary": "- Parent: 15/123456 (CON, filed 2017-05-12)",
        "amendments_summary": "- [AMND] Amendment A (2020-03-15): narrowed yield from 0.5 to 0.8 mol/mol\n- [RCE] Request for Continued Examination (2020-04-01)",
        "office_action_events": [
            {
                "document_code": "CTNF",
                "description": "Non-final rejection under 35 U.S.C. §103: Fictional Beta (2002) + Fictional Alpha (2008) combination",
                "event_date": "2019-11-22",
                "office_action_type": "non_final_office_action",
                "claims_rejected": [1, 2, 3, 4, 5],
                "rejection_bases": ["103", "prior_art"],
            },
            {
                "document_code": "CTFR",
                "description": "Final rejection under 35 U.S.C. §103",
                "event_date": "2020-01-15",
                "office_action_type": "final_office_action",
                "claims_rejected": [1, 2, 3],
                "rejection_bases": ["103", "prior_art"],
            },
        ],
        "continuity_entries": [
            {
                "relationship": "parent",
                "application_number": "00/000003",
                "related_application_number": "",
                "continuity_type": "continuation",
                "filing_date": "2017-05-12",
            }
        ],
        "amendment_events": [
            {
                "transaction_code": "AMND",
                "description": "Amendment A: narrowed yield limitation from 0.5 to 0.8 mol/mol carbon source",
                "event_date": "2020-03-15",
                "event_type": "after_final_response",
                "claim_numbers": [1],
            },
            {
                "transaction_code": "RCE",
                "description": "Request for Continued Examination",
                "event_date": "2020-04-01",
                "event_type": "rce",
                "claim_numbers": [],
            },
        ],
        "office_action_count": 2,
        "continuity_entry_count": 1,
        "amendment_entry_count": 2,
        "office_action_types": ["non_final_office_action", "final_office_action"],
        "amendment_types": ["after_final_response", "rce"],
        "continuity_types": ["continuation"],
        "rejected_claim_numbers": [],
        "narrowing_claim_numbers": [1],
        "rejection_bases": ["103", "prior_art"],
        "estoppel_risk_flags": [
            "after_final_response_history",
            "rce_history",
            "continuation_lineage",
        ],
        "continuation_parent_count": 1,
        "continuation_child_count": 0,
        "divisional_parent_count": 0,
        "divisional_child_count": 0,
        "cip_parent_count": 0,
        "cip_child_count": 0,
        "response_after_final_count": 1,
        "rce_count": 1,
        "interview_event_count": 1,
        "appeal_event_count": 0,
        "narrowing_signal": True,
        "terminal_disclaimer": False,
        "terminal_disclaimer_linked_patent": "",
        "ptab_challenged": True,
        "pending_family_signal": True,
        "record_basis": ["uspto_odp", "application_number", "uspto_transactions", "family_members"],
        "summary": "2 office actions, 2 amendments, 1 continuity record. Yield claim narrowed during prosecution. IPR0000-00001 denied. 2 pending family members.",
    },
]


def _raw_succinic_acid_report() -> dict:
    """Full 5-patent FTO report for succinic acid. High risk (3 blocking)."""
    compound_name = "succinic acid"
    all_ids = [f"US{i + 100:010d}A1" for i in range(2412)] + _SA_PATENTS
    audit = _search_funnel(all_ids, _SA_TRIAGE, _SA_PATENTS)
    return {
        "report_id": str(uuid.uuid4()),
        "generated_at": "2026-04-08T14:36:00+00:00",
        "praviar_pipeline_version": "0.1.0-demo",
        "compound": {
            "name": "succinic acid",
            "canonical_smiles": "OC(=O)CCC(O)=O",
            "inchi": "InChI=1S/C4H6O4/c5-3(6)1-2-4(7)8/h1-2H2,(H,5,6)(H,7,8)",
            "inchi_key": "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
            "pubchem_cid": 1110,
            "synonyms": [
                "succinic acid",
                "butanedioic acid",
                "1,2-ethanedicarboxylic acid",
                "amber acid",
            ],
            "cas_numbers": ["110-15-6"],
            "molecular_formula": "C4H6O4",
            "molecular_weight": 118.09,
            "morgan_fp": "",
            "maccs_keys": "",
            "functional_groups": ["carboxylic acid", "dicarboxylic acid"],
            "related_compounds": [
                {
                    "cid": 196,
                    "name": "citric acid",
                    "canonical_smiles": "OC(=O)CC(O)(CC(O)=O)C(O)=O",
                    "tanimoto_similarity": 0.61,
                },
                {
                    "cid": 5862,
                    "name": "glutaric acid",
                    "canonical_smiles": "OC(=O)CCCC(O)=O",
                    "tanimoto_similarity": 0.85,
                },
            ],
            "original_input": "succinic acid",
            "input_type": "name",
        },
        "risk_summary": {
            "overall_risk": "high",
            "blocking_patents_count": 3,
            "total_patents_analyzed": 5,
            "key_risks": [
                "US0000000001A1 (Fictional Meridian) claims a process for producing C4 dicarboxylic acids using recombinant E. coli fermentation; three of four claim elements are met by standard bio-based production routes.",
                "US0000000002A1 (Fictional Atlas) covers crystallisation and purification of bio-succinic acid at yields above 85%, overlapping common downstream processing protocols.",
                "US0000000003A1 (Fictional Nova) creates medium risk for enzymatic conversion approaches via interpretive ambiguity around fumarate as a reductive TCA intermediate.",
            ],
            "executive_summary": (
                "This freedom-to-operate analysis evaluated succinic acid (CID 1110, butanedioic acid) against 2,417 patents "
                "discovered across PubChem, SureChEMBL, Google Patents (BigQuery), and PatCID. After automated hard-filtering, "
                "composite scoring, and BM25 re-ranking, 5 patents passed triage for detailed claim-level analysis.\n\n"
                "Two patents present high infringement risk. US0000000001A1 (assigned to Fictional Meridian) contains broad independent claims "
                "covering microbial fermentation of C4 dicarboxylic acids using recombinant prokaryotic hosts, and three of four "
                "claim elements are met by a standard bio-succinic production process. US0000000002A1 (assigned to Fictional Atlas) claims a "
                "purification method for crystallising bio-based succinic acid from aqueous fermentation broth, with both "
                "independent claim elements satisfied. Design-around opportunities exist primarily through alternative downstream "
                "processing (reactive extraction with tri-n-octylamine) or through use of eukaryotic hosts not covered by the "
                "Fictional Meridian claims.\n\n"
                "Invalidity analysis identified potentially strong prior art against both high-risk patents. The Fictional Atlas crystallisation "
                "patent faces an anticipation argument based on Fictional Reference Gamma (2008). The Fictional Meridian fermentation patent is vulnerable "
                "to an obviousness challenge given Fictional Reference Beta (2002) and Fictional Reference Alpha (2008). An IPR (IPR0000-00001) was filed "
                "against the Fictional Meridian patent but was denied institution. Engage patent counsel to evaluate design-around strategies "
                "before proceeding with commercialisation."
            ),
            "summary_validation_issues": [
                "Two high-risk patents share overlapping claim scope on the fermentation element. The risk assessment may double-count this infringement vector.",
            ],
        },
        "clearance_decision": _clearance_decision("blocked", 0.88, _SA_PATENTS, _SA_BLOCKING),
        "decision_scope": {
            "matter_type": "small_molecule",
            "jurisdictions": ["US"],
            "asset_classes": ["compound", "formulation", "process"],
            "supports_positive_clearance": True,
            "summary": "US evidence is within the certified decision scope for this matter.",
        },
        "supporting_scope": {
            "matter_type": "small_molecule",
            "jurisdictions": [],
            "asset_classes": ["compound", "formulation", "process"],
            "supports_positive_clearance": False,
            "summary": "No supporting-only jurisdictions were material in this matter.",
        },
        "certification_scope": {
            "certified_jurisdictions": ["US", "EP"],
            "certified_matter_types": ["small_molecule", "formulation", "process"],
            "certified_asset_classes": ["compound", "formulation", "process"],
            "attorney_supervised_matter_types": [],
            "attorney_supervised_asset_classes": [],
            "supporting_only_jurisdictions": [],
            "current_matter_type_certified": True,
            "attorney_supervision_required": False,
            "summary": "Direct-clearance certification covers US and EP small-molecule, formulation, and process cohorts.",
        },
        "cohort_status": "attorney_supervised",
        "jurisdiction_decisions": [
            _jurisdiction_decision("blocked", 0.88, _SA_PATENTS, _SA_BLOCKING)
        ],
        "patent_analyses": _SA_PATENT_ANALYSES,
        "doe_assessments": _SA_DOE,
        "invalidity_assessments": _SA_INVALIDITY,
        "verification": _verification_ok(),
        "prosecution_findings": _SA_PROSECUTION_FINDINGS,
        "prosecution_dossiers": _SA_PROSECUTION_DOSSIERS,
        "claim_construction_record": {
            "standard": "Phillips claim construction for U.S. infringement-risk assessment",
            "jurisdictions": ["US"],
            "assumptions": [
                "Issued claim text was prioritised.",
                "Prosecution history narrowing was applied conservatively.",
            ],
            "disputed_terms": [
                "overexpress (claim 1, element 2): whether metabolic evolution constitutes overexpression"
            ],
            "summary": "Conservative claim construction applied; prosecution history estoppel from Amendment A is dispositive for DoE analysis.",
        },
        "future_risk": [
            {
                "patent_id": "US0000000001A1",
                "jurisdiction": "US",
                "risk_type": "pending_family",
                "severity": "high",
                "monitoring_required": True,
                "related_patent_ids": ["US0000000001A1"],
                "record_basis": ["family_members"],
                "summary": "2 pending family members remain open. Broad claims may issue with higher yield thresholds.",
            },
        ],
        "commercial_exposure": {
            "damages_injunction_risk": "elevated",
            "business_severity": "high",
            "blocking_patent_ids": _SA_BLOCKING,
            "rationale": [
                "Two high-risk patents with overlapping claim scope on fermentation element.",
                "Design-around via eukaryotic host would require significant process change.",
            ],
            "summary": "Commercial launch not advisable without design-around or freedom-to-operate opinion from patent counsel.",
        },
        "claim_program_decisions": [
            {
                "patent_id": "US0000000001A1",
                "claim_number": 1,
                "jurisdiction": "US",
                "literal_outcome": "partially_met",
                "literal_risk": "high",
                "doe_risk": "not_equivalent",
                "invalidity_strength": "moderate",
                "prosecution_risk_flags": ["narrowing_signal", "pending_family_signal"],
                "prosecution_risk_level": "high",
                "post_grant_risk_level": "moderate",
                "scope_constrained": True,
                "future_risk_flags": ["pending_family"],
                "commercial_severity": "high",
                "evidence_sufficient": True,
                "missing_components": [],
                "record_basis": ["application_number", "family_members", "claim_level_analysis"],
                "rationale": ["Three of four elements met; yield gap is narrow."],
            },
        ],
        "evidence_artifacts": [
            {
                "artifact_id": f"{pid}:search_hit",
                "artifact_type": "search_hit",
                "source_name": "pubchem_sdq,bigquery",
                "authority_tier": "supporting",
                "jurisdiction": "US",
                "patent_id": pid,
                "family_id": _demo_family_id(pid),
                "summary": "Patent retained as material record in the final matter.",
                "record_basis": ["pubchem_sdq", "bigquery"],
                "linked_node_ids": [
                    f"patent:{pid}",
                    f"family:{_demo_family_id(pid)}",
                ],
            }
            for pid in _SA_PATENTS
        ],
        "evidence_adapter_results": [
            {
                "adapter_name": "pubchem_sdq",
                "adapter_kind": "search",
                "authority_tier": "supporting",
                "status": "ok",
                "collection_state": "collected",
                "required_before_clear": False,
                "target_patent_ids": _SA_PATENTS,
                "covered_patent_ids": _SA_PATENTS,
                "missing_patent_ids": [],
                "artifacts": [],
                "warnings": [],
                "freshness_note": "Records captured during current pipeline run.",
                "artifact_count": len(_SA_PATENTS),
                "covered_components": [],
                "expected_components": [],
                "missing_components": [],
                "supports_authoritative_findings": False,
            },
            {
                "adapter_name": "patentsview",
                "adapter_kind": "legal_record",
                "authority_tier": "authoritative",
                "status": "ok",
                "collection_state": "collected",
                "required_before_clear": True,
                "target_patent_ids": _SA_PATENTS,
                "covered_patent_ids": _SA_PATENTS,
                "missing_patent_ids": [],
                "artifacts": [],
                "warnings": [],
                "freshness_note": "Authoritative claim text retrieved.",
                "artifact_count": len(_SA_PATENTS),
                "covered_components": ["claims_text"],
                "expected_components": ["claims_text"],
                "missing_components": [],
                "supports_authoritative_findings": True,
            },
        ],
        "collector_runs": [
            {
                "definition": {
                    "collector_name": "pubchem_sdq",
                    "adapter_kind": "search",
                    "authority_tier": "supporting",
                    "supports_authoritative_findings": False,
                    "expected_components": [],
                },
                "collection_state": "collected",
                "required_before_clear": False,
                "target_patent_ids": _SA_PATENTS,
                "covered_patent_ids": _SA_PATENTS,
                "missing_patent_ids": [],
                "expected_components": [],
                "covered_components": [],
                "missing_components": [],
                "retry_budget_remaining": 0,
                "freshness_note": "Records captured during current pipeline run.",
                "triggered_directive_ids": [],
                "collection_targets": [
                    {
                        "patent_id": pid,
                        "jurisdiction": "US",
                        "required_components": [],
                        "covered_components": [],
                        "missing_components": [],
                        "required_before_clear": False,
                    }
                    for pid in _SA_PATENTS
                ],
                "attempts": [
                    {
                        "attempt_number": 1,
                        "status": "ok",
                        "collection_state": "collected",
                        "artifact_count": len(_SA_PATENTS),
                        "warnings": [],
                        "rate_limit_remaining": None,
                        "retry_after_seconds": None,
                        "summary": "All targets satisfied.",
                    }
                ],
            },
        ],
        "evidence_collection_plan": [],
        "coverage_gaps": [],
        "matter_graph": _matter_graph(compound_name, _SA_PATENTS),
        "matter_graph_summary": _matter_graph_summary(compound_name, _SA_PATENTS),
        "matter_store": {
            "matter_graph": _matter_graph(compound_name, _SA_PATENTS),
            "matter_graph_summary": _matter_graph_summary(compound_name, _SA_PATENTS),
            "matter_evidence_index": {
                "source_names": ["pubchem_sdq", "bigquery"],
                "authoritative_source_names": ["patentsview"],
                "supporting_source_names": ["bigquery", "pubchem_sdq"],
                "material_patent_count": len(_SA_PATENTS),
                "family_count": len(_SA_PATENTS),
                "analysis_failure_patent_ids": [],
                "critic_flagged_patent_ids": _SA_BLOCKING,
                "clearance_grade_ready_patent_ids": [],
                "incomplete_patent_ids": _SA_BLOCKING,
                "clearance_grade_ready_family_ids": [],
                "incomplete_family_ids": [_demo_family_id(patent_id) for patent_id in _SA_BLOCKING],
                "patent_records": [],
                "family_records": [],
            },
            "prosecution_dossiers": _SA_PROSECUTION_DOSSIERS,
            "claim_program_decisions": [],
            "evidence_artifacts": [],
            "evidence_adapter_results": [],
            "collector_runs": [],
            "evidence_collection_plan": [],
            "coverage_gaps": [],
            "authority_coverage": {
                "policy": "official_plus_licensed",
                "authoritative_source_names": ["patentsview"],
                "supporting_source_names": ["bigquery", "pubchem_sdq"],
                "authoritative_categories_covered": [
                    "authoritative_search_source",
                    "family_record",
                    "us_prosecution_record",
                ],
                "authoritative_categories_missing": [],
                "patents_with_authoritative_records": len(_SA_PATENTS),
                "patents_without_authoritative_records": 0,
                "clearance_grade_ready_patents": 0,
            },
            "record_completeness": {
                "profile": "world_class_us_ep",
                "matter_type": "small_molecule",
                "jurisdictions": ["US"],
                "required_components": [
                    "claims_text",
                    "claim_level_analysis",
                    "authoritative_records",
                    "family_context",
                ],
                "missing_components": [],
                "blocking_gaps": [],
                "clearance_grade_ready": False,
            },
            "run_observability": {
                "authoritative_source_hit_rate": 1.0,
                "claims_text_coverage": 1.0,
                "family_context_coverage": 1.0,
                "us_file_wrapper_dossier_coverage": 0.4,
                "ep_register_coverage": 0.0,
                "failed_adapter_names": ["epo_ops"],
                "false_clear_risk_flags": ["high_risk_claims"],
                "unresolved_contradictions": [],
            },
            "record_contradictions": [],
        },
        "authority_coverage": {
            "policy": "official_plus_licensed",
            "authoritative_source_names": ["patentsview"],
            "supporting_source_names": ["bigquery", "pubchem_sdq"],
            "authoritative_categories_covered": [
                "authoritative_search_source",
                "family_record",
                "us_prosecution_record",
            ],
            "authoritative_categories_missing": [],
            "patents_with_authoritative_records": len(_SA_PATENTS),
            "patents_without_authoritative_records": 0,
            "clearance_grade_ready_patents": 0,
        },
        "record_completeness": {
            "profile": "world_class_us_ep",
            "matter_type": "small_molecule",
            "jurisdictions": ["US"],
            "required_components": [
                "claims_text",
                "claim_level_analysis",
                "authoritative_records",
                "family_context",
            ],
            "missing_components": [],
            "blocking_gaps": [],
            "clearance_grade_ready": False,
        },
        "run_observability": {
            "authoritative_source_hit_rate": 1.0,
            "claims_text_coverage": 1.0,
            "family_context_coverage": 1.0,
            "us_file_wrapper_dossier_coverage": 0.4,
            "ep_register_coverage": 0.0,
            "failed_adapter_names": ["epo_ops"],
            "false_clear_risk_flags": ["high_risk_claims"],
            "unresolved_contradictions": [],
        },
        "matter_evidence_index": {
            "source_names": ["pubchem_sdq", "bigquery"],
            "authoritative_source_names": ["patentsview"],
            "supporting_source_names": ["bigquery", "pubchem_sdq"],
            "material_patent_count": len(_SA_PATENTS),
            "family_count": len(_SA_PATENTS),
            "analysis_failure_patent_ids": [],
            "critic_flagged_patent_ids": _SA_BLOCKING,
            "clearance_grade_ready_patent_ids": [],
            "incomplete_patent_ids": _SA_BLOCKING,
            "clearance_grade_ready_family_ids": [],
            "incomplete_family_ids": [_demo_family_id(patent_id) for patent_id in _SA_BLOCKING],
            "patent_records": [],
            "family_records": [],
        },
        "total_patents_found": 2417,
        "patents_after_triage": 5,
        "search_sources_used": ["pubchem_sdq", "bigquery", "patentsview"],
        "source_health": _source_health(_SA_PATENTS),
        "scholarly_prior_art_count": 4,
        "analysis_failures": [],
        "data_limitations": [
            {
                "category": "source_unavailable",
                "description": "EPO OPS rate limit exceeded during run; EP family members were not retrieved via EPO Register.",
                "impact": "EP-jurisdiction claim analysis is based on US family members only. EP-specific prosecution history is unavailable.",
            },
        ],
        "audit_trail": audit,
        "patent_narratives": {
            "US0000000001A1": "Broad fermentation patent covering E. coli-based C4 dicarboxylic acid production. Assigned to Fictional Meridian. High infringement risk due to breadth of claim 1.",
            "US0000000002A1": "Crystallisation and purification process patent. Assigned to Fictional Atlas. High risk due to overlap with standard downstream processing.",
            "US0000000003A1": "Fictional Nova enzymatic conversion patent. Medium risk due to interpretive ambiguity around fumarate as TCA intermediate.",
            "US0000000013A1": "Fictional Orbit low-pH yeast fermentation patent. Low risk; process uses E. coli at neutral pH, not yeast at pH < 3.0.",
            "US0000000012A1": "Fictional Myria electrochemical CO2 reduction patent. Clear; no overlap with biological fermentation.",
        },
        "disclaimer": (
            "IMPORTANT: This report is an AI-assisted screening tool and does NOT constitute legal advice "
            "or a formal Freedom-to-Operate opinion. A qualified patent attorney should review all findings "
            "before making commercial decisions."
        ),
        "llm_models_used": {
            "triage": "claude-haiku-4-5-20251001",
            "analysis": "claude-sonnet-4-6",
            "deep": "claude-opus-4-7",
        },
        "drawing_analyses": [],
        "drawing_summary": {},
        "report_pipeline": "world_class_adaptive",
        "reasoning_traces": [],
        "patent_details": {},
        "action_items": [
            {
                "action_type": "design_around",
                "priority": "critical",
                "description": "Evaluate switching the production host from E. coli to a eukaryotic organism (S. cerevisiae or Y. lipolytica) to avoid the prokaryote limitation in US0000000001A1 claim 1.",
                "patent_ids": ["US0000000001A1"],
                "reasoning": "Eukaryotic host falls outside the explicit 'prokaryotic microorganism' limitation in the Fictional Meridian independent claim.",
                "estimated_timeline": "6-12 months for strain development and process validation",
            },
            {
                "action_type": "design_around",
                "priority": "high",
                "description": "Evaluate reactive extraction with tri-n-octylamine (TOA) as an alternative to cooling crystallisation to avoid the Fictional Atlas purification claims.",
                "patent_ids": ["US0000000002A1"],
                "reasoning": "TOA reactive extraction avoids the acidification-crystallisation sequence claimed by Fictional Atlas. Well-established at commercial scale.",
                "estimated_timeline": "3-6 months for process development",
            },
            {
                "action_type": "challenge_ipr",
                "priority": "medium",
                "description": "Assess IPR petition against US0000000002A1 (Fictional Atlas) based on Fictional Reference Gamma (2008) anticipation argument.",
                "patent_ids": ["US0000000002A1"],
                "reasoning": "Fictional Reference Gamma describes substantially identical crystallisation conditions. Anticipation score is 0.72.",
                "estimated_timeline": "12-18 months for IPR preparation and PTAB decision",
            },
            {
                "action_type": "monitor",
                "priority": "high",
                "description": "Monitor the 2 pending family members of US0000000001A1 for claim scope that may extend to lower yield thresholds.",
                "patent_ids": ["US0000000001A1"],
                "reasoning": "Pending family members may issue with broader claims or different yield thresholds than the parent.",
                "estimated_timeline": "Ongoing; review at 6-month intervals",
            },
        ],
        "bibliography": [],
        "verification_summary": {},
        "factual_accuracy_rate": 0.94,
        "total_input_tokens": 27846,
        "total_output_tokens": 7233,
        "estimated_cost_usd": 4.82,
        "step_token_usage": [
            {
                "step_name": "search",
                "model_role": "triage",
                "model_name": "claude-haiku-4-5-20251001",
                "input_tokens": 3200,
                "output_tokens": 890,
            },
            {
                "step_name": "triage",
                "model_role": "triage",
                "model_name": "claude-haiku-4-5-20251001",
                "input_tokens": 8100,
                "output_tokens": 1800,
            },
            {
                "step_name": "analysis",
                "model_role": "analysis",
                "model_name": "claude-sonnet-4-6",
                "input_tokens": 12000,
                "output_tokens": 3800,
            },
            {
                "step_name": "doe",
                "model_role": "deep",
                "model_name": "claude-opus-4-7",
                "input_tokens": 2800,
                "output_tokens": 520,
            },
            {
                "step_name": "invalidity",
                "model_role": "deep",
                "model_name": "claude-opus-4-7",
                "input_tokens": 1746,
                "output_tokens": 223,
            },
        ],
    }


# ── Legacy compound scenario Gamma ─────────────────────────────────────────────
# All publication records and outcomes in this section are synthetic.

_SOF_BLOCKING = ["WO1978000002A1", "WO1978000004A1"]
_SOF_PATENTS = ["WO1978000002A1", "WO1978000004A1", "WO1978000001A1", "WO1978000003A1"]


def _raw_sofosbuvir_report() -> dict:
    """Return a synthetic four-publication high-risk component-test report."""
    compound_name = "sofosbuvir"
    all_ids = [f"WO1978{i + 100:06d}A1" for i in range(181)] + _SOF_PATENTS
    audit = _search_funnel(all_ids, _SOF_PATENTS, _SOF_PATENTS)
    return {
        "report_id": str(uuid.uuid4()),
        "generated_at": "2026-04-10T09:21:00+00:00",
        "praviar_pipeline_version": "0.1.0-demo",
        "compound": {
            "name": "sofosbuvir",
            "canonical_smiles": "CC(C)OC(=O)[C@@H](C)N[P@@](=O)(Oc1ccccc1)O[C@@H]1[C@@H](O)[C@](C)(F)[C@@H](O1)n1ccc(=O)[nH]c1=O",
            "inchi": "InChI=1S/C22H29FN3O9P/c1-12(2)34-20(30)13(3)24-36(32,35-14-8-6-5-7-9-14)33-16-11-22(4,23)18(28)15(16)25-10-17(27)26-21(25)29/h5-10,12-13,15-16,18,28H,11H2,1-4H3,(H,24,32)(H,26,27,29)/t13-,15+,16+,18+,22+/m0/s1",
            "inchi_key": "TTZHDVOVKQGIBA-IQWMDFIBSA-N",
            "pubchem_cid": 45375808,
            "synonyms": ["sofosbuvir", "Fictional Brand Gamma", "ECG-7977", "ECG-7977"],
            "cas_numbers": ["1190307-88-0"],
            "molecular_formula": "C22H29FN3O9P",
            "molecular_weight": 529.45,
            "morgan_fp": "",
            "maccs_keys": "",
            "functional_groups": ["phosphoramidate", "nucleoside", "ester", "fluorine"],
            "related_compounds": [],
            "original_input": "sofosbuvir",
            "input_type": "name",
        },
        "risk_summary": {
            "overall_risk": "high",
            "blocking_patents_count": 2,
            "total_patents_analyzed": 4,
            "key_risks": [
                "WO1978000002A1 (Fictional Helix Therapeutics) is the core sofosbuvir prodrug patent with 6 Orange Book listings covering the marketed form. All independent claim elements are met by the compound as-is.",
                "WO1978000004A1 (Fictional Helix Therapeutics) covers polymorph Form 1 of sofosbuvir. If the evaluated compound uses the same crystalline form, all claim elements are met.",
            ],
            "executive_summary": (
                "This freedom-to-operate analysis evaluated sofosbuvir (ECG-7977, CAS 1190307-88-0) against 185 patents discovered "
                "across PubChem, BigQuery, and PatentsView. After hard-filtering and triage, 4 patents were selected for detailed "
                "claim-level analysis.\n\n"
                "Two patents present blocking risk. WO1978000002A1 (Fictional Helix Therapeutics) is the primary compound patent for the sofosbuvir "
                "prodrug as marketed, with 6 Orange Book listings covering US0000000021A1, US0000000022A1, US0000000023A1, US0000000024A1, US0000000025A1, and "
                "US0000000026A1. The independent claim covers the specific phosphoramidate prodrug structure that defines sofosbuvir, "
                "and all claim elements are met by the compound without qualification. WO1978000004A1 (Fictional Helix Therapeutics) covers "
                "crystalline Form 1 of sofosbuvir. If the evaluated compound uses Form 1 (the commercially predominant polymorph), "
                "this patent presents a blocking risk.\n\n"
                "WO1978000001A1, the primary compound patent, expired on 2024-04-20 and presents no current risk. WO1978000003A1 "
                "covers a specific formulation with excipients not used in the evaluated compound and presents low risk. "
                "Given the blocking status of the core prodrug patent and the polymorph patent, commercialisation of sofosbuvir "
                "in the US is not possible without a licence from Fictional Helix Therapeutics or a successful invalidity challenge."
            ),
            "summary_validation_issues": [],
        },
        "clearance_decision": _clearance_decision("blocked", 0.96, _SOF_PATENTS, _SOF_BLOCKING),
        "decision_scope": {
            "matter_type": "small_molecule",
            "jurisdictions": ["US"],
            "asset_classes": ["compound", "formulation"],
            "supports_positive_clearance": True,
            "summary": "US evidence is within the certified decision scope.",
        },
        "supporting_scope": {
            "matter_type": "small_molecule",
            "jurisdictions": [],
            "asset_classes": ["compound", "formulation"],
            "supports_positive_clearance": False,
            "summary": "No supporting-only jurisdictions were material.",
        },
        "certification_scope": {
            "certified_jurisdictions": ["US", "EP"],
            "certified_matter_types": ["small_molecule", "formulation"],
            "certified_asset_classes": ["compound", "formulation"],
            "attorney_supervised_matter_types": [],
            "attorney_supervised_asset_classes": [],
            "supporting_only_jurisdictions": [],
            "current_matter_type_certified": True,
            "attorney_supervision_required": True,
            "summary": "Attorney supervision required given blocking status of core compound patent.",
        },
        "cohort_status": "attorney_supervised",
        "jurisdiction_decisions": [
            _jurisdiction_decision("blocked", 0.96, _SOF_PATENTS, _SOF_BLOCKING)
        ],
        "patent_analyses": [
            {
                "patent_id": "WO1978000002A1",
                "title": "Nucleoside phosphoramidate prodrugs",
                "assignee": "Fictional Helix Therapeutics",
                "expiry_date": "2028-04-03",
                "claims_analyzed": [
                    {
                        "claim_number": 1,
                        "claim_type": "independent",
                        "depends_on": None,
                        "preamble": "A compound of formula (I)",
                        "transitional_phrase": "wherein",
                        "elements": [
                            {
                                "element_number": 1,
                                "element_text": "A phosphoramidate prodrug comprising a uridine nucleoside core with 2'-fluoro, 2'-methyl substitution",
                                "status": "met",
                                "reasoning": "Sofosbuvir is a phosphoramidate prodrug of 2'-deoxy-2'-fluoro-2'-C-methyluridine 5'-monophosphate. The nucleoside core, 2'-fluoro, and 2'-methyl substitutions are all present.",
                                "confidence": 0.98,
                                "evidence": "IUPAC name and structural formula of sofosbuvir confirm all structural features recited in the claim.",
                            },
                            {
                                "element_number": 2,
                                "element_text": "with a phenyl phosphoramidate moiety at the 5' position bearing an L-alanine methyl ester",
                                "status": "met",
                                "reasoning": "Sofosbuvir bears a phenyl phosphoramidate group at the 5' position with an isopropyl ester of L-alanine. This matches the structural requirements of the claim.",
                                "confidence": 0.97,
                                "evidence": "SMILES string confirms phenyl phosphoramidate with L-alanine isopropyl ester at 5' position.",
                            },
                        ],
                        "overall_status": "met",
                        "overall_confidence": 0.97,
                        "reasoning": "All structural elements of independent claim 1 are met. Sofosbuvir is within the literal scope of this claim.",
                    },
                ],
                "risk_level": "high",
                "risk_summary": "Core sofosbuvir prodrug patent with 6 Orange Book listings. All independent claim elements met. Commercialisation without licence is not possible.",
                "design_around_suggestions": [],
                "orange_book_info": {
                    "is_listed": True,
                    "nda_numbers": ["NDA204671"],
                    "patent_use_codes": ["U-2608"],
                },
                "model_used": "claude-sonnet-4-6",
                "thinking_text": "This is the primary compound/prodrug patent. Sofosbuvir is unambiguously within claim 1. No design-around is possible without creating a different compound that would no longer be sofosbuvir.",
                "input_tokens": 9200,
                "output_tokens": 2400,
            },
            {
                "patent_id": "WO1978000004A1",
                "title": "Solid forms of an antiviral compound",
                "assignee": "Fictional Helix Therapeutics",
                "expiry_date": "2031-04-08",
                "claims_analyzed": [
                    {
                        "claim_number": 1,
                        "claim_type": "independent",
                        "depends_on": None,
                        "preamble": "Crystalline Form 1 of sofosbuvir",
                        "transitional_phrase": "characterised by",
                        "elements": [
                            {
                                "element_number": 1,
                                "element_text": "X-ray powder diffraction peaks at 2θ values of 4.6, 9.3, 14.0, and 18.1 degrees (±0.2°)",
                                "status": "met",
                                "reasoning": "The commercially supplied API uses Form 1 as the predominant crystalline form. Published XRPD data for commercial sofosbuvir matches the claimed peak positions.",
                                "confidence": 0.89,
                                "evidence": "Published XRPD characterisation of Fictional Brand Gamma API (Fictional Helix drug product monograph) matches claimed peaks.",
                            },
                        ],
                        "overall_status": "met",
                        "overall_confidence": 0.89,
                        "reasoning": "Commercial sofosbuvir API uses Form 1. The polymorph patent is met if the evaluated compound uses the same crystalline form.",
                    },
                ],
                "risk_level": "high",
                "risk_summary": "Polymorph Form 1 patent. Met if commercial sofosbuvir API (Form 1) is used. Orange Book listed.",
                "design_around_suggestions": [
                    {
                        "element_avoided": 1,
                        "suggestion": "Use an amorphous form or a different crystalline polymorph of sofosbuvir not covered by WO1978000004A1.",
                        "feasibility": "Low. Form 1 is the thermodynamically stable form under ambient conditions; other polymorphs may convert spontaneously.",
                    },
                ],
                "orange_book_info": {
                    "is_listed": True,
                    "nda_numbers": ["NDA204671"],
                    "patent_use_codes": ["U-2608"],
                },
                "model_used": "claude-sonnet-4-6",
                "thinking_text": "Polymorph patents are standard life-cycle management strategy. Form 1 is the commercially predominant form. Design-around via alternative polymorph is technically difficult.",
                "input_tokens": 6800,
                "output_tokens": 1900,
            },
            {
                "patent_id": "WO1978000001A1",
                "title": "Nucleoside compounds for treating viral infections",
                "assignee": "Fictional Helix Therapeutics",
                "expiry_date": "2024-04-20",
                "claims_analyzed": [
                    {
                        "claim_number": 1,
                        "claim_type": "independent",
                        "depends_on": None,
                        "preamble": "A compound of formula (I) for treating HCV infection",
                        "transitional_phrase": "wherein",
                        "elements": [
                            {
                                "element_number": 1,
                                "element_text": "A 2'-substituted nucleoside or nucleotide compound active against HCV NS5B polymerase",
                                "status": "met",
                                "reasoning": "Sofosbuvir is a 2'-fluoro, 2'-methyl substituted nucleoside prodrug active against HCV NS5B polymerase.",
                                "confidence": 0.95,
                                "evidence": "Mechanism of action studies confirm NS5B polymerase inhibition.",
                            },
                        ],
                        "overall_status": "met",
                        "overall_confidence": 0.95,
                        "reasoning": "Patent EXPIRED 2024-04-20. Although claim elements are met, the patent presents no current risk.",
                    },
                ],
                "risk_level": "clear",
                "risk_summary": "Primary compound patent for sofosbuvir. EXPIRED 2024-04-20. No current infringement risk.",
                "design_around_suggestions": [],
                "orange_book_info": None,
                "model_used": "claude-sonnet-4-6",
                "thinking_text": "Expired patent. No current risk regardless of claim scope.",
                "input_tokens": 4100,
                "output_tokens": 890,
            },
            {
                "patent_id": "WO1978000003A1",
                "title": "Pharmaceutical compositions of sofosbuvir with specific excipient combinations",
                "assignee": "Fictional Helix Therapeutics",
                "expiry_date": "2030-06-01",
                "claims_analyzed": [
                    {
                        "claim_number": 1,
                        "claim_type": "independent",
                        "depends_on": None,
                        "preamble": "A pharmaceutical composition comprising sofosbuvir",
                        "transitional_phrase": "and",
                        "elements": [
                            {
                                "element_number": 1,
                                "element_text": "mannitol, microcrystalline cellulose, croscarmellose sodium, and magnesium stearate as excipients",
                                "status": "not_met",
                                "reasoning": "The evaluated compound formulation uses a different excipient combination not including all four of the listed excipients.",
                                "confidence": 0.82,
                                "evidence": "Formulation specification does not include croscarmellose sodium.",
                            },
                        ],
                        "overall_status": "not_met",
                        "overall_confidence": 0.82,
                        "reasoning": "The specific excipient combination is not used in the evaluated formulation.",
                    },
                ],
                "risk_level": "low",
                "risk_summary": "Specific formulation patent requiring a defined excipient combination. Evaluated formulation does not use all listed excipients. Low risk.",
                "design_around_suggestions": [],
                "orange_book_info": None,
                "model_used": "claude-sonnet-4-6",
                "thinking_text": "Formulation patent requiring specific excipient combination. Easy to avoid by using different excipients.",
                "input_tokens": 3800,
                "output_tokens": 780,
            },
        ],
        "doe_assessments": [],
        "invalidity_assessments": [],
        "verification": _verification_ok(),
        "prosecution_findings": [],
        "prosecution_dossiers": [],
        "claim_construction_record": {
            "standard": "Phillips claim construction for U.S. infringement-risk assessment",
            "jurisdictions": ["US"],
            "assumptions": [
                "Structural claim language interpreted according to IUPAC nomenclature conventions."
            ],
            "disputed_terms": [],
            "summary": "Structural claims are unambiguous. No claim construction disputes identified.",
        },
        "future_risk": [],
        "commercial_exposure": {
            "damages_injunction_risk": "high",
            "business_severity": "high",
            "blocking_patent_ids": _SOF_BLOCKING,
            "rationale": [
                "Core compound patent and polymorph patent block commercialisation until 2028 and 2031 respectively."
            ],
            "summary": "Commercialisation of sofosbuvir in the US requires a licence from Fictional Helix Therapeutics.",
        },
        "claim_program_decisions": [],
        "evidence_artifacts": [
            {
                "artifact_id": f"{pid}:search_hit",
                "artifact_type": "search_hit",
                "source_name": "pubchem_sdq,bigquery",
                "authority_tier": "supporting",
                "jurisdiction": "US",
                "patent_id": pid,
                "family_id": _demo_family_id(pid),
                "summary": "Patent retained as material record.",
                "record_basis": ["pubchem_sdq"],
                "linked_node_ids": [
                    f"patent:{pid}",
                    f"family:{_demo_family_id(pid)}",
                ],
            }
            for pid in _SOF_PATENTS
        ],
        "evidence_adapter_results": [
            {
                "adapter_name": "pubchem_sdq",
                "adapter_kind": "search",
                "authority_tier": "supporting",
                "status": "ok",
                "collection_state": "collected",
                "required_before_clear": False,
                "target_patent_ids": _SOF_PATENTS,
                "covered_patent_ids": _SOF_PATENTS,
                "missing_patent_ids": [],
                "artifacts": [],
                "warnings": [],
                "freshness_note": "Records captured during current pipeline run.",
                "artifact_count": len(_SOF_PATENTS),
                "covered_components": [],
                "expected_components": [],
                "missing_components": [],
                "supports_authoritative_findings": False,
            },
        ],
        "collector_runs": [],
        "evidence_collection_plan": [],
        "coverage_gaps": [],
        "matter_graph": _matter_graph(compound_name, _SOF_PATENTS),
        "matter_graph_summary": _matter_graph_summary(compound_name, _SOF_PATENTS),
        "matter_store": {
            "matter_graph": _matter_graph(compound_name, _SOF_PATENTS),
            "matter_graph_summary": _matter_graph_summary(compound_name, _SOF_PATENTS),
            "matter_evidence_index": {
                "source_names": ["pubchem_sdq", "bigquery"],
                "authoritative_source_names": ["patentsview"],
                "supporting_source_names": ["bigquery", "pubchem_sdq"],
                "material_patent_count": len(_SOF_PATENTS),
                "family_count": len(_SOF_PATENTS),
                "analysis_failure_patent_ids": [],
                "critic_flagged_patent_ids": _SOF_BLOCKING,
                "clearance_grade_ready_patent_ids": [],
                "incomplete_patent_ids": _SOF_BLOCKING,
                "clearance_grade_ready_family_ids": [],
                "incomplete_family_ids": [
                    _demo_family_id(patent_id) for patent_id in _SOF_BLOCKING
                ],
                "patent_records": [],
                "family_records": [],
            },
            "prosecution_dossiers": [],
            "claim_program_decisions": [],
            "evidence_artifacts": [],
            "evidence_adapter_results": [],
            "collector_runs": [],
            "evidence_collection_plan": [],
            "coverage_gaps": [],
            "authority_coverage": {
                "policy": "official_plus_licensed",
                "authoritative_source_names": ["patentsview"],
                "supporting_source_names": ["bigquery", "pubchem_sdq"],
                "authoritative_categories_covered": ["authoritative_search_source"],
                "authoritative_categories_missing": ["us_file_wrapper_dossier"],
                "patents_with_authoritative_records": len(_SOF_PATENTS),
                "patents_without_authoritative_records": 0,
                "clearance_grade_ready_patents": 0,
            },
            "record_completeness": {
                "profile": "world_class_us_ep",
                "matter_type": "small_molecule",
                "jurisdictions": ["US"],
                "required_components": [
                    "claims_text",
                    "claim_level_analysis",
                    "authoritative_records",
                ],
                "missing_components": [],
                "blocking_gaps": [],
                "clearance_grade_ready": False,
            },
            "run_observability": {
                "authoritative_source_hit_rate": 1.0,
                "claims_text_coverage": 1.0,
                "family_context_coverage": 1.0,
                "us_file_wrapper_dossier_coverage": 0.0,
                "ep_register_coverage": 0.0,
                "failed_adapter_names": ["epo_ops"],
                "false_clear_risk_flags": ["high_risk_claims"],
                "unresolved_contradictions": [],
            },
            "record_contradictions": [],
        },
        "authority_coverage": {
            "policy": "official_plus_licensed",
            "authoritative_source_names": ["patentsview"],
            "supporting_source_names": ["bigquery", "pubchem_sdq"],
            "authoritative_categories_covered": ["authoritative_search_source"],
            "authoritative_categories_missing": ["us_file_wrapper_dossier"],
            "patents_with_authoritative_records": len(_SOF_PATENTS),
            "patents_without_authoritative_records": 0,
            "clearance_grade_ready_patents": 0,
        },
        "record_completeness": {
            "profile": "world_class_us_ep",
            "matter_type": "small_molecule",
            "jurisdictions": ["US"],
            "required_components": ["claims_text", "claim_level_analysis", "authoritative_records"],
            "missing_components": [],
            "blocking_gaps": [],
            "clearance_grade_ready": False,
        },
        "run_observability": {
            "authoritative_source_hit_rate": 1.0,
            "claims_text_coverage": 1.0,
            "family_context_coverage": 1.0,
            "us_file_wrapper_dossier_coverage": 0.0,
            "ep_register_coverage": 0.0,
            "failed_adapter_names": ["epo_ops"],
            "false_clear_risk_flags": ["high_risk_claims"],
            "unresolved_contradictions": [],
        },
        "matter_evidence_index": {
            "source_names": ["pubchem_sdq", "bigquery"],
            "authoritative_source_names": ["patentsview"],
            "supporting_source_names": ["bigquery", "pubchem_sdq"],
            "material_patent_count": len(_SOF_PATENTS),
            "family_count": len(_SOF_PATENTS),
            "analysis_failure_patent_ids": [],
            "critic_flagged_patent_ids": _SOF_BLOCKING,
            "clearance_grade_ready_patent_ids": [],
            "incomplete_patent_ids": _SOF_BLOCKING,
            "clearance_grade_ready_family_ids": [],
            "incomplete_family_ids": [_demo_family_id(patent_id) for patent_id in _SOF_BLOCKING],
            "patent_records": [],
            "family_records": [],
        },
        "total_patents_found": 185,
        "patents_after_triage": 4,
        "search_sources_used": ["pubchem_sdq", "bigquery", "patentsview"],
        "source_health": _source_health(_SOF_PATENTS),
        "scholarly_prior_art_count": 0,
        "analysis_failures": [],
        "data_limitations": [],
        "audit_trail": audit,
        "patent_narratives": {
            "WO1978000002A1": "Core sofosbuvir prodrug patent. Orange Book listed. 2028 expiry. Blocking.",
            "WO1978000004A1": "Polymorph Form 1 patent. Orange Book listed. 2031 expiry. Blocking if Form 1 used.",
            "WO1978000001A1": "Primary compound patent. EXPIRED 2024-04-20. No current risk.",
            "WO1978000003A1": "Specific formulation patent. Low risk; evaluated formulation uses different excipients.",
        },
        "disclaimer": (
            "IMPORTANT: This report is an AI-assisted screening tool and does NOT constitute legal advice "
            "or a formal Freedom-to-Operate opinion."
        ),
        "llm_models_used": {
            "triage": "claude-haiku-4-5-20251001",
            "analysis": "claude-sonnet-4-6",
        },
        "drawing_analyses": [],
        "drawing_summary": {},
        "report_pipeline": "world_class_adaptive",
        "reasoning_traces": [],
        "patent_details": {},
        "action_items": [
            {
                "action_type": "license",
                "priority": "critical",
                "description": "Pursue a licence from Fictional Helix Therapeutics for WO1978000002A1 (core prodrug patent, expiry 2028) and WO1978000004A1 (polymorph patent, expiry 2031).",
                "patent_ids": ["WO1978000002A1", "WO1978000004A1"],
                "reasoning": "Both blocking patents are held by Fictional Helix Therapeutics. Licences are available via the Fictional Access Consortium for low- and middle-income countries.",
                "estimated_timeline": "6-18 months for licence negotiation",
            },
            {
                "action_type": "halt",
                "priority": "critical",
                "description": "Do not commence commercialisation of sofosbuvir in the US without a valid licence or successful invalidity outcome.",
                "patent_ids": ["WO1978000002A1"],
                "reasoning": "Core prodrug patent claims are unambiguously met. No design-around is possible without creating a different compound.",
                "estimated_timeline": "Immediate",
            },
        ],
        "bibliography": [],
        "verification_summary": {},
        "factual_accuracy_rate": 0.97,
        "total_input_tokens": 23900,
        "total_output_tokens": 5970,
        "estimated_cost_usd": 3.84,
        "step_token_usage": [
            {
                "step_name": "search",
                "model_role": "triage",
                "model_name": "claude-haiku-4-5-20251001",
                "input_tokens": 2800,
                "output_tokens": 720,
            },
            {
                "step_name": "triage",
                "model_role": "triage",
                "model_name": "claude-haiku-4-5-20251001",
                "input_tokens": 6300,
                "output_tokens": 1400,
            },
            {
                "step_name": "analysis",
                "model_role": "analysis",
                "model_name": "claude-sonnet-4-6",
                "input_tokens": 14800,
                "output_tokens": 3850,
            },
        ],
    }


# ── Legacy compound scenario Delta ─────────────────────────────────────────────

_ASP_PATENTS = ["US0000000011A1"]


def _raw_aspirin_report() -> dict:
    """Return a synthetic one-publication clear-outcome component-test report."""
    compound_name = "aspirin"
    all_ids = [f"US{i + 100:010d}A1" for i in range(127)] + _ASP_PATENTS
    audit = _search_funnel(all_ids, _ASP_PATENTS, _ASP_PATENTS)
    return {
        "report_id": str(uuid.uuid4()),
        "generated_at": "2026-04-07T10:11:00+00:00",
        "praviar_pipeline_version": "0.1.0-demo",
        "compound": {
            "name": "aspirin",
            "canonical_smiles": "CC(=O)Oc1ccccc1C(=O)O",
            "inchi": "InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)",
            "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            "pubchem_cid": 2244,
            "synonyms": ["aspirin", "acetylsalicylic acid", "2-acetyloxybenzoic acid"],
            "cas_numbers": ["50-78-2"],
            "molecular_formula": "C9H8O4",
            "molecular_weight": 180.16,
            "morgan_fp": "",
            "maccs_keys": "",
            "functional_groups": ["ester", "carboxylic acid", "aromatic"],
            "related_compounds": [],
            "original_input": "aspirin",
            "input_type": "name",
        },
        "risk_summary": {
            "overall_risk": "clear",
            "blocking_patents_count": 0,
            "total_patents_analyzed": 1,
            "key_risks": [],
            "executive_summary": (
                "This freedom-to-operate analysis evaluated aspirin (acetylsalicylic acid, CID 2244) against 128 patents "
                "discovered across PubChem and BigQuery. After hard-filtering and triage, 1 patent was selected for claim-level "
                "analysis.\n\n"
                "No blocking patent risks were identified. The single patent reviewed (US0000000011A1) covers a novel aspirin "
                "formulation combining aspirin with a specific phosphodiesterase inhibitor and antioxidant blend. The evaluated "
                "compound — plain aspirin API — does not meet the combination claim requirements. All claim elements relating "
                "to the co-formulated agents are not met.\n\n"
                "Aspirin itself is a well-established compound with an expired primary compound patent (Fictional Legacy Pharma, expired 1917) "
                "and is freely practised worldwide. Standard monitoring is recommended to track any novel formulation patents "
                "that may be relevant to specific delivery routes or combination products."
            ),
            "summary_validation_issues": [],
        },
        "clearance_decision": _clearance_decision("clear", 0.97, _ASP_PATENTS, []),
        "decision_scope": {
            "matter_type": "small_molecule",
            "jurisdictions": ["US"],
            "asset_classes": ["compound"],
            "supports_positive_clearance": True,
            "summary": "US evidence supports a positive clearance conclusion for plain aspirin API.",
        },
        "supporting_scope": {
            "matter_type": "small_molecule",
            "jurisdictions": [],
            "asset_classes": ["compound"],
            "supports_positive_clearance": False,
            "summary": "No supporting-only jurisdictions were material.",
        },
        "certification_scope": {
            "certified_jurisdictions": ["US", "EP"],
            "certified_matter_types": ["small_molecule"],
            "certified_asset_classes": ["compound"],
            "attorney_supervised_matter_types": [],
            "attorney_supervised_asset_classes": [],
            "supporting_only_jurisdictions": [],
            "current_matter_type_certified": True,
            "attorney_supervision_required": False,
            "summary": "Direct-clearance certification covers US and EP small-molecule cohort.",
        },
        "cohort_status": "certified",
        "jurisdiction_decisions": [_jurisdiction_decision("clear", 0.97, _ASP_PATENTS, [])],
        "patent_analyses": [
            {
                "patent_id": "US0000000011A1",
                "title": "Aspirin-containing combination formulation with phosphodiesterase inhibitor and antioxidant",
                "assignee": "Fictional Cobalt Therapeutics",
                "expiry_date": "2022-03-14",
                "claims_analyzed": [
                    {
                        "claim_number": 1,
                        "claim_type": "independent",
                        "depends_on": None,
                        "preamble": "A pharmaceutical composition comprising aspirin",
                        "transitional_phrase": "and",
                        "elements": [
                            {
                                "element_number": 1,
                                "element_text": "aspirin in an amount of 81-325 mg",
                                "status": "met",
                                "reasoning": "The evaluated compound is aspirin API.",
                                "confidence": 0.99,
                                "evidence": "Compound identity confirmed.",
                            },
                            {
                                "element_number": 2,
                                "element_text": "a phosphodiesterase type 5 inhibitor selected from sildenafil, tadalafil, or vardenafil",
                                "status": "not_met",
                                "reasoning": "The evaluated compound is plain aspirin API with no phosphodiesterase inhibitor co-formulation.",
                                "confidence": 0.99,
                                "evidence": "Formulation specification contains no PDE5 inhibitor.",
                            },
                            {
                                "element_number": 3,
                                "element_text": "alpha-tocopherol or ascorbic acid as an antioxidant",
                                "status": "not_met",
                                "reasoning": "No antioxidant is present in the evaluated formulation.",
                                "confidence": 0.99,
                                "evidence": "Formulation specification contains no added antioxidant.",
                            },
                        ],
                        "overall_status": "not_met",
                        "overall_confidence": 0.99,
                        "reasoning": "Two of three elements are not met. Plain aspirin API does not include the required PDE5 inhibitor or antioxidant co-formulation. Note: this patent is also EXPIRED (2022-03-14).",
                    },
                ],
                "risk_level": "clear",
                "risk_summary": "Combination formulation patent. Plain aspirin API does not meet combination claim elements. Patent also expired 2022-03-14.",
                "design_around_suggestions": [],
                "orange_book_info": None,
                "model_used": "claude-sonnet-4-6",
                "thinking_text": "Not met on combination elements. Also expired. Double-clear.",
                "input_tokens": 3200,
                "output_tokens": 720,
            },
        ],
        "doe_assessments": [],
        "invalidity_assessments": [],
        "verification": _verification_ok(),
        "prosecution_findings": [],
        "prosecution_dossiers": [],
        "claim_construction_record": {
            "standard": "Phillips claim construction for U.S. infringement-risk assessment",
            "jurisdictions": ["US"],
            "assumptions": ["Combination claim interpreted to require all recited components."],
            "disputed_terms": [],
            "summary": "No claim construction issues identified.",
        },
        "future_risk": [],
        "commercial_exposure": {
            "damages_injunction_risk": "none",
            "business_severity": "low",
            "blocking_patent_ids": [],
            "rationale": [
                "No blocking patents identified. Aspirin is a generic compound off-patent."
            ],
            "summary": "Clear to commercialise plain aspirin API in the US.",
        },
        "claim_program_decisions": [],
        "evidence_artifacts": [
            {
                "artifact_id": "US0000000011A1:search_hit",
                "artifact_type": "search_hit",
                "source_name": "pubchem_sdq",
                "authority_tier": "supporting",
                "jurisdiction": "US",
                "patent_id": "US0000000011A1",
                "family_id": _demo_family_id("US0000000011A1"),
                "summary": "Patent retained as material record.",
                "record_basis": ["pubchem_sdq"],
                "linked_node_ids": ["patent:US0000000011A1"],
            },
        ],
        "evidence_adapter_results": [
            {
                "adapter_name": "pubchem_sdq",
                "adapter_kind": "search",
                "authority_tier": "supporting",
                "status": "ok",
                "collection_state": "collected",
                "required_before_clear": False,
                "target_patent_ids": _ASP_PATENTS,
                "covered_patent_ids": _ASP_PATENTS,
                "missing_patent_ids": [],
                "artifacts": [],
                "warnings": [],
                "freshness_note": "Records captured during current pipeline run.",
                "artifact_count": 1,
                "covered_components": [],
                "expected_components": [],
                "missing_components": [],
                "supports_authoritative_findings": False,
            },
        ],
        "collector_runs": [],
        "evidence_collection_plan": [],
        "coverage_gaps": [],
        "matter_graph": _matter_graph(compound_name, _ASP_PATENTS),
        "matter_graph_summary": _matter_graph_summary(compound_name, _ASP_PATENTS),
        "matter_store": {
            "matter_graph": _matter_graph(compound_name, _ASP_PATENTS),
            "matter_graph_summary": _matter_graph_summary(compound_name, _ASP_PATENTS),
            "matter_evidence_index": {
                "source_names": ["pubchem_sdq"],
                "authoritative_source_names": ["patentsview"],
                "supporting_source_names": ["pubchem_sdq"],
                "material_patent_count": 1,
                "family_count": 1,
                "analysis_failure_patent_ids": [],
                "critic_flagged_patent_ids": [],
                "clearance_grade_ready_patent_ids": ["US0000000011A1"],
                "incomplete_patent_ids": [],
                "clearance_grade_ready_family_ids": [_demo_family_id("US0000000011A1")],
                "incomplete_family_ids": [],
                "patent_records": [],
                "family_records": [],
            },
            "prosecution_dossiers": [],
            "claim_program_decisions": [],
            "evidence_artifacts": [],
            "evidence_adapter_results": [],
            "collector_runs": [],
            "evidence_collection_plan": [],
            "coverage_gaps": [],
            "authority_coverage": {
                "policy": "official_plus_licensed",
                "authoritative_source_names": ["patentsview"],
                "supporting_source_names": ["pubchem_sdq"],
                "authoritative_categories_covered": [
                    "authoritative_search_source",
                    "family_record",
                ],
                "authoritative_categories_missing": [],
                "patents_with_authoritative_records": 1,
                "patents_without_authoritative_records": 0,
                "clearance_grade_ready_patents": 1,
            },
            "record_completeness": {
                "profile": "world_class_us_ep",
                "matter_type": "small_molecule",
                "jurisdictions": ["US"],
                "required_components": [
                    "claims_text",
                    "claim_level_analysis",
                    "authoritative_records",
                ],
                "missing_components": [],
                "blocking_gaps": [],
                "clearance_grade_ready": True,
            },
            "run_observability": {
                "authoritative_source_hit_rate": 1.0,
                "claims_text_coverage": 1.0,
                "family_context_coverage": 1.0,
                "us_file_wrapper_dossier_coverage": 0.0,
                "ep_register_coverage": 0.0,
                "failed_adapter_names": [],
                "false_clear_risk_flags": [],
                "unresolved_contradictions": [],
            },
            "record_contradictions": [],
        },
        "authority_coverage": {
            "policy": "official_plus_licensed",
            "authoritative_source_names": ["patentsview"],
            "supporting_source_names": ["pubchem_sdq"],
            "authoritative_categories_covered": ["authoritative_search_source", "family_record"],
            "authoritative_categories_missing": [],
            "patents_with_authoritative_records": 1,
            "patents_without_authoritative_records": 0,
            "clearance_grade_ready_patents": 1,
        },
        "record_completeness": {
            "profile": "world_class_us_ep",
            "matter_type": "small_molecule",
            "jurisdictions": ["US"],
            "required_components": ["claims_text", "claim_level_analysis", "authoritative_records"],
            "missing_components": [],
            "blocking_gaps": [],
            "clearance_grade_ready": True,
        },
        "run_observability": {
            "authoritative_source_hit_rate": 1.0,
            "claims_text_coverage": 1.0,
            "family_context_coverage": 1.0,
            "us_file_wrapper_dossier_coverage": 0.0,
            "ep_register_coverage": 0.0,
            "failed_adapter_names": [],
            "false_clear_risk_flags": [],
            "unresolved_contradictions": [],
        },
        "matter_evidence_index": {
            "source_names": ["pubchem_sdq"],
            "authoritative_source_names": ["patentsview"],
            "supporting_source_names": ["pubchem_sdq"],
            "material_patent_count": 1,
            "family_count": 1,
            "analysis_failure_patent_ids": [],
            "critic_flagged_patent_ids": [],
            "clearance_grade_ready_patent_ids": ["US0000000011A1"],
            "incomplete_patent_ids": [],
            "clearance_grade_ready_family_ids": [_demo_family_id("US0000000011A1")],
            "incomplete_family_ids": [],
            "patent_records": [],
            "family_records": [],
        },
        "total_patents_found": 128,
        "patents_after_triage": 1,
        "search_sources_used": ["pubchem_sdq", "bigquery"],
        "source_health": {
            "entries": [
                {"source": "pubchem_sdq", "status": "ok", "patent_count": 1, "error_message": ""},
                {"source": "bigquery", "status": "ok", "patent_count": 0, "error_message": ""},
            ]
        },
        "scholarly_prior_art_count": 0,
        "analysis_failures": [],
        "data_limitations": [],
        "audit_trail": audit,
        "patent_narratives": {
            "US0000000011A1": "Combination formulation patent. Expired 2022-03-14. Plain aspirin API does not meet combination claim elements.",
        },
        "disclaimer": (
            "IMPORTANT: This report is an AI-assisted screening tool and does NOT constitute legal advice "
            "or a formal Freedom-to-Operate opinion."
        ),
        "llm_models_used": {
            "triage": "claude-haiku-4-5-20251001",
            "analysis": "claude-sonnet-4-6",
        },
        "drawing_analyses": [],
        "drawing_summary": {},
        "report_pipeline": "world_class_adaptive",
        "reasoning_traces": [],
        "patent_details": {},
        "action_items": [
            {
                "action_type": "monitor",
                "priority": "low",
                "description": "Continue periodic monitoring of formulation patents to catch any novel combination products that may be relevant to specific delivery routes.",
                "patent_ids": [],
                "reasoning": "Plain aspirin API is clear. Novel formulations or combination products would require separate FTO analysis.",
                "estimated_timeline": "Annual review",
            },
        ],
        "bibliography": [],
        "verification_summary": {},
        "factual_accuracy_rate": 0.99,
        "total_input_tokens": 6200,
        "total_output_tokens": 1420,
        "estimated_cost_usd": 0.96,
        "step_token_usage": [
            {
                "step_name": "search",
                "model_role": "triage",
                "model_name": "claude-haiku-4-5-20251001",
                "input_tokens": 1800,
                "output_tokens": 380,
            },
            {
                "step_name": "triage",
                "model_role": "triage",
                "model_name": "claude-haiku-4-5-20251001",
                "input_tokens": 2200,
                "output_tokens": 560,
            },
            {
                "step_name": "analysis",
                "model_role": "analysis",
                "model_name": "claude-sonnet-4-6",
                "input_tokens": 2200,
                "output_tokens": 480,
            },
        ],
    }


def _demo_claim_text(patent: dict) -> str:
    claims_text: list[str] = []
    for claim in patent.get("claims_analyzed") or []:
        claim_number = int(claim.get("claim_number") or 1)
        elements = [
            str(element.get("element_text") or "").strip()
            for element in claim.get("elements") or []
            if str(element.get("element_text") or "").strip()
        ]
        claim_parts = [str(claim.get("preamble") or "").strip(), *elements]
        claims_text.append(
            f"Claim {claim_number}: " + "; ".join(part for part in claim_parts if part)
        )
    return "\n".join(claims_text)


def _demo_claim_program_decision(
    patent: dict,
    claim: dict,
) -> dict:
    risk = str(patent.get("risk_level") or "clear").lower()
    literal_risk = "low" if risk in {"clear", "low"} else risk
    commercial_severity = {
        "high": "high",
        "medium": "medium",
    }.get(literal_risk, "low")
    patent_id = str(patent["patent_id"])
    is_blocker = literal_risk == "high"
    return {
        "patent_id": patent_id,
        "claim_number": int(claim.get("claim_number") or 1),
        "jurisdiction": publication_jurisdiction(patent_id),
        "literal_outcome": str(claim.get("overall_status") or "not_met"),
        "literal_risk": literal_risk,
        "doe_risk": "not_assessed",
        "invalidity_strength": "",
        "prosecution_risk_flags": [],
        "prosecution_risk_level": "",
        "post_grant_risk_level": "",
        "scope_constrained": False,
        "future_risk_flags": [],
        "legal_status": "active" if is_blocker else "",
        "legal_status_provenance_verified": is_blocker,
        "prospective_enforceability": "active" if is_blocker else "unresolved",
        "accused_acts": ["manufacture", "sale"] if is_blocker else [],
        "accused_acts_verified": is_blocker,
        "commercial_severity": commercial_severity,
        "evidence_sufficient": True,
        "missing_components": [],
        "record_basis": (
            [
                "claim_level_analysis",
                "synthetic_fixture_accused_acts",
                "synthetic_fixture_legal_status",
            ]
            if is_blocker
            else ["claim_level_analysis"]
        ),
        "rationale": [str(claim.get("reasoning") or "The claim elements were reviewed.")],
    }


def _sync_demo_decision_audit(
    report: dict,
    *,
    downgrade_clearance: bool,
) -> None:
    clearance = report["clearance_decision"]
    audit = clearance["decision_audit"]
    coverage = audit["coverage_summary"]
    decisions = report["claim_program_decisions"]

    blocking_decisions = [decision for decision in decisions if decision["literal_risk"] == "high"]
    medium_decisions = [decision for decision in decisions if decision["literal_risk"] == "medium"]
    blocking_patent_ids = sorted({str(decision["patent_id"]) for decision in blocking_decisions})
    medium_patent_ids = sorted({str(decision["patent_id"]) for decision in medium_decisions})
    audit["claim_program_summary"] = {
        "total_claim_programs_reviewed": len(decisions),
        "patent_level_fallback_count": 0,
        "blocking_claim_ids": [
            f"{decision['patent_id']}#claim{decision['claim_number']}"
            for decision in blocking_decisions
        ],
        "contested_claim_ids": [],
        "medium_risk_claim_ids": [
            f"{decision['patent_id']}#claim{decision['claim_number']}"
            for decision in medium_decisions
        ],
        "claims_with_strong_invalidity": [],
        "claims_with_insufficient_evidence": [],
        "blocking_patent_ids": blocking_patent_ids,
        "contested_patent_ids": [],
        "medium_risk_patent_ids": medium_patent_ids,
    }

    reviewed_patent_ids = list(dict.fromkeys(coverage["reviewed_patent_ids"]))
    reviewed_by_jurisdiction: defaultdict[str, list[str]] = defaultdict(list)
    for patent_id in reviewed_patent_ids:
        reviewed_by_jurisdiction[publication_jurisdiction(patent_id)].append(patent_id)
    coverage["reviewed_us_patent_ids"] = reviewed_by_jurisdiction.get("US", [])
    coverage["reviewed_ep_patent_ids"] = reviewed_by_jurisdiction.get("EP", [])

    source_health = report.get("source_health") or {}
    failed_sources = sorted(
        {
            str(entry.get("source") or "").strip()
            for entry in source_health.get("entries") or []
            if str(entry.get("status") or "").lower() == "failed"
            and str(entry.get("source") or "").strip()
        }
    )
    coverage["failed_source_names"] = failed_sources
    audit["failed_sources"] = failed_sources

    decisive_ids = blocking_patent_ids or reviewed_patent_ids[:1]
    audit["decisive_references"] = [
        {
            "category": (
                "blocking_patent" if patent_id in blocking_patent_ids else "clearance_support"
            ),
            "summary": "Governed claim-program decision for the synthetic demo matter.",
            "patent_id": patent_id,
            "jurisdiction": publication_jurisdiction(patent_id),
            "source_name": "synthetic_fixture",
            "signal": ("blocking" if patent_id in blocking_patent_ids else "reviewed"),
        }
        for patent_id in decisive_ids
    ]

    if downgrade_clearance:
        clearance["decision"] = "unclear"
        audit["evidence_sufficient_for_clearance"] = False
        audit["insufficiency_reasons"] = ["Synthetic demo evidence is not release certified."]
        report["risk_summary"]["overall_risk"] = "medium"

    report["jurisdiction_decisions"] = []
    for jurisdiction, patent_ids in reviewed_by_jurisdiction.items():
        if not patent_ids:
            continue
        jurisdiction_blockers = sorted(set(patent_ids) & set(blocking_patent_ids))
        if jurisdiction_blockers:
            decision = "blocked"
            gate_failures = ["Evidence indicates blocking risk."]
            evidence_sufficient = False
        elif downgrade_clearance:
            decision = "unclear"
            gate_failures = ["Synthetic demo evidence is not release certified."]
            evidence_sufficient = False
        else:
            decision = "clear"
            gate_failures = []
            evidence_sufficient = True
        report["jurisdiction_decisions"].append(
            {
                "jurisdiction": jurisdiction,
                "decision": decision,
                "decision_confidence": clearance["decision_confidence"],
                "evidence_quality": clearance["evidence_quality"],
                "evidence_sufficient_for_clearance": evidence_sufficient,
                "supports_positive_clearance": True,
                "lane_status": "counsel_ready",
                "local_review_required": False,
                "gate_failures": gate_failures,
                "reviewed_patent_ids": patent_ids,
                "blocking_patent_ids": jurisdiction_blockers,
                "reasoning": [f"Reviewed {len(patent_ids)} material {jurisdiction} patent(s)."],
            }
        )

    missing_claims = set(coverage["patents_missing_claims"])
    missing_family = set(coverage["patents_missing_family_context"])
    missing_prosecution = set(coverage["us_patents_missing_prosecution_context"])
    missing_file_wrapper = set(coverage.get("us_patents_missing_file_wrapper_dossier") or [])
    missing_ep_register = set(coverage["ep_patents_missing_register_context"])
    audit.update(
        {
            "queried_sources_count": len(set(coverage["queried_source_names"])),
            "successful_sources_count": len(set(coverage["successful_source_names"])),
            "authoritative_sources_count": len(set(coverage["authoritative_source_names"])),
            "material_patents_reviewed": len(set(reviewed_patent_ids)),
            "material_us_patents": len(set(reviewed_by_jurisdiction.get("US", []))),
            "material_ep_patents": len(set(reviewed_by_jurisdiction.get("EP", []))),
            "analysis_failures_count": len(set(coverage["failed_analysis_patent_ids"])),
            "clearance_grade_ready_patents": len(set(coverage["clearance_grade_ready_patent_ids"])),
            "incomplete_material_patents": len(set(coverage["incomplete_patent_ids"])),
            "clearance_grade_ready_families": len(
                set(coverage["clearance_grade_ready_family_ids"])
            ),
            "incomplete_material_families": len(set(coverage["incomplete_family_ids"])),
            "patents_with_claims": len(set(reviewed_patent_ids) - missing_claims),
            "patents_with_family": len(set(reviewed_patent_ids) - missing_family),
            "us_patents_with_prosecution_context": len(
                set(reviewed_by_jurisdiction.get("US", [])) - missing_prosecution
            ),
            "us_patents_with_file_wrapper_dossier": len(
                set(reviewed_by_jurisdiction.get("US", [])) - missing_file_wrapper
            ),
            "ep_patents_with_register_context": len(
                set(reviewed_by_jurisdiction.get("EP", [])) - missing_ep_register
            ),
        }
    )

    decision = str(clearance["decision"])
    analyzed_count = len(report["patent_analyses"])
    blocker_count = len(blocking_patent_ids)
    report["risk_summary"].update(
        {
            "blocking_patents_count": blocker_count,
            "total_patents_analyzed": analyzed_count,
            "executive_summary": (
                f"Clearance decision: {decision.upper()}. {blocker_count} blocking "
                f"patent{'s' if blocker_count != 1 else ''} identified from "
                f"{analyzed_count} analyzed."
            ),
        }
    )
    report["commercial_exposure"]["blocking_patent_ids"] = blocking_patent_ids
    if not blocking_patent_ids:
        report["commercial_exposure"]["damages_injunction_risk"] = "limited"


def _sync_demo_blocker_family_records(report: dict) -> None:
    """Project demo decisions through the production blocker-family builder."""
    audit = report["clearance_decision"]["decision_audit"]
    summary = ClaimProgramSummary.model_validate(audit["claim_program_summary"])
    blocking_patent_ids = set(summary.blocking_patent_ids)

    family_id_by_patent: dict[str, str] = {}
    for node in report["matter_graph"].get("nodes") or []:
        if str(node.get("node_type") or "") != "patent":
            continue
        patent_id = str(node.get("patent_id") or "").strip()
        family_id = str(node.get("family_id") or "").strip()
        if not patent_id or not family_id:
            raise ValueError("demo patent nodes require patent and family identities")
        if patent_id in family_id_by_patent:
            raise ValueError(f"duplicate demo patent-family membership for {patent_id}")
        family_id_by_patent[patent_id] = family_id

    evidence_index = deepcopy(report["matter_evidence_index"])
    patent_analyses = report.get("patent_analyses") or []
    analyzed_patent_ids = [str(patent["patent_id"]) for patent in patent_analyses]
    if set(family_id_by_patent) != set(analyzed_patent_ids):
        raise ValueError("demo matter graph must exactly cover analyzed patents")

    source_names = list(evidence_index.get("source_names") or [])
    authoritative_source_names = list(evidence_index.get("authoritative_source_names") or [])
    supporting_source_names = list(evidence_index.get("supporting_source_names") or [])
    authoritative_record_categories = (
        ["authoritative_search_source", "family_record"] if authoritative_source_names else []
    )
    ready_patent_ids = set(evidence_index.get("clearance_grade_ready_patent_ids") or [])
    incomplete_patent_ids = set(evidence_index.get("incomplete_patent_ids") or [])

    patent_records: list[dict] = []
    family_patent_ids: defaultdict[str, list[str]] = defaultdict(list)
    for patent in patent_analyses:
        patent_id = str(patent["patent_id"])
        family_id = family_id_by_patent[patent_id]
        jurisdiction = publication_jurisdiction(patent_id)
        family_patent_ids[family_id].append(patent_id)
        patent_records.append(
            {
                "patent_id": patent_id,
                "jurisdiction": jurisdiction,
                "title": str(patent.get("title") or ""),
                "legal_status": ("active" if patent_id in blocking_patent_ids else "unresolved"),
                "source_names": source_names,
                "authoritative_source_names": authoritative_source_names,
                "supporting_source_names": supporting_source_names,
                "assignees": [str(patent["assignee"])] if patent.get("assignee") else [],
                "family_id": family_id,
                "family_member_count": 1,
                "family_jurisdictions": [jurisdiction],
                "family_broadest": True,
                "has_claims_text": True,
                "has_family_context": True,
                "authoritative_record_categories": authoritative_record_categories,
                "analysis_completed": True,
                "claims_analyzed_count": len(patent.get("claims_analyzed") or []),
                "risk_level": str(patent.get("risk_level") or ""),
                "clearance_grade_ready": patent_id in ready_patent_ids,
                "gate_failures": (
                    ["Synthetic demo evidence is not release certified."]
                    if patent_id in incomplete_patent_ids
                    else []
                ),
            }
        )

    family_records = []
    ready_family_ids = set(evidence_index.get("clearance_grade_ready_family_ids") or [])
    incomplete_family_ids = set(evidence_index.get("incomplete_family_ids") or [])
    for family_id, material_patent_ids in sorted(family_patent_ids.items()):
        material_patent_ids = sorted(material_patent_ids)
        family_blockers = sorted(set(material_patent_ids) & blocking_patent_ids)
        family_incomplete_patents = sorted(set(material_patent_ids) & incomplete_patent_ids)
        family_records.append(
            {
                "family_id": family_id,
                "material_patent_ids": material_patent_ids,
                "jurisdictions": sorted(
                    {publication_jurisdiction(patent_id) for patent_id in material_patent_ids}
                ),
                "broadest_patent_id": material_patent_ids[0],
                "member_count": len(material_patent_ids),
                "blocking_patent_ids": family_blockers,
                "authoritative_record_categories": (
                    ["family_record"] if authoritative_source_names else []
                ),
                "clearance_grade_ready": family_id in ready_family_ids,
                "gate_failures": (
                    ["Synthetic demo evidence is not release certified."]
                    if family_id in incomplete_family_ids
                    else []
                ),
                "clearance_grade_ready_patent_ids": sorted(
                    set(material_patent_ids) & ready_patent_ids
                ),
                "incomplete_patent_ids": family_incomplete_patents,
            }
        )

    evidence_index.update(
        {
            "material_patent_count": len(patent_records),
            "family_count": len(family_records),
            "patent_records": patent_records,
            "family_records": family_records,
        }
    )
    governed_evidence_index = MatterEvidenceIndex.model_validate(evidence_index)
    governed_evidence_payload = governed_evidence_index.model_dump(mode="json")
    report["matter_evidence_index"] = governed_evidence_payload
    report["matter_store"]["matter_evidence_index"] = deepcopy(governed_evidence_payload)

    claim_decisions = [
        ClaimProgramDecision.model_validate(decision)
        for decision in report["claim_program_decisions"]
    ]
    blocker_families = build_blocker_family_records(
        decision=report["clearance_decision"]["decision"],
        claim_program_summary=summary,
        claim_program_decisions=claim_decisions,
        matter_evidence_index=governed_evidence_index,
    )
    audit["blocker_families"] = [family.model_dump(mode="json") for family in blocker_families]


def _sync_demo_authority_coverage(report: dict) -> None:
    evidence_index = report["matter_evidence_index"]
    patent_records = evidence_index.get("patent_records") or []
    covered_categories = sorted(
        {
            str(category)
            for record in patent_records
            if isinstance(record, dict)
            for category in record.get("authoritative_record_categories") or []
            if str(category).strip()
        }
    )
    required_categories = {
        COMPONENT_TO_CATEGORY[component]
        for component in report["record_completeness"].get("required_components", [])
        if component in COMPONENT_TO_CATEGORY
    }
    records_with_authority = sum(
        1
        for record in patent_records
        if isinstance(record, dict)
        and any(
            str(category).strip()
            for category in record.get("authoritative_record_categories") or []
        )
    )
    material_patent_count = int(evidence_index.get("material_patent_count") or 0)
    authority_coverage = {
        "policy": "official_plus_licensed",
        "authoritative_source_names": list(evidence_index.get("authoritative_source_names") or []),
        "supporting_source_names": list(evidence_index.get("supporting_source_names") or []),
        "authoritative_categories_covered": covered_categories,
        "authoritative_categories_missing": sorted(required_categories - set(covered_categories)),
        "patents_with_authoritative_records": records_with_authority,
        "patents_without_authoritative_records": max(
            0, material_patent_count - records_with_authority
        ),
        "clearance_grade_ready_patents": len(
            set(evidence_index.get("clearance_grade_ready_patent_ids") or [])
        ),
    }
    report["authority_coverage"] = authority_coverage
    report["matter_store"]["authority_coverage"] = deepcopy(authority_coverage)


def _govern_demo_report(
    report: dict,
    *,
    downgrade_clearance: bool = False,
    verification_failure: bool = False,
    generated_at: datetime | None = None,
) -> dict:
    """Bring a dev-only synthetic fixture through the live report access contract."""
    report = deepcopy(report)
    generated_at = generated_at or datetime.now(UTC)
    report["generated_at"] = generated_at.isoformat()
    entries: list[dict] = []
    spans: dict[str, dict] = {}
    patent_details: dict[str, dict] = {}
    claim_program_decisions: list[dict] = []

    for patent in report.get("patent_analyses") or []:
        patent_id = str(patent["patent_id"])
        claims_text = _demo_claim_text(patent)
        provenance = build_claim_text_provenance(
            patent_id=patent_id,
            claims_text=claims_text,
            source=PatentSource.SYNTHETIC_FIXTURE,
            artifact_locator=f"praviar-demo://claim-text/{patent_id}",
            collector_identity="dev.synthetic_fixture",
            retrieved_at=generated_at,
        ).model_dump(mode="json")
        patent_details[patent_id] = {
            "claims_text": claims_text,
            "claims_text_source": "synthetic_fixture",
            "claims_text_provenance": provenance,
        }

        for claim in patent.get("claims_analyzed") or []:
            statuses = {
                str(element.get("status") or "unclear").strip().lower()
                for element in claim.get("elements") or []
            }
            claim["overall_status"] = (
                "not_met"
                if "not_met" in statuses
                else (
                    "unclear"
                    if "unclear" in statuses
                    else ("partially_met" if "partially_met" in statuses else "met")
                )
            )
            decision = _demo_claim_program_decision(patent, claim)
            claim_program_decisions.append(decision)
            claim_number = int(decision["claim_number"])
            for element in claim.get("elements") or []:
                element_number = int(element.get("element_number") or 1)
                span_id = f"span-{patent_id}-{claim_number}-{element_number}"
                assertion_id = f"assertion-{patent_id}-{claim_number}-{element_number}"
                spans[span_id] = {
                    "span_id": span_id,
                    "source_type": "verified_claim_text",
                    "patent_id": patent_id,
                    "claim_number": claim_number,
                    "element_number": element_number,
                    "citation": f"{patent_id} claim {claim_number}",
                    "excerpt": str(element.get("element_text") or claims_text),
                    "source_document_id": patent_id,
                    "source_name": "synthetic_fixture",
                    "source_text_sha256": provenance["artifact_sha256"],
                    "source_retrieved_at": provenance["retrieved_at"],
                    "source_artifact_locator": provenance["artifact_locator"],
                    "collector_identity": provenance["collector_identity"],
                    "collector_version": provenance["collector_version"],
                    "provenance_schema_version": provenance["schema_version"],
                    "claim_numbers": provenance["claim_numbers"],
                    "independent_claim_numbers": provenance["independent_claim_numbers"],
                    "retrieval_complete": provenance["retrieval_complete"],
                    "provenance_cassette_sha256": provenance["cassette_sha256"],
                }
                entries.append(
                    {
                        "assertion_id": assertion_id,
                        "patent_id": patent_id,
                        "claim_number": claim_number,
                        "element_number": element_number,
                        "report_section": "claim_element_analysis",
                        "assertion_text": (
                            f"Claim {claim_number} element {element_number} was "
                            f"assessed as {element.get('status') or 'not_assessed'}."
                        ),
                        "source_span_ids": [span_id],
                        "support_status": "supported",
                        "customer_visible": True,
                        "review_required": False,
                    }
                )

    report["claim_source_span_map"] = {
        "generated_from": "dev_seed_fixture",
        "entries": entries,
        "spans": spans,
        "unsupported_customer_visible_claim_count": 0,
        "needs_review_count": 0,
    }
    report["patent_details"] = patent_details
    report["claim_program_decisions"] = claim_program_decisions
    _sync_demo_decision_audit(
        report,
        downgrade_clearance=downgrade_clearance,
    )
    _sync_demo_blocker_family_records(report)
    _sync_demo_authority_coverage(report)
    report["matter_store"]["claim_program_decisions"] = deepcopy(claim_program_decisions)
    incorrect_claims = 1 if verification_failure and entries else 0
    correct_claims = len(entries) - incorrect_claims
    factual_accuracy_rate = correct_claims / len(entries) if entries else 0.0
    report["factual_accuracy_rate"] = factual_accuracy_rate
    report["verification_summary"] = {
        "overall_assessment": "FAIL" if verification_failure else "PASS",
        "factual_accuracy_rate": factual_accuracy_rate,
        "claims_correct": correct_claims,
        "claims_incorrect": incorrect_claims,
        "claims_unverifiable": 0,
        "corrections_needed": [],
        "total_claims_checked": len(entries),
    }
    return report


def _mark_legacy_component_fixture(report: dict) -> dict:
    """Make the non-canonical boundary explicit in every returned legacy report."""
    report["disclaimer"] = (
        "SYNTHETIC COMPONENT-TEST FIXTURE: every organization, person, "
        "publication identifier, legal record, citation, and conclusion is "
        "fictional. This is not the canonical showcase and is not release "
        f"evidence. {report.get('disclaimer', '')}"
    ).strip()
    return report


def _raw_showcase_report() -> dict:
    """Adapt the canonical fixture into the live report schema for dev only."""
    fixture = load_showcase_fixture()
    receipt = showcase_fixture_receipt()
    payload = fixture["payload"]
    analysis = payload["analysis"]
    compound = payload["compound"]
    family = analysis["families"][0]
    claim = family["claims"][0]
    patent_id = showcase_publication_id()
    source_names = [source["label"] for source in analysis["searched_sources"]]

    report = _raw_aspirin_report()
    report.update(
        {
            "report_id": f"rpt_{analysis['id']}",
            "generated_at": analysis["completed_at"],
            "praviar_pipeline_version": f"showcase-fixture-{receipt['fixture_version']}",
            "compound": {
                "name": compound["display_name"],
                "canonical_smiles": "",
                "inchi": "",
                "inchi_key": "",
                "pubchem_cid": None,
                "synonyms": [compound["submitted_identity"]],
                "cas_numbers": [],
                "molecular_formula": "",
                "molecular_weight": None,
                "morgan_fp": "",
                "maccs_keys": "",
                "functional_groups": [],
                "related_compounds": [],
                "original_input": compound["submitted_identity"],
                "input_type": "name",
            },
            "risk_summary": {
                "overall_risk": "medium",
                "blocking_patents_count": 0,
                "total_patents_analyzed": 1,
                "key_risks": [
                    "The synthetic claim mapping requires qualified review.",
                    "One synthetic source intentionally models partial coverage.",
                ],
                "executive_summary": payload["disclaimer"],
                "summary_validation_issues": [
                    "Canonical fictional fixture; no live legal evidence."
                ],
            },
            "clearance_decision": _clearance_decision(
                "unclear",
                0.0,
                [patent_id],
                [],
            ),
            "decision_scope": {
                "matter_type": "small_molecule",
                "jurisdictions": ["US"],
                "asset_classes": ["fictional_placeholder"],
                "supports_positive_clearance": False,
                "summary": "The synthetic fixture cannot support positive clearance.",
            },
            "supporting_scope": {
                "matter_type": "small_molecule",
                "jurisdictions": ["US"],
                "asset_classes": ["fictional_placeholder"],
                "supports_positive_clearance": False,
                "summary": "Demonstration-only supporting scope.",
            },
            "certification_scope": {
                "certified_jurisdictions": [],
                "certified_matter_types": [],
                "certified_asset_classes": [],
                "attorney_supervised_matter_types": ["small_molecule"],
                "attorney_supervised_asset_classes": ["fictional_placeholder"],
                "supporting_only_jurisdictions": ["US"],
                "current_matter_type_certified": False,
                "attorney_supervision_required": True,
                "evidence_verified": False,
                "evidence_verification_status": "unverified",
                "evidence_failures": ["Synthetic fixture has no release certification."],
                "summary": payload["export"]["watermark"],
            },
            "cohort_status": "supporting_only",
            "routing_profile": {
                "mode": "canonical_fictional_showcase",
                "fixture_id": receipt["fixture_id"],
                "fixture_version": receipt["fixture_version"],
                "fixture_digest": receipt["fixture_digest"],
                "fixture_clock": payload["clock"],
            },
            "patent_analyses": [
                {
                    "patent_id": patent_id,
                    "jurisdiction": "US",
                    "title": family["title"],
                    "assignee": family["assignee"],
                    "expiry_date": None,
                    "claims_analyzed": [
                        {
                            "claim_number": int(claim["number"]),
                            "claim_type": "independent",
                            "depends_on": None,
                            "preamble": "A wholly fictional demonstration claim",
                            "transitional_phrase": "comprising",
                            "preamble_limiting": "unresolved",
                            "elements": [
                                {
                                    "element_number": 1,
                                    "element_text": claim["text"],
                                    "status": "unclear",
                                    "reasoning": claim["review_note"],
                                    "confidence": 0.0,
                                    "evidence": claim["review_note"],
                                    "uncertainty_note": claim["review_note"],
                                }
                            ],
                            "overall_status": "unclear",
                            "overall_confidence": 0.0,
                            "reasoning": claim["review_note"],
                            "uncertainty_note": claim["review_note"],
                        }
                    ],
                    "risk_level": "medium",
                    "risk_summary": (
                        "Synthetic candidate overlap; qualified human review is required."
                    ),
                    "design_around_suggestions": [],
                    "model_used": "deterministic-showcase-adapter-v1",
                    "thinking_text": "",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "analysis_review_required": True,
                }
            ],
            "verification": {
                "checks": [
                    {
                        "check_name": "canonical_fixture_digest",
                        "passed": True,
                        "severity": "pass",
                        "details": f"Payload bound to {receipt['fixture_digest']}.",
                    },
                    {
                        "check_name": "synthetic_source_boundary",
                        "passed": True,
                        "severity": "warning",
                        "details": "All evidence is explicitly synthetic.",
                    },
                    {
                        "check_name": "human_review_gate",
                        "passed": True,
                        "severity": "warning",
                        "details": payload["failure_states"][1]["message"],
                    },
                ],
                "all_citations_valid": True,
                "all_claims_grounded": True,
                "all_entities_valid": True,
                "dates_consistent": True,
                "risk_levels_justified": True,
                "issues": [],
            },
            "claim_construction_record": {
                "standard": "unresolved fictional demonstration",
                "jurisdictions": ["US"],
                "assumptions": [],
                "disputed_terms": [],
                "summary": claim["review_note"],
            },
            "commercial_exposure": {
                "damages_injunction_risk": "uncertain",
                "business_severity": "low",
                "blocking_patent_ids": [],
                "rationale": [payload["disclaimer"]],
                "summary": "No commercial conclusion is represented.",
            },
            "total_patents_found": len(analysis["families"]),
            "patents_after_triage": 1,
            "search_sources_used": source_names,
            "source_health": {
                "entries": [
                    {
                        "source": source["label"],
                        "status": "ok" if source["status"] == "complete" else "failed",
                        "patent_count": len(analysis["families"]),
                        "error_message": (
                            ""
                            if source["status"] == "complete"
                            else "Intentional partial synthetic coverage."
                        ),
                    }
                    for source in analysis["searched_sources"]
                ]
            },
            "analysis_failures": [],
            "data_limitations": [
                {
                    "category": "synthetic_showcase",
                    "description": limitation,
                    "impact": "No real legal or commercial decision is supported.",
                }
                for limitation in analysis["limitations"]
            ],
            "audit_trail": _search_funnel([patent_id], [patent_id], [patent_id]),
            "patent_narratives": {
                patent_id: "Synthetic candidate overlap; qualified review required."
            },
            "disclaimer": payload["disclaimer"],
            "llm_models_used": {"adapter": "deterministic-showcase-adapter-v1"},
            "action_items": [
                {
                    "action_type": "monitor",
                    "priority": "high",
                    "description": action,
                    "patent_ids": [patent_id],
                    "reasoning": payload["disclaimer"],
                    "estimated_timeline": "Before any external use",
                }
                for action in payload["review"]["required_actions"]
            ],
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "step_token_usage": [],
            "record_completeness": {
                "profile": "canonical_fictional_showcase",
                "matter_type": "small_molecule",
                "jurisdictions": ["US"],
                "required_components": [
                    "claims_text",
                    "claim_level_analysis",
                    "authoritative_records",
                ],
                "missing_components": ["authoritative_records"],
                "blocking_gaps": [
                    "Synthetic showcase evidence cannot satisfy authoritative-record policy."
                ],
                "clearance_grade_ready": False,
            },
            "run_observability": {
                "authoritative_source_hit_rate": 0.0,
                "claims_text_coverage": 1.0,
                "family_context_coverage": 1.0,
                "us_file_wrapper_dossier_coverage": 0.0,
                "ep_register_coverage": 0.0,
                "failed_adapter_names": [analysis["searched_sources"][1]["label"]],
                "false_clear_risk_flags": [
                    "canonical_fixture_is_synthetic",
                    "authoritative_records_missing",
                ],
                "unresolved_contradictions": [],
            },
        }
    )
    report["matter_store"]["record_completeness"] = deepcopy(report["record_completeness"])
    report["matter_store"]["run_observability"] = deepcopy(report["run_observability"])
    report["audit_trail"]["timing_data"] = [
        {
            "step_name": step["id"],
            "started_at": analysis["started_at"],
            "completed_at": analysis["completed_at"],
            "duration_seconds": 0.0,
            "items_processed": step["evidence_count"],
            "items_output": step["evidence_count"],
        }
        for step in analysis["pipeline_steps"]
    ]
    report["audit_trail"].update(
        {
            "total_patents_discovered": len(analysis["families"]),
            "patents_after_hard_filter": len(analysis["families"]),
            "patents_after_ranking": len(analysis["families"]),
            "patents_after_triage": 1,
            "patents_analyzed": 1,
        }
    )
    for funnel_entry in report["audit_trail"].get("search_funnel") or []:
        funnel_entry["sources_found_in"] = source_names
    report["matter_graph"] = _matter_graph(compound["display_name"], [patent_id])
    report["matter_graph_summary"] = _matter_graph_summary(compound["display_name"], [patent_id])
    report["matter_store"]["matter_graph"] = deepcopy(report["matter_graph"])
    report["matter_store"]["matter_graph_summary"] = deepcopy(report["matter_graph_summary"])
    evidence_index = report["matter_evidence_index"]
    evidence_index.update(
        {
            "source_names": source_names,
            "authoritative_source_names": [],
            "supporting_source_names": source_names,
            "clearance_grade_ready_patent_ids": [],
            "incomplete_patent_ids": [patent_id],
            "clearance_grade_ready_family_ids": [],
            "incomplete_family_ids": [_demo_family_id(patent_id)],
            "patent_records": [],
            "family_records": [],
        }
    )
    report["matter_store"]["matter_evidence_index"] = deepcopy(evidence_index)
    report["evidence_artifacts"] = []
    report["evidence_adapter_results"] = []
    report["matter_store"]["evidence_artifacts"] = []
    report["matter_store"]["evidence_adapter_results"] = []
    coverage = report["clearance_decision"]["decision_audit"]["coverage_summary"]
    coverage.update(
        {
            "queried_source_names": source_names,
            "successful_source_names": [analysis["searched_sources"][0]["label"]],
            "failed_source_names": [analysis["searched_sources"][1]["label"]],
            "authoritative_source_names": [],
            "supporting_source_names": source_names,
            "reviewed_patent_ids": [patent_id],
            "reviewed_us_patent_ids": [patent_id],
            "reviewed_ep_patent_ids": [],
            "clearance_grade_ready_patent_ids": [],
            "incomplete_patent_ids": [patent_id],
            "clearance_grade_ready_family_ids": [],
            "incomplete_family_ids": [_demo_family_id(patent_id)],
            "verification_gaps": analysis["limitations"],
        }
    )
    return report


def showcase_report(*, generated_at: datetime | None = None) -> dict:
    """Return the canonical API showcase through the live freshness contract.

    The canonical fixture clock remains in the receipt. Claim provenance has a
    bounded freshness policy, so the API projection uses a deterministic UTC
    day boundary unless a test or caller supplies an execution time.
    """
    generated_at = generated_at or datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    report = _govern_demo_report(
        _raw_showcase_report(),
        downgrade_clearance=True,
        generated_at=generated_at,
    )
    report["claim_source_span_map"]["generated_from"] = showcase_fixture_receipt()["fixture_id"]
    return report


def succinic_acid_report() -> dict:
    return _mark_legacy_component_fixture(
        _govern_demo_report(
            _raw_succinic_acid_report(),
            verification_failure=True,
        )
    )


def sofosbuvir_report() -> dict:
    return _mark_legacy_component_fixture(_govern_demo_report(_raw_sofosbuvir_report()))


def aspirin_report() -> dict:
    # Synthetic dev evidence must never claim positive clearance without a
    # release-signed certification receipt.
    return _mark_legacy_component_fixture(
        _govern_demo_report(
            _raw_aspirin_report(),
            downgrade_clearance=True,
        )
    )
