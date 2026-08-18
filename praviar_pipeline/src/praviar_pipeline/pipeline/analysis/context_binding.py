"""Deterministic binding between a claim analysis and the customer matter context."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

_COMPOUND_IDENTITY_FIELDS = (
    "compound_type",
    "name",
    "canonical_smiles",
    "inchi",
    "inchi_key",
    "pubchem_cid",
    "original_input",
    "input_type",
    "free_base_smiles",
    "stereo_stripped_smiles",
    "scaffold_smiles",
    "unii",
    "gsrs_uuid",
    "gsrs_substance_class",
    "gsrs_definition_type",
    "gsrs_definition_level",
    "gsrs_record_version",
    "gsrs_names_last_updated",
    "gsrs_record_last_updated",
    "bla_number",
    "reference_product",
)


def _canonical_context_value(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return {
            str(key).strip(): _canonical_context_value(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
            if str(key).strip()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        normalized = [_canonical_context_value(item) for item in value]
        if isinstance(value, (set, frozenset)):
            return sorted(
                normalized,
                key=lambda item: json.dumps(item, sort_keys=True, default=str),
            )
        return normalized
    if value is None or isinstance(value, (bool, int, float)):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _canonical_context_value(model_dump(mode="json"))
    return str(value).strip()


def _compound_identity_projection(value: object) -> dict[str, object]:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        payload = {}
    projection = {
        field: _canonical_context_value(payload.get(field))
        for field in _COMPOUND_IDENTITY_FIELDS
        if payload.get(field) not in (None, "", [])
    }
    sequences = payload.get("protein_subunit_sequences")
    if isinstance(sequences, (list, tuple)):
        projection["protein_subunit_sequence_sha256"] = [
            hashlib.sha256(str(sequence).encode("utf-8")).hexdigest()
            for sequence in sequences
            if str(sequence)
        ]
    return projection


def analysis_context_payload(
    *,
    patent_id: str,
    compound_identity: object,
    product_context: object,
    intended_actions: list[str] | tuple[str, ...] | None,
    target_jurisdictions: list[str] | tuple[str, ...] | None,
    development_stage: object,
) -> dict[str, object]:
    """Return the canonical, prompt-safe matter facts used for claim analysis."""
    context = product_context if isinstance(product_context, Mapping) else {}
    normalized_context = _canonical_context_value(context)
    normalized_compound = _compound_identity_projection(compound_identity)
    return {
        "schema_version": "claim-analysis-context-v2",
        "patent_id": str(patent_id or "").strip().upper(),
        "compound_identity": normalized_compound,
        "development_stage": str(development_stage or "").strip().lower(),
        "intended_actions": sorted(
            {
                str(action).strip().lower()
                for action in intended_actions or []
                if str(action).strip()
            }
        ),
        "target_jurisdictions": sorted(
            {
                str(jurisdiction).strip().upper()
                for jurisdiction in target_jurisdictions or []
                if str(jurisdiction).strip()
            }
        ),
        "product_context": normalized_context,
    }


def analysis_context_sha256(
    *,
    patent_id: str,
    compound_identity: object,
    product_context: object,
    intended_actions: list[str] | tuple[str, ...] | None,
    target_jurisdictions: list[str] | tuple[str, ...] | None,
    development_stage: object,
) -> str:
    """Return a stable SHA-256 receipt for the exact analysis context."""
    payload = analysis_context_payload(
        patent_id=patent_id,
        compound_identity=compound_identity,
        product_context=product_context,
        intended_actions=intended_actions,
        target_jurisdictions=target_jurisdictions,
        development_stage=development_stage,
    )
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def analysis_context_json(
    *,
    patent_id: str,
    compound_identity: object,
    product_context: object,
    intended_actions: list[str] | tuple[str, ...] | None,
    target_jurisdictions: list[str] | tuple[str, ...] | None,
    development_stage: object,
) -> str:
    """Return canonical JSON for insertion into the governed model prompt."""
    return json.dumps(
        analysis_context_payload(
            patent_id=patent_id,
            compound_identity=compound_identity,
            product_context=product_context,
            intended_actions=intended_actions,
            target_jurisdictions=target_jurisdictions,
            development_stage=development_stage,
        ),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


__all__ = [
    "analysis_context_json",
    "analysis_context_payload",
    "analysis_context_sha256",
]
