"""Claim-level analysis models."""

from __future__ import annotations

import enum
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from praviar_pipeline.models.analysis_validation import (
    coerce_enum_value,
    warn_missing_claim_evidence,
)


class ElementStatus(enum.StrEnum):
    """Whether the target compound meets a claim element."""

    MET = "met"
    NOT_MET = "not_met"
    PARTIALLY_MET = "partially_met"
    UNCLEAR = "unclear"


class RiskLevel(enum.StrEnum):
    """Overall FTO risk level for a patent."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    CLEAR = "clear"


class ClaimElement(BaseModel):
    """Element-by-element analysis of a single claim limitation."""

    model_config = ConfigDict(extra="ignore")

    element_number: int
    element_text: str = Field(description="The claim limitation text")
    status: ElementStatus
    reasoning: str = Field(description="Why this element is/isn't met")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str = Field(default="", description="Specific evidence supporting the assessment")
    uncertainty_note: str = Field(
        default="",
        description=(
            "Optional free-text note capturing genuine ambiguity in this element's "
            "assessment (e.g. an unresolved claim term or thin evidence). Empty when "
            "the assessment is unambiguous."
        ),
    )
    spec_citation: str = Field(
        default="",
        description=(
            "Optional specification reference (column/line or paragraph, e.g. "
            "'col. 5, lines 10-22' or 'para. 0042') for where a construed claim "
            "term is defined. Empty when no specification definition was relied on."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_element_fields(cls, data: Any) -> Any:
        """Normalize LLM field-name drift and null optional strings.

        Without a compiled grammar:
        - 'element_id' (e.g. '1.1') is mapped to 'element_number' (int)
        - null values for optional string fields are replaced with ""
        - null confidence is replaced with 0.0
        """
        if not isinstance(data, dict):
            return data
        if "element_id" in data and "element_number" not in data:
            raw = data.pop("element_id")
            m = re.match(r"(\d+)", str(raw).strip())
            data["element_number"] = int(m.group(1)) if m else 1
        for field in ("evidence", "uncertainty_note", "spec_citation", "reasoning"):
            if data.get(field) is None:
                data[field] = ""
        if data.get("confidence") is None:
            data["confidence"] = 0.0
        return data

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: str) -> str:
        """Normalise the element status from LLM output, failing loud on bad input.

        Common drift such as ``"Not Met"`` or ``"partially met"`` is normalised
        to the canonical underscore form. A value that is still unrecognised
        raises rather than silently becoming ``unclear``: element statuses drive
        the deterministic risk computation, so a silent default can collapse a
        blocking patent to CLEAR and drop it from invalidity assessment.
        """
        return coerce_enum_value(
            v,
            valid_values={e.value for e in ElementStatus},
            default=ElementStatus.UNCLEAR.value,
            log_event="element_status_coerced",
            replace_spaces=True,
            raise_on_unknown=True,
        )

    @model_validator(mode="after")
    def _check_evidence_present(self) -> ClaimElement:
        """Warn if status is decisive but evidence is empty."""
        warn_missing_claim_evidence(self.status, self.evidence)
        return self


class ClaimAnalysis(BaseModel):
    """Analysis of a single patent claim."""

    model_config = ConfigDict(extra="ignore")

    claim_number: int
    claim_type: Literal["independent", "dependent"] = Field(
        description="independent or dependent",
    )
    depends_on: int | None = Field(
        default=None,
        description="Parent claim number if dependent",
    )
    preamble: str = Field(default="", description="Claim preamble text")
    transitional_phrase: str | None = Field(
        default=None,
        description="comprising, consisting of, consisting essentially of",
    )
    preamble_limiting: Literal["limiting", "nonlimiting", "unresolved"] = Field(
        default="unresolved",
        description=(
            "Jurisdiction-specific construction of whether the preamble limits the "
            "claim. Unresolved must never support a positive clearance conclusion."
        ),
    )
    preamble_limitation_reasoning: str = Field(
        default="",
        description="Grounded reasoning for the preamble-limitation construction.",
    )
    preamble_limitation_evidence: str = Field(
        default="",
        description="Specification, prosecution, or controlling-law evidence.",
    )
    elements: list[ClaimElement] = Field(default_factory=list)
    reasoning: str = Field(default="", description="Overall reasoning for the claim analysis")
    overall_status: ElementStatus = Field(
        description="Overall: met only if ALL elements are met",
    )
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertainty_note: str = Field(
        default="",
        description=(
            "Optional free-text note capturing genuine claim-level ambiguity "
            "(e.g. an unresolved claim term that affects several elements). "
            "Empty when the claim assessment is unambiguous."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_claim_fields(cls, data: Any) -> Any:
        """Normalize null optional strings and non-int claim_number.

        Without compiled grammar, the model emits null for optional string
        fields and sometimes emits null or descriptive strings for claim_number.
        """
        if not isinstance(data, dict):
            return data
        for field in (
            "preamble",
            "preamble_limitation_reasoning",
            "preamble_limitation_evidence",
            "reasoning",
            "uncertainty_note",
        ):
            if data.get(field) is None:
                data[field] = ""
        if data.get("overall_confidence") is None:
            data["overall_confidence"] = 0.0
        return data

    @field_validator("claim_number", mode="before")
    @classmethod
    def _coerce_claim_number(cls, v: Any) -> Any:
        """Coerce string/null claim numbers from LLM output to int.

        Without compiled grammar, the model sometimes emits descriptive
        strings like '1 (inferred from abstract)' or null. Default to 1.
        """
        if v is None:
            return 1
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            m = re.match(r"(\d+)", v.strip())
            if m:
                return int(m.group(1))
        return v

    @field_validator("claim_type", mode="before")
    @classmethod
    def _coerce_claim_type(cls, v: str) -> str:
        """Normalise the claim dependency type from LLM output.

        When the model returns subject-matter terminology ('composition-of-matter',
        'method/process') instead of structural dependency ('independent',
        'dependent'), coerce to 'independent'. This is the FTO-conservative
        default: treating a claim as independent means it is always included in
        risk scoring, so no blocking claim is silently excluded. The alternative
        (raising) blocks the entire analysis when the model drifts without a
        compiled-grammar constraint.
        """
        return coerce_enum_value(
            v,
            valid_values={"independent", "dependent"},
            default="independent",
            log_event="claim_type_coerced",
            raise_on_unknown=False,
        )

    @field_validator("overall_status", mode="before")
    @classmethod
    def _coerce_overall_status(cls, v: str) -> str:
        """Normalise the overall claim status from LLM output, failing loud on bad input.

        See :meth:`ClaimElement._coerce_status` for why an unrecognised status
        raises rather than silently coercing to ``unclear``.
        """
        return coerce_enum_value(
            v,
            valid_values={e.value for e in ElementStatus},
            default=ElementStatus.UNCLEAR.value,
            log_event="overall_status_coerced",
            replace_spaces=True,
            raise_on_unknown=True,
        )

    @model_validator(mode="after")
    def _validate_all_limitations_status(self) -> ClaimAnalysis:
        """Reject a claim-level result that contradicts its limitation rows."""
        if not self.elements:
            return self
        if self.preamble:
            element_zero = [element for element in self.elements if element.element_number == 0]
            if len(element_zero) > 1:
                raise ValueError("a claim cannot contain duplicate Element 0 rows")
            if (
                element_zero
                and self.preamble_limiting != "unresolved"
                and (
                    not self.preamble_limitation_reasoning.strip()
                    or not self.preamble_limitation_evidence.strip()
                )
            ):
                raise ValueError("resolved preamble construction requires reasoning and evidence")
        body_elements = [element for element in self.elements if element.element_number != 0]
        effective_elements = (
            self.elements
            if (self.preamble and element_zero and self.preamble_limiting == "limiting")
            else body_elements
        )
        statuses = {element.status for element in effective_elements}
        if self.preamble and element_zero and self.preamble_limiting == "unresolved":
            statuses.add(ElementStatus.UNCLEAR)
        if ElementStatus.NOT_MET in statuses:
            expected = ElementStatus.NOT_MET
        elif ElementStatus.UNCLEAR in statuses:
            expected = ElementStatus.UNCLEAR
        elif ElementStatus.PARTIALLY_MET in statuses:
            expected = ElementStatus.PARTIALLY_MET
        else:
            expected = ElementStatus.MET
        if self.overall_status != expected:
            raise ValueError("claim overall_status contradicts the all-limitations element record")
        return self


class DesignAroundSuggestion(BaseModel):
    """A suggested modification to avoid infringement."""

    model_config = ConfigDict(extra="forbid")

    element_avoided: int = Field(ge=1, description="Which claim element this avoids")
    suggestion: str

    feasibility: str = Field(
        default="",
        description="Assessment of whether this modification is chemically viable",
    )

    # Structured validation fields — populated by design_around_validation.validate_design_around
    # when the suggestion includes a proposed SMILES string. Left as None when no SMILES is given.
    smiles: str | None = Field(
        default=None,
        description="Proposed modified structure as a SMILES string",
    )
    tanimoto_to_original: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Tanimoto similarity (Morgan fingerprints, r=2) to the original compound",
    )
    rdkit_valid: bool | None = Field(
        default=None,
        description="Whether RDKit successfully parsed the proposed SMILES",
    )
    pharmacophore_preserved: bool | None = Field(
        default=None,
        description=(
            "Heuristic flag: True when Tanimoto is in a defensible mid-range band "
            "suggesting structural similarity without identity (see design_around_validation)"
        ),
    )
