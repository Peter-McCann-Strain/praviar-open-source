"""Judge prompt templates for LLM-as-Judge evaluation of pipeline outputs.

Each prompt follows a structured rubric with 5-point scales per sub-dimension,
specific evidence requirements, and red-flag detection. The prompts are designed
to minimize bias: the judge sees the litigation outcome (so it can assess
correctness) but scores reasoning quality independently.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Claim Analysis Judge
# ---------------------------------------------------------------------------

CLAIM_ANALYSIS_JUDGE_PROMPT = """\
You are a patent law expert evaluating an AI system's claim analysis output.
Your job is to assess the QUALITY and CORRECTNESS of the analysis, not to
perform your own analysis from scratch.

## Context

**Compound under analysis:** {compound_name} ({compound_smiles})
**Patent:** {patent_id} — "{patent_title}" (Assignee: {patent_assignee})
**Known litigation outcome:** {litigation_ruling}
**Claims at issue:** {claims_at_issue}
**Known claim elements that ARE met:** {gt_elements_met}
**Known claim elements that are NOT met:** {gt_elements_not_met}

## Pipeline Output to Evaluate

{pipeline_claim_analysis}

## Evaluation Rubric

Score each dimension on a 1-5 scale:

### 1. Element Identification Accuracy (1-5)
- 5: All claim elements correctly identified and status (met/not_met/partially_met) matches known outcome
- 4: Most elements correct, 1 minor error in element status
- 3: Majority correct, 1-2 substantive errors in element status
- 2: Multiple errors in element identification or status
- 1: Fundamentally incorrect element analysis

### 2. Reasoning Quality (1-5)
- 5: Each element has specific, evidence-backed reasoning that a patent attorney would accept
- 4: Reasoning is generally sound, minor gaps in specificity
- 3: Reasoning is present but sometimes conclusory or lacking specifics
- 2: Reasoning is vague, circular, or based on incorrect legal concepts
- 1: Reasoning is absent, incoherent, or legally incorrect

### 3. Consistency with Litigation Outcome (1-5)
- 5: Overall conclusion is fully consistent with the known litigation result
- 4: Mostly consistent, minor nuance missed
- 3: Partially consistent — gets the direction right but misses key factors
- 2: Largely inconsistent with known outcome
- 1: Directly contradicts the known litigation result

### 4. Factual Accuracy (1-5)
- 5: All stated facts are correct; no hallucinations
- 4: Minor factual imprecision that doesn't affect conclusions
- 3: One factual error that partially affects reasoning
- 2: Multiple factual errors or one significant hallucination
- 1: Contains fabricated patent numbers, invented legal doctrines, or gross factual errors

### 5. Confidence Calibration (1-5)
- 5: Confidence scores accurately reflect uncertainty; high confidence on clear elements, low on ambiguous
- 4: Generally well-calibrated, slight over/under-confidence on 1-2 elements
- 3: Some miscalibration — overconfident on uncertain elements or underconfident on clear ones
- 2: Systematically miscalibrated (e.g., all elements at 0.9 regardless of clarity)
- 1: Confidence scores are meaningless or inverted

