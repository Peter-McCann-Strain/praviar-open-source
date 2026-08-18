"""Build the exact post-resolution identity packet reviewed before search."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from praviar_pipeline.models.identity_review import (
    IdentityComparison,
    IdentityDerivationEvidence,
    IdentityReviewContext,
    IdentitySearchLane,
    IdentitySource,
    IdentityVariant,
    IdentityVariantAssessment,
    IdentityVariantStatus,
    ResolvedIdentityRecord,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound


def build_identity_review_context(
    compound: ResolvedCompound,
    *,
    settings: Any,
    run_id: str,
) -> dict[str, Any]:
    """Return a fingerprint-bound, UI-safe identity approval packet."""
    product_context = getattr(settings, "product_context", {}) or {}
    product_form = str(product_context.get("salt_polymorph_form", "") or "").strip()
    resolved_identity = _resolved_identity_record(compound)
    comparison = _compare_submitted_to_resolved(compound)
    search_envelope = _build_search_envelope(compound, settings=settings)
    variants = _build_variant_assessments(
        compound,
        product_form=product_form,
    )
    enabled_sources = sorted(
        {source for lane in search_envelope if lane.enabled for source in lane.sources}
    )
    derivation_evidence = IdentityDerivationEvidence(
        tautomer_enumeration=compound.tautomer_enumeration,
        prodrug_candidates=compound.prodrug_candidates,
        unsupported_prodrug_motifs=compound.unsupported_prodrug_motifs,
    )
    fingerprint_payload = {
        "original_input": compound.original_input,
        "input_type": compound.input_type,
        "resolved_identity": resolved_identity.model_dump(mode="json"),
        "search_envelope": [lane.model_dump(mode="json") for lane in search_envelope],
        "variant_assessments": [variant.model_dump(mode="json") for variant in variants],
        "derivation_evidence": derivation_evidence.model_dump(mode="json"),
        "product_form_declaration": product_form,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    checkpoint_id = f"{run_id}:identity_review:{fingerprint}"

    context = IdentityReviewContext(
        checkpoint_id=checkpoint_id,
        identity_fingerprint=fingerprint,
        original_input=compound.original_input,
        input_type=compound.input_type,
        comparison=comparison,
        resolved_identity=resolved_identity,
        search_envelope=search_envelope,
        variant_assessments=variants,
        derivation_evidence=derivation_evidence,
        enabled_search_sources=enabled_sources,
        product_form_declaration=product_form,
        approval_attestation=(
            "I verified the resolved identity against the submitted compound, reviewed "
            "the declared product form and every fingerprint-bound derived search form, "
            "and accept the bounded tautomer set and explicitly hypothetical prodrug-parent "
            "candidates, provenance, integrity checks, and unsupported limitations."
        ),
    )
    return context.model_dump(mode="json")


def _resolved_identity_record(compound: ResolvedCompound) -> ResolvedIdentityRecord:
    has_pubchem = compound.pubchem_cid is not None
    has_purple_book = bool(compound.bla_number)
    has_gsrs = bool(
        compound.unii
        and compound.gsrs_uuid
        and compound.gsrs_substance_class == "protein"
        and compound.gsrs_definition_type == "PRIMARY"
        and compound.gsrs_definition_level == "COMPLETE"
    )
    identity_source: IdentitySource
    if has_pubchem and has_purple_book:
        identity_source = "pubchem_and_fda_purple_book"
        source_authority = "PubChem and FDA Purple Book"
        source_record_id = f"PubChem CID {compound.pubchem_cid}; BLA {compound.bla_number}"
    elif has_purple_book:
        identity_source = "fda_purple_book"
        source_authority = "FDA Purple Book"
        source_record_id = f"BLA {compound.bla_number}"
    elif has_pubchem and has_gsrs:
        identity_source = "pubchem_and_fda_gsrs"
        source_authority = "PubChem and FDA GSRS"
        source_record_id = (
            f"PubChem CID {compound.pubchem_cid}; UNII {compound.unii}; "
            f"GSRS UUID {compound.gsrs_uuid}"
        )
    elif has_gsrs:
        identity_source = "fda_gsrs"
        source_authority = "FDA GSRS (substance identity; not approval status)"
        source_record_id = f"UNII {compound.unii}; GSRS UUID {compound.gsrs_uuid}"
    elif has_pubchem:
        identity_source = "pubchem"
        source_authority = "PubChem"
        source_record_id = f"CID {compound.pubchem_cid}"
    else:
        raise ValueError(
            "Identity review requires an authoritative PubChem, FDA Purple Book, "
            "or primary/complete FDA GSRS record"
        )

    return ResolvedIdentityRecord(
        name=compound.name,
        compound_type=compound.compound_type,
        identity_source=identity_source,
        source_authority=source_authority,
        source_record_id=source_record_id,
        canonical_smiles=compound.canonical_smiles,
        inchi=compound.inchi,
        inchi_key=compound.inchi_key,
        molecular_formula=compound.molecular_formula,
        molecular_weight=compound.molecular_weight,
        cas_numbers=compound.cas_numbers[:20],
        bla_number=compound.bla_number,
        reference_product=compound.reference_product,
        unii=compound.unii,
        gsrs_uuid=compound.gsrs_uuid,
        gsrs_substance_class=compound.gsrs_substance_class,
        gsrs_definition_type=compound.gsrs_definition_type,
        gsrs_definition_level=compound.gsrs_definition_level,
        gsrs_record_version=compound.gsrs_record_version,
        gsrs_names_last_updated=compound.gsrs_names_last_updated,
        gsrs_record_last_updated=compound.gsrs_record_last_updated,
        authoritative_record_present=bool(
            has_purple_book
            or has_gsrs
            or (
                has_pubchem
                and (
                    compound.inchi_key
                    or compound.canonical_smiles
                    or compound.compound_type != "small_molecule"
                )
            )
        ),
    )


def _compare_submitted_to_resolved(compound: ResolvedCompound) -> IdentityComparison:
    submitted = compound.original_input.strip()
    input_type = compound.input_type

    if input_type == "smiles":
        submitted_canonical = _canonicalize_smiles(submitted)
        resolved_canonical = _canonicalize_smiles(compound.canonical_smiles)
        if submitted == compound.canonical_smiles:
            return IdentityComparison(
                outcome="exact_match",
                submitted_value=submitted,
                resolved_value=compound.canonical_smiles,
                detail="The submitted SMILES exactly matches the resolved canonical SMILES.",
            )
        if submitted_canonical and submitted_canonical == resolved_canonical:
            return IdentityComparison(
                outcome="normalized_match",
                submitted_value=submitted,
                resolved_value=compound.canonical_smiles,
                detail=(
                    "The notation changed during canonicalization, but RDKit resolves both "
                    "strings to the same isomeric molecular graph."
                ),
            )
        return IdentityComparison(
            outcome="different",
            submitted_value=submitted,
            resolved_value=compound.canonical_smiles,
            detail=(
                "The submitted and resolved structures are not graph-equivalent under the "
                "available canonicalization check. Reject unless this difference is intended."
            ),
            requires_attention=True,
        )

    if input_type == "inchi":
        exact = submitted == compound.inchi
        return IdentityComparison(
            outcome="exact_match" if exact else "different",
            submitted_value=submitted,
            resolved_value=compound.inchi,
            detail=(
                "The submitted InChI exactly matches the resolved record."
                if exact
                else "The resolved InChI differs from the submitted InChI."
            ),
            requires_attention=not exact,
        )

    if input_type == "inchikey":
        exact = submitted.upper() == compound.inchi_key.upper()
        return IdentityComparison(
            outcome="normalized_match" if exact else "different",
            submitted_value=submitted,
            resolved_value=compound.inchi_key,
            detail=(
                "The submitted InChIKey matches the resolved record after case normalization."
                if exact
                else "The resolved InChIKey differs from the submitted InChIKey."
            ),
            requires_attention=not exact,
        )

    if input_type == "cas":
        normalized = _normalize_cas(submitted)
        exact = normalized in compound.cas_numbers
        return IdentityComparison(
            outcome="normalized_match" if exact else "resolved_from_identifier",
            submitted_value=submitted,
            resolved_value=", ".join(compound.cas_numbers[:5]) or compound.name,
            detail=(
                "The submitted CAS Registry Number appears in the resolved synonym record."
                if exact
                else (
                    "The source resolved this registry-number query, but the submitted number "
                    "is not present in the returned CAS synonym set. Verify the source record."
                )
            ),
            requires_attention=not exact,
        )

    names = {
        value.strip().casefold() for value in [compound.name, *compound.synonyms] if value.strip()
    }
    if submitted.casefold() in names:
        return IdentityComparison(
            outcome="normalized_match",
            submitted_value=submitted,
            resolved_value=compound.name,
            detail="The submitted name appears in the resolved name or synonym record.",
        )
    return IdentityComparison(
        outcome="resolved_from_identifier",
        submitted_value=submitted,
        resolved_value=compound.name,
        detail=(
            "The identity source resolved the submitted name to this record, but the exact "
            "submitted name is not in the retained synonym set. Confirm the intended asset."
        ),
        requires_attention=True,
    )


def _build_search_envelope(
    compound: ResolvedCompound,
    *,
    settings: Any,
) -> list[IdentitySearchLane]:
    pubchem_enabled = bool(getattr(settings, "search_enable_pubchem", False))
    bigquery_enabled = bool(getattr(settings, "search_enable_bigquery", False))
    surechembl_enabled = bool(getattr(settings, "search_enable_surechembl", False))
    patcid_enabled = bool(getattr(settings, "search_enable_patcid", False))

    lanes: list[IdentitySearchLane] = []
    _append_lane(
        lanes,
        lane_id="resolved_names",
        label="Resolved name and synonyms",
        values=_dedupe([compound.name, *compound.synonyms])[:20],
        total_value_count=len(_dedupe([compound.name, *compound.synonyms])),
        sources=["BigQuery Patents"],
        enabled=bigquery_enabled,
        purpose="Lexical compound-name retrieval in patent text.",
    )
    _append_lane(
        lanes,
        lane_id="cas_numbers",
        label="CAS registry numbers",
        values=compound.cas_numbers[:20],
        total_value_count=len(compound.cas_numbers),
        sources=["BigQuery Patents"],
        enabled=bigquery_enabled,
        purpose="Exact registry-number retrieval in patent text.",
    )
    _append_lane(
        lanes,
        lane_id="pubchem_cid",
        label="PubChem compound record",
        values=[str(compound.pubchem_cid)] if compound.pubchem_cid is not None else [],
        total_value_count=1 if compound.pubchem_cid is not None else 0,
        sources=["PubChem"],
        enabled=pubchem_enabled,
        purpose="Direct PubChem compound-to-patent links and similarity expansion.",
    )
    inchi_sources = [
        source
        for source, enabled in (
            ("PatCID", patcid_enabled),
            ("BigQuery chemical annotations", bigquery_enabled),
        )
        if enabled
    ]
    _append_lane(
        lanes,
        lane_id="inchikey",
        label="InChIKey",
        values=[compound.inchi_key] if compound.inchi_key else [],
        total_value_count=1 if compound.inchi_key else 0,
        sources=inchi_sources or ["PatCID", "BigQuery chemical annotations"],
        enabled=bool(compound.inchi_key and (patcid_enabled or bigquery_enabled)),
        purpose=("Exact structure-key lookup plus connectivity-block expansion where supported."),
    )
    _append_lane(
        lanes,
        lane_id="canonical_structure",
        label="Canonical structure",
        values=[compound.canonical_smiles] if compound.canonical_smiles else [],
        total_value_count=1 if compound.canonical_smiles else 0,
        sources=["SureChEMBL", "PubChem"],
        enabled=bool(compound.canonical_smiles and (surechembl_enabled or pubchem_enabled)),
        purpose="Exact and similarity structure retrieval.",
    )
    _append_lane(
        lanes,
        lane_id="free_base_structure",
        label="Salt-stripped / largest-fragment structure",
        values=[compound.free_base_smiles] if compound.free_base_smiles else [],
        total_value_count=1 if compound.free_base_smiles else 0,
        sources=["SureChEMBL"],
        enabled=bool(compound.free_base_smiles and surechembl_enabled),
        derived=True,
        differs_from_canonical=bool(
            compound.free_base_smiles and compound.free_base_smiles != compound.canonical_smiles
        ),
        purpose="Broaden exact structure retrieval beyond a submitted salt or counter-ion.",
    )
    _append_lane(
        lanes,
        lane_id="stereo_stripped_structure",
        label="Stereo-stripped structure",
        values=[compound.stereo_stripped_smiles] if compound.stereo_stripped_smiles else [],
        total_value_count=1 if compound.stereo_stripped_smiles else 0,
        sources=["SureChEMBL"],
        enabled=bool(compound.stereo_stripped_smiles and surechembl_enabled),
        derived=True,
        differs_from_canonical=bool(
            compound.stereo_stripped_smiles
            and compound.stereo_stripped_smiles != compound.canonical_smiles
        ),
        purpose="Broaden retrieval to racemate or stereoisomer claim scope.",
    )
    _append_lane(
        lanes,
        lane_id="murcko_scaffold",
        label="Murcko scaffold",
        values=[compound.scaffold_smiles] if compound.scaffold_smiles else [],
        total_value_count=1 if compound.scaffold_smiles else 0,
        sources=["SureChEMBL"],
        enabled=bool(compound.scaffold_smiles and surechembl_enabled),
        derived=True,
        differs_from_canonical=bool(
            compound.scaffold_smiles and compound.scaffold_smiles != compound.canonical_smiles
        ),
        purpose="Broaden structure retrieval toward core-scaffold genus claims.",
    )
    tautomer_candidates = (
        [
            candidate
            for candidate in compound.tautomer_enumeration.candidates
            if candidate.search_eligible and candidate.integrity.passed
        ]
        if compound.tautomer_enumeration is not None
        and compound.tautomer_enumeration.search_expansion_allowed
        else []
    )
    _append_lane(
        lanes,
        lane_id="validated_tautomer_structures",
        label="Bounded, property-validated tautomers",
        values=[candidate.canonical_smiles for candidate in tautomer_candidates],
        total_value_count=len(tautomer_candidates),
        sources=["SureChEMBL"],
        enabled=bool(tautomer_candidates and surechembl_enabled),
        derived=True,
        differs_from_canonical=True,
        purpose=(
            "Exact retrieval for the completed RDKit tautomer set; candidate IDs, engine "
            "version, bounds, invariants, and limitations are fingerprinted in this review."
        ),
    )
    prodrug_candidates = [
        candidate
        for candidate in compound.prodrug_candidates
        if candidate.search_eligible and candidate.integrity.passed
    ]
    _append_lane(
        lanes,
        lane_id="prodrug_parent_hypotheses",
        label="Reviewer-approved prodrug-parent hypotheses",
        values=[candidate.canonical_smiles for candidate in prodrug_candidates],
        total_value_count=len(prodrug_candidates),
        sources=["SureChEMBL"],
        enabled=bool(prodrug_candidates and surechembl_enabled),
        derived=True,
        differs_from_canonical=True,
        purpose=(
            "Additional exact searches for bounded hydrolysis/deprotection hypotheses. "
            "These structures never replace or redefine the resolved compound identity."
        ),
    )
    if compound.bla_number:
        _append_lane(
            lanes,
            lane_id="purple_book_bla",
            label="Purple Book BLA",
            values=[compound.bla_number],
            total_value_count=1,
            sources=["FDA Purple Book"],
            enabled=True,
            purpose="Bind the biologic identity to its authoritative FDA product record.",
        )
    if compound.unii and compound.gsrs_uuid:
        _append_lane(
            lanes,
            lane_id="fda_gsrs_identity",
            label="FDA GSRS substance identity",
            values=[compound.unii, compound.gsrs_uuid],
            total_value_count=2,
            sources=["FDA GSRS via openFDA"],
            enabled=True,
            purpose=(
                "Bind the exact biologic name to one primary, complete FDA GSRS protein "
                "record. A UNII identifies a substance and does not establish FDA approval."
            ),
        )
    return lanes


def _build_variant_assessments(
    compound: ResolvedCompound,
    *,
    product_form: str,
) -> list[IdentityVariantAssessment]:
    if compound.compound_type != "small_molecule":
        biologic_variants: list[tuple[IdentityVariant, str]] = [
            ("salt_or_product_form", "Salt / product form"),
            ("stereochemistry", "Stereochemistry"),
            ("tautomer", "Tautomers"),
            ("prodrug", "Prodrug / active form"),
        ]
        return [
            IdentityVariantAssessment(
                variant=variant,
                label=label,
                status="not_applicable",
                search_effect="No small-molecule structure transform is applied.",
                limitation=(
                    "Sequence, glycoform, conjugate, and product-variant scope requires "
                    "separate biologic evidence and is not represented by these fields."
                ),
                requires_attention=True,
            )
            for variant, label in biologic_variants
        ]

    salt_differs = bool(
        compound.free_base_smiles and compound.free_base_smiles != compound.canonical_smiles
    )
    salt_status: IdentityVariantStatus = (
        "declared"
        if product_form
        else "derived_search_form"
        if salt_differs
        else "no_distinct_form"
    )
    salt_limitation = (
        "The declared product form is user-supplied context; the resolver does not "
        "independently verify polymorph, hydrate, solvate, or crystal-form identity."
        if product_form
        else (
            "A counter-ion or smaller fragment was removed for an additional search lane; "
            "this does not establish the marketed product form."
            if salt_differs
            else (
                "No distinct salt transform was derived. This does not prove that salt, "
                "hydrate, solvate, polymorph, or crystal-form scope is irrelevant."
            )
        )
    )

    stereo_differs = bool(
        compound.stereo_stripped_smiles
        and compound.stereo_stripped_smiles != compound.canonical_smiles
    )
    prodrug_detected = bool(compound.prodrug_pattern)
    tautomer_record = compound.tautomer_enumeration
    eligible_tautomers = (
        [
            candidate
            for candidate in tautomer_record.candidates
            if candidate.search_eligible and candidate.integrity.passed
        ]
        if tautomer_record is not None and tautomer_record.search_expansion_allowed
        else []
    )
    eligible_prodrug_candidates = [
        candidate
        for candidate in compound.prodrug_candidates
        if candidate.search_eligible and candidate.integrity.passed
    ]
    if eligible_tautomers:
        tautomer_status: IdentityVariantStatus = "derived_search_form"
        tautomer_search_effect = (
            f"{len(eligible_tautomers)} bounded, property-invariant tautomer structure(s) "
            "are included as additional exact-search lanes."
        )
    elif tautomer_record is not None and tautomer_record.status == "completed":
        tautomer_status = "no_distinct_form"
        tautomer_search_effect = (
            "RDKit enumeration completed within bounds but produced no distinct, eligible "
            "tautomer search representation."
        )
    elif tautomer_record is not None:
        tautomer_status = "unavailable"
        tautomer_search_effect = (
            f"Tautomer enumeration status is {tautomer_record.status}; no alternate "
            "tautomer is allowed to expand search."
        )
    else:
        tautomer_status = "not_modeled"
        tautomer_search_effect = "No tautomer-enumeration receipt is available."

    if eligible_prodrug_candidates:
        prodrug_status: IdentityVariantStatus = "derived_search_form"
        prodrug_search_effect = (
            f"{len(eligible_prodrug_candidates)} parent structure hypothesis/hypotheses "
            "are included as additional exact-search lanes."
        )
    elif prodrug_detected:
        prodrug_status = "candidate_detected"
        prodrug_search_effect = (
            "A candidate motif was detected, but no structure passed the conservative "
            "dominant-parent and integrity gates; no active-form lane is added."
        )
    else:
        prodrug_status = "not_detected"
        prodrug_search_effect = (
            "No supported simple prodrug motif was detected; no parent-hypothesis lane is added."
        )

    return [
        IdentityVariantAssessment(
            variant="salt_or_product_form",
            label="Salt / product form",
            status=salt_status,
            declared_value=product_form,
            derived_value=compound.free_base_smiles,
            search_effect=(
                "The salt-stripped largest fragment is included as a distinct structure lane."
                if salt_differs
                else "No distinct salt-stripped structure lane is produced."
            ),
            limitation=salt_limitation,
            requires_attention=not bool(product_form),
        ),
        IdentityVariantAssessment(
            variant="stereochemistry",
            label="Stereochemistry",
            status="derived_search_form" if stereo_differs else "no_distinct_form",
            derived_value=compound.stereo_stripped_smiles,
            search_effect=(
                "A stereo-stripped structure is included as a distinct search lane."
                if stereo_differs
                else "Stereo stripping did not produce a distinct search representation."
            ),
            limitation=(
                "Stereo stripping broadens retrieval but does not enumerate or validate "
                "individual stereoisomers, racemates, epimers, or mixtures."
            ),
            requires_attention=stereo_differs,
        ),
        IdentityVariantAssessment(
            variant="tautomer",
            label="Tautomers",
            status=tautomer_status,
            derived_value=", ".join(candidate.canonical_smiles for candidate in eligible_tautomers),
            search_effect=tautomer_search_effect,
            limitation=(
                tautomer_record.limitation
                if tautomer_record is not None
                else (
                    "Canonical SMILES must not be treated as proof of tautomer coverage. "
                    "Reject this identity if tautomer search is decision-critical."
                )
            ),
            requires_attention=bool(
                eligible_tautomers
                or tautomer_record is None
                or tautomer_record.status != "completed"
            ),
        ),
        IdentityVariantAssessment(
            variant="prodrug",
            label="Prodrug / active form",
            status=prodrug_status,
            derived_value=", ".join(
                candidate.canonical_smiles for candidate in eligible_prodrug_candidates
            ),
            search_effect=prodrug_search_effect,
            limitation=(
                "Every generated structure is a reviewer-approved hypothesis, never an "
                "identity substitution. Unsupported motifs: "
                + (
                    "; ".join(compound.unsupported_prodrug_motifs)
                    if compound.unsupported_prodrug_motifs
                    else "none detected"
                )
                + ". Motif absence does not rule out metabolic activation."
            ),
            requires_attention=bool(
                prodrug_detected
                or eligible_prodrug_candidates
                or compound.unsupported_prodrug_motifs
            ),
        ),
    ]


def _append_lane(
    lanes: list[IdentitySearchLane],
    *,
    lane_id: str,
    label: str,
    values: list[str],
    total_value_count: int,
    sources: list[str],
    enabled: bool,
    purpose: str,
    derived: bool = False,
    differs_from_canonical: bool = False,
) -> None:
    if not values:
        return
    lanes.append(
        IdentitySearchLane(
            lane_id=lane_id,
            label=label,
            values=values,
            total_value_count=total_value_count,
            sources=sources,
            enabled=enabled,
            purpose=purpose,
            derived=derived,
            differs_from_canonical=differs_from_canonical,
        )
    )


def _canonicalize_smiles(value: str) -> str:
    if not value:
        return ""
    try:
        from rdkit import Chem

        molecule = Chem.MolFromSmiles(value)
        if molecule is None:
            return ""
        return str(Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True))
    except Exception:
        return ""


def _normalize_cas(value: str) -> str:
    normalized = value.strip()
    for prefix in ("CAS RN", "CAS No.", "CAS No", "CAS #", "CAS:"):
        if normalized.casefold().startswith(prefix.casefold()):
            return normalized[len(prefix) :].strip()
    return normalized


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw_value in values:
        value = raw_value.strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