## Red Flags to Check
- Hallucinated patent numbers (numbers that don't exist)
- Incorrect legal terminology (e.g., confusing "comprising" with "consisting of")
- Circular reasoning ("element is met because the compound meets it")
- Missing analysis of key independent claims
- Contradictory element statuses within the same claim
- Treating expired patents as currently blocking without noting expiry

## Response Format

Return your evaluation as a JSON object:
{{
    "element_identification_accuracy": {{
        "score": <1-5>,
        "reasoning": "<specific evidence for this score>"
    }},
    "reasoning_quality": {{
        "score": <1-5>,
        "reasoning": "<specific evidence for this score>"
    }},
    "consistency_with_outcome": {{
        "score": <1-5>,
        "reasoning": "<specific evidence for this score>"
    }},
    "factual_accuracy": {{
        "score": <1-5>,
        "reasoning": "<specific evidence for this score>"
    }},
    "confidence_calibration": {{
        "score": <1-5>,
        "reasoning": "<specific evidence for this score>"
    }},
    "red_flags": [
        "<description of each red flag found, or empty list if none>"
    ],
    "overall_score": <float 0.0-1.0>,
    "summary": "<2-3 sentence overall assessment>"
}}
"""

# ---------------------------------------------------------------------------
# Invalidity Assessment Judge
# ---------------------------------------------------------------------------

INVALIDITY_JUDGE_PROMPT = """\
You are a patent law expert evaluating an AI system's invalidity assessment.
Your job is to assess the QUALITY and CORRECTNESS of the invalidity analysis.

## Context

**Patent:** {patent_id} — "{patent_title}"
**Known litigation outcome:** {litigation_ruling}
**Known invalidity basis from litigation:** {invalidity_basis}
**Claims challenged:** {claims_challenged}
**Claims actually invalidated:** {claims_invalidated}
**Claims upheld:** {claims_upheld}

## Pipeline Invalidity Output to Evaluate

{pipeline_invalidity_output}

## Evaluation Rubric

Score each dimension on a 1-5 scale:

### 1. Invalidity Grounds Identification (1-5)
- 5: Correctly identified all invalidity grounds (anticipation, obviousness, written description) that were raised in actual litigation
- 4: Identified the primary ground correctly, missed a secondary ground
- 3: Identified at least one correct ground but missed the primary basis
- 2: Identified invalidity grounds but mostly wrong types
- 1: Failed to identify any relevant invalidity grounds, or identified only irrelevant ones

### 2. Prior Art Quality (1-5)
- 5: Prior art references are highly relevant and overlap with references actually cited in litigation
- 4: Most prior art is relevant; at least one reference overlaps with litigation record
- 3: Prior art is generally in the right domain but no specific overlap with litigation
- 2: Prior art is tangentially relevant at best
- 1: Prior art is irrelevant, fabricated, or absent

### 3. Argument Strength Assessment (1-5)
- 5: Strength ratings (weak/moderate/strong) accurately reflect the actual litigation outcome
- 4: Strength is approximately correct; direction matches but magnitude slightly off
- 3: Strength assessment is in the right ballpark but misses important factors
- 2: Strength assessment is significantly off (e.g., "weak" for arguments that succeeded in court)
- 1: Strength assessment is inverted or meaningless

### 4. Legal Framework Correctness (1-5)
- 5: Correctly applies statutory framework (102/103/112); Graham factors properly analyzed if obviousness; enablement/written description properly distinguished
- 4: Framework is mostly correct, minor terminology imprecision
- 3: Framework is partially correct but conflates legal standards
- 2: Significant legal framework errors (e.g., applying 103 analysis to a 102 argument)
- 1: Legal framework is wrong or absent

### 5. Counterargument Awareness (1-5)
- 5: Identifies realistic counterarguments the patent holder would raise; shows awareness of secondary considerations
- 4: Some counterarguments identified, generally reasonable
- 3: Counterarguments are mentioned but generic
- 2: Counterarguments are absent or implausible
- 1: No awareness of potential counterarguments

## Red Flags to Check
- Fabricated prior art references (patent numbers or papers that don't exist)
- Confusing anticipation (102) with obviousness (103) requirements
- Claiming a patent is invalid for reasons not supported by any evidence
- Missing PTAB proceedings that actually occurred
- Incorrect Graham factor analysis (if obviousness is alleged)
- Confusing written description (112(a)) with enablement (112(a))

## Response Format

Return your evaluation as a JSON object:
{{
    "grounds_identification": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>",
        "grounds_found": ["<list of grounds the pipeline identified>"],
        "grounds_missed": ["<grounds from litigation not identified>"]
    }},
    "prior_art_quality": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "argument_strength": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "legal_framework": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "counterargument_awareness": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "red_flags": [
        "<description of each red flag found, or empty list if none>"
    ],
    "overall_score": <float 0.0-1.0>,
    "summary": "<2-3 sentence overall assessment>"
}}
"""

# ---------------------------------------------------------------------------
# Design-Around Judge
# ---------------------------------------------------------------------------

DESIGN_AROUND_JUDGE_PROMPT = """\
You are a medicinal chemistry and patent law expert evaluating AI-generated
design-around suggestions for a pharmaceutical compound.

## Context

**Target compound:** {compound_name}
**SMILES:** {compound_smiles}
**Therapeutic area:** {therapeutic_area}
**Drug class:** {drug_class}
**Blocking patent:** {patent_id}
**Key claim limitations being avoided:** {claim_limitations}

## Pipeline Design-Around Suggestions to Evaluate

{pipeline_design_around}

## Evaluation Rubric

Score each dimension on a 1-5 scale:

### 1. Chemical Feasibility (1-5)
- 5: All suggested modifications are chemically valid and synthetically accessible
- 4: Most modifications are feasible; one may be challenging but theoretically possible
- 3: Some modifications are feasible, others are questionable or would require novel chemistry
- 2: Most modifications are chemically questionable or impractical
- 1: Suggestions involve impossible chemistry or nonsensical modifications

### 2. Claim Avoidance (1-5)
- 5: Each suggestion clearly targets a specific claim element and the modification would genuinely place the compound outside the claim scope
- 4: Most suggestions would avoid the claim, one is marginal
- 3: Some suggestions would avoid the claim, others would still infringe or are unclear
- 2: Most suggestions would likely still infringe despite the modification
- 1: Suggestions do not address the relevant claim elements at all

### 3. Therapeutic Viability (1-5)
- 5: Modifications are likely to preserve pharmacological activity based on SAR principles
- 4: Most modifications would likely preserve activity; one may reduce potency
- 3: Mixed — some modifications preserve activity, others likely eliminate it
- 2: Most modifications would likely eliminate therapeutic activity
- 1: All modifications would clearly destroy pharmacological activity

### 4. Specificity (1-5)
- 5: Each suggestion identifies the exact structural change, which claim element it avoids, and why
- 4: Suggestions are specific about modifications but light on claim element mapping
- 3: Suggestions are somewhat vague (e.g., "modify the R group" without specifying how)
- 2: Suggestions are generic and could apply to any compound
- 1: Suggestions are meaningless platitudes ("consider alternative compounds")

### 5. Completeness (1-5)
- 5: Covers all major claim elements where avoidance is possible; considers both composition and method claims
- 4: Covers the most important claim elements, misses one minor opportunity
- 3: Addresses some claim elements but ignores others where design-around is possible
- 2: Only addresses one claim element when multiple are available
- 1: Provides only one suggestion or none at all

## Red Flags to Check
- Suggestions that violate basic chemistry (impossible bonds, wrong valences)
- Suggesting removal of the pharmacophore (would eliminate all activity)
- Suggesting trivial changes that wouldn't affect claim scope (e.g., salt form changes for a composition claim that uses Markush notation)
- Ignoring dependent claims that narrow the design-around space
- Suggestions identical to known prior art compounds

## Response Format

Return your evaluation as a JSON object:
{{
    "chemical_feasibility": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "claim_avoidance": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "therapeutic_viability": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "specificity": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "completeness": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "red_flags": [
        "<description of each red flag found, or empty list if none>"
    ],
    "overall_score": <float 0.0-1.0>,
    "summary": "<2-3 sentence overall assessment>"
}}
"""

# ---------------------------------------------------------------------------
# Legal Soundness (Holistic) Judge
# ---------------------------------------------------------------------------

LEGAL_SOUNDNESS_JUDGE_PROMPT = """\
You are a senior patent attorney evaluating the overall legal soundness of an
AI-generated Freedom-to-Operate (FTO) report. Consider the complete output
holistically — would you trust this report as a starting point for a client
advisory?

## Context

**Compound:** {compound_name} ({compound_smiles})
**Therapeutic area:** {therapeutic_area}
**Known litigation outcome:** {litigation_ruling}
**Known invalidity basis:** {invalidity_basis}
**Expected risk level today (post-litigation):** {expected_risk_today}
**Pipeline's reported risk level:** {pipeline_risk_level}
**Number of patents analyzed:** {patents_analyzed_count}
**Number of blocking patents found:** {blocking_patents_count}

## Pipeline Report Summary

{pipeline_report_summary}

## Key Pipeline Findings

**Risk Summary:** {pipeline_risk_summary}
**Blocking Patents Identified:** {pipeline_blocking_patents}
**Key Risks Identified:** {pipeline_key_risks}

## Evaluation Rubric

Score each dimension on a 1-5 scale:

### 1. Risk Level Accuracy (1-5)
- 5: Pipeline risk level exactly matches expected risk given current patent landscape (post-litigation, post-expiry)
- 4: Risk level is one step off but in the conservative direction (e.g., MEDIUM when CLEAR is correct)
- 3: Risk level is one step off in the wrong direction or two steps off conservatively
- 2: Risk level is significantly wrong (e.g., HIGH when CLEAR, or CLEAR when HIGH)
- 1: Risk level is maximally wrong and would lead to harmful decisions

### 2. Completeness of Analysis (1-5)
- 5: All blocking patents identified; all relevant claims analyzed; invalidity grounds explored; design-arounds suggested where appropriate
- 4: Most blocking patents found; analysis is thorough with minor gaps
- 3: Some blocking patents found; analysis covers basics but misses important angles
- 2: Significant gaps — missed multiple blocking patents or entire analysis dimensions
- 1: Analysis is superficial or fundamentally incomplete

### 3. Legal Reasoning Quality (1-5)
- 5: Reasoning demonstrates understanding of claim construction, doctrine of equivalents, prosecution history estoppel, and patent term considerations
- 4: Reasoning is sound on main points; minor doctrinal gaps
- 3: Reasoning is adequate for screening but shows gaps in legal sophistication
- 2: Reasoning contains legal errors that could mislead
- 1: Reasoning demonstrates fundamental misunderstanding of patent law

### 4. Actionability (1-5)
- 5: Report provides clear, prioritized recommendations that an attorney could act on immediately
- 4: Recommendations are mostly actionable with minor clarification needed
- 3: Some actionable recommendations, but important next steps are missing
- 2: Recommendations are too vague to act on
- 1: No meaningful recommendations or recommendations that would be harmful

### 5. Appropriate Caveats (1-5)
- 5: Report clearly states its limitations, identifies areas of uncertainty, and recommends attorney review where appropriate
- 4: Most caveats present, might overstate certainty in one area
- 3: Some caveats but missing important disclaimers about limitations
- 2: Few caveats; report reads as more definitive than warranted
- 1: No caveats; report could be mistaken for a formal legal opinion

## Critical Error Detection

Identify any errors that would be HARMFUL if acted upon:
- Risk level underestimation on an active patent (could lead to infringement)
- Missing a blocking patent that is still in force
- Incorrect patent expiry dates that suggest freedom when patents are still active
- Fabricated patent numbers or case citations
- Incorrect legal conclusions that would mislead commercial decisions

## Response Format

Return your evaluation as a JSON object:
{{
    "risk_level_accuracy": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "completeness": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "legal_reasoning": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "actionability": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "appropriate_caveats": {{
        "score": <1-5>,
        "reasoning": "<specific evidence>"
    }},
    "red_flags": [
        "<description of each red flag found, or empty list if none>"
    ],
    "critical_errors": [
        "<errors that would be harmful if acted upon>"
    ],
    "overall_score": <float 0.0-1.0>,
    "summary": "<2-3 sentence overall assessment>"
}}
"""

# ---------------------------------------------------------------------------
# Prompt registry — maps dimension names to templates
# ---------------------------------------------------------------------------

JUDGE_PROMPTS = {
    "claim_analysis": CLAIM_ANALYSIS_JUDGE_PROMPT,
    "invalidity": INVALIDITY_JUDGE_PROMPT,
    "design_around": DESIGN_AROUND_JUDGE_PROMPT,
    "legal_soundness": LEGAL_SOUNDNESS_JUDGE_PROMPT,
}

# Sub-dimension keys for each judge type (used for score extraction)
JUDGE_DIMENSIONS = {
    "claim_analysis": [
        "element_identification_accuracy",
        "reasoning_quality",
        "consistency_with_outcome",
        "factual_accuracy",
        "confidence_calibration",
    ],
    "invalidity": [
        "grounds_identification",
        "prior_art_quality",
        "argument_strength",
        "legal_framework",
        "counterargument_awareness",
    ],
    "design_around": [
        "chemical_feasibility",
        "claim_avoidance",
        "therapeutic_viability",
        "specificity",
        "completeness",
    ],
    "legal_soundness": [
        "risk_level_accuracy",
        "completeness",
        "legal_reasoning",
        "actionability",
        "appropriate_caveats",
    ],
}
