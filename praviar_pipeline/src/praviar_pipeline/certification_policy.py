"""Shared certification policy for routed modalities and clearance cohorts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypedDict

DEFAULT_CERTIFICATION_POLICY_VERSION = "2026-04-core-v1"
DEFAULT_CERTIFIED_MODALITIES = (
    "small_molecule",
    "formulation",
    "process_or_synthesis",
)
DEFAULT_CERTIFIED_MATTER_TYPES = (
    "small_molecule",
    "formulation",
    "process",
)
DEFAULT_CERTIFIED_DECISION_JURISDICTIONS = ("US", "EP")
DEFAULT_CERTIFIED_ASSET_CLASSES = ("compound", "formulation", "process")
DEFAULT_MAJOR_MARKETS_JURISDICTIONS = ("US", "EP", "UK", "IN", "JP", "CN")
DEFAULT_JURISDICTION_BUNDLES: dict[str, tuple[str, ...]] = {
    "us_europe": ("US", "EP"),
    "europe_uk": ("EP", "UK"),
    "major_markets": DEFAULT_MAJOR_MARKETS_JURISDICTIONS,
    "custom": (),
}

_MODALITY_ALIASES = {
    "small_molecule": "small_molecule",
    "markush": "markush_candidate",
    "markush_candidate": "markush_candidate",
    "biologic": "biologic_or_sequence",
    "biologic_or_sequence": "biologic_or_sequence",
    "biologic_sequence": "biologic_or_sequence",
    "sequence": "biologic_or_sequence",
    "formulation": "formulation",
    "process": "process_or_synthesis",
    "process_or_synthesis": "process_or_synthesis",
    "combination": "combination",
    "unknown": "unknown",
}

_JURISDICTION_ALIASES = {
    "US": "US",
    "USA": "US",
    "EP": "EP",
    "EPC": "EP",
    "EUROPE": "EP",
    "UK": "UK",
    "GB": "UK",
    "GBR": "UK",
    "UNITED_KINGDOM": "UK",
    "IN": "IN",
    "INDIA": "IN",
    "JP": "JP",
    "JAPAN": "JP",
    "CN": "CN",
    "CHINA": "CN",
    "WO": "WO",
    "PCT": "WO",
}

_MATTER_TYPE_ALIASES = {
    "small_molecule": "small_molecule",
    "formulation": "formulation",
    "process": "process",
    "process_or_synthesis": "process",
    "biologic": "biologic",
    "biologic_or_sequence": "biologic",
    "combination": "combination",
    "markush_candidate": "markush_candidate",
    "unknown": "unknown",
}


class _RuntimeAdapterRule(TypedDict):
    modalities: tuple[str, ...]
    jurisdictions: tuple[str, ...]


_RUNTIME_ADAPTER_RULES: dict[str, _RuntimeAdapterRule] = {
    "bigquery": {
        "modalities": DEFAULT_CERTIFIED_MODALITIES,
        "jurisdictions": (),
    },
    "patentsview": {
        "modalities": DEFAULT_CERTIFIED_MODALITIES,
        "jurisdictions": ("US",),
    },
    "epo_search": {
        "modalities": DEFAULT_CERTIFIED_MODALITIES,
        "jurisdictions": ("EP",),
    },
    "uspto_odp": {
        "modalities": DEFAULT_CERTIFIED_MODALITIES,
        "jurisdictions": ("US",),
    },
    "epo_register": {
        "modalities": DEFAULT_CERTIFIED_MODALITIES,
        "jurisdictions": ("EP",),
    },
    "federated_register": {
        "modalities": DEFAULT_CERTIFIED_MODALITIES,
        "jurisdictions": ("EP", "UK"),
    },
    "ptab": {
        "modalities": DEFAULT_CERTIFIED_MODALITIES,
        "jurisdictions": ("US",),
    },
    "orange_book": {
        "modalities": ("small_molecule", "formulation"),
        "jurisdictions": ("US",),
    },
    "purple_book": {
        "modalities": ("biologic_or_sequence",),
        "jurisdictions": ("US",),
    },
}

_TRUST_MODES = {"explorer", "counsel", "monitor"}


def _normalize_text(value: object) -> str:
    return str(value or "").strip().lower()


def _normalize_unique_strings(values: object, *, uppercase: bool = False) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = [part.strip() for part in values.split(",") if part.strip()]
    elif not isinstance(values, Iterable):
        raise TypeError("certification policy values must be a string or iterable")

    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        normalized = normalized.upper() if uppercase else normalized.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def normalize_modality(value: object) -> str:
    normalized = _normalize_text(value)
    return _MODALITY_ALIASES.get(normalized, normalized)


def normalize_matter_type(value: object) -> str:
    normalized = _normalize_text(value)
    return _MATTER_TYPE_ALIASES.get(normalized, normalized)


def normalize_jurisdiction(value: object) -> str:
    normalized = str(value or "").strip().replace("-", "_").replace(" ", "_").upper()
    return _JURISDICTION_ALIASES.get(normalized, normalized)


def normalize_trust_mode(value: object) -> str:
    normalized = _normalize_text(value)
    return normalized if normalized in _TRUST_MODES else "explorer"


@dataclass(frozen=True)
class CertificationPolicySnapshot:
    version: str
    certified_modalities: tuple[str, ...]
    certified_matter_types: tuple[str, ...]
    certified_decision_jurisdictions: tuple[str, ...]
    certified_asset_classes: tuple[str, ...]
    supported_jurisdictions: tuple[str, ...]
    counsel_certification_matrix: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class RuntimeAdapterCertificationResult:
    adapter_name: str
    allowed: bool
    reason: str = ""


def certification_policy_from_settings(settings=None) -> CertificationPolicySnapshot:
    certified_modalities = _normalize_unique_strings(
        getattr(settings, "certified_modalities", DEFAULT_CERTIFIED_MODALITIES)
        if settings is not None
        else DEFAULT_CERTIFIED_MODALITIES
    )
    certified_matter_types = tuple(
        normalize_matter_type(value)
        for value in _normalize_unique_strings(
            getattr(settings, "certified_matter_types", DEFAULT_CERTIFIED_MATTER_TYPES)
            if settings is not None
            else DEFAULT_CERTIFIED_MATTER_TYPES
        )
    )
    certified_decision_jurisdictions = _normalize_unique_strings(
        getattr(
            settings,
            "certified_decision_jurisdictions",
            DEFAULT_CERTIFIED_DECISION_JURISDICTIONS,
        )
        if settings is not None
        else DEFAULT_CERTIFIED_DECISION_JURISDICTIONS,
        uppercase=True,
    )
    certified_decision_jurisdictions = tuple(
        normalize_jurisdiction(value) for value in certified_decision_jurisdictions
    )
    certified_asset_classes = _normalize_unique_strings(
        getattr(settings, "certified_asset_classes", DEFAULT_CERTIFIED_ASSET_CLASSES)
        if settings is not None
        else DEFAULT_CERTIFIED_ASSET_CLASSES
    )
    version = (
        str(
            getattr(settings, "certification_policy_version", DEFAULT_CERTIFICATION_POLICY_VERSION)
            if settings is not None
            else DEFAULT_CERTIFICATION_POLICY_VERSION
        ).strip()
        or DEFAULT_CERTIFICATION_POLICY_VERSION
    )
    supported_jurisdictions = tuple(
        jurisdiction
        for jurisdiction in (
            *DEFAULT_MAJOR_MARKETS_JURISDICTIONS,
            *certified_decision_jurisdictions,
        )
        if jurisdiction
    )
    deduped_supported: list[str] = []
    seen_supported: set[str] = set()
    for jurisdiction in supported_jurisdictions:
        if jurisdiction in seen_supported:
            continue
        seen_supported.add(jurisdiction)
        deduped_supported.append(jurisdiction)

    counsel_certification_matrix: dict[str, tuple[str, ...]] = {}
    for modality in tuple(normalize_modality(value) for value in certified_modalities):
        if modality not in {"small_molecule", "formulation", "process_or_synthesis"}:
            counsel_certification_matrix[modality] = ()
            continue
        counsel_certification_matrix[modality] = certified_decision_jurisdictions

    return CertificationPolicySnapshot(
        version=version,
        certified_modalities=tuple(normalize_modality(value) for value in certified_modalities),
        certified_matter_types=certified_matter_types,
        certified_decision_jurisdictions=certified_decision_jurisdictions,
        certified_asset_classes=certified_asset_classes,
        supported_jurisdictions=tuple(deduped_supported),
        counsel_certification_matrix=counsel_certification_matrix,
    )


def is_certified_modality(value: object, *, settings=None) -> bool:
    modality = normalize_modality(value)
    if not modality:
        return False
    return modality in certification_policy_from_settings(settings).certified_modalities


def is_certified_matter_type(value: object, *, settings=None) -> bool:
    matter_type = normalize_matter_type(value)
    if not matter_type:
        return False
    return matter_type in certification_policy_from_settings(settings).certified_matter_types


def _jurisdictions_from_targets(
    *,
    target_patent_ids: list[str] | None = None,
    target_jurisdictions: list[str] | None = None,
) -> tuple[str, ...]:
    explicit = _normalize_unique_strings(target_jurisdictions or (), uppercase=True)
    if explicit:
        return explicit
    derived = []
    for patent_id in target_patent_ids or []:
        normalized = str(patent_id or "").strip().upper()
        if len(normalized) >= 2:
            derived.append(normalized[:2])
    return _normalize_unique_strings(derived, uppercase=True)


def runtime_adapter_allowed_jurisdictions(adapter_name: str) -> tuple[str, ...]:
    rule = _RUNTIME_ADAPTER_RULES.get(str(adapter_name or "").strip())
    if rule is None:
        return ()
    return tuple(
        normalize_jurisdiction(value)
        for value in _normalize_unique_strings(rule["jurisdictions"], uppercase=True)
    )


def certify_runtime_adapter(
    adapter_name: str,
    *,
    settings=None,
    target_patent_ids: list[str] | None = None,
    target_jurisdictions: list[str] | None = None,
) -> RuntimeAdapterCertificationResult:
    normalized_name = str(adapter_name or "").strip()
    rule = _RUNTIME_ADAPTER_RULES.get(normalized_name)
    if rule is None:
        return RuntimeAdapterCertificationResult(adapter_name=normalized_name, allowed=True)

    modality = normalize_modality(
        getattr(settings, "asset_type_hint", "") or getattr(settings, "matter_type", "")
    )
    allowed_modalities = tuple(normalize_modality(value) for value in rule["modalities"])
    if modality and modality not in allowed_modalities:
        return RuntimeAdapterCertificationResult(
            adapter_name=normalized_name,
            allowed=False,
            reason=(
                f"Filtered by certification policy for modality {modality}; "
                f"{normalized_name} is not validated for this routed cohort."
            ),
        )

    target_codes = _jurisdictions_from_targets(
        target_patent_ids=target_patent_ids,
        target_jurisdictions=target_jurisdictions,
    )
    allowed_jurisdictions = runtime_adapter_allowed_jurisdictions(normalized_name)
    if (
        allowed_jurisdictions
        and target_codes
        and not (set(target_codes) & set(allowed_jurisdictions))
    ):
        return RuntimeAdapterCertificationResult(
            adapter_name=normalized_name,
            allowed=False,
            reason=(
                "Filtered by certification policy for jurisdictions "
                f"{', '.join(target_codes)}; {normalized_name} is not validated there."
            ),
        )

    return RuntimeAdapterCertificationResult(adapter_name=normalized_name, allowed=True)


def expand_jurisdiction_bundle(
    jurisdiction_bundle: object,
    *,
    target_jurisdictions: list[str] | tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    bundle = _normalize_text(jurisdiction_bundle)
    explicit = tuple(
        normalize_jurisdiction(value)
        for value in _normalize_unique_strings(target_jurisdictions or (), uppercase=True)
        if normalize_jurisdiction(value)
    )
    if bundle == "custom":
        return explicit
    bundled = DEFAULT_JURISDICTION_BUNDLES.get(bundle)
    if bundled is None:
        return explicit
    if explicit:
        return tuple(jurisdiction for jurisdiction in (*bundled, *explicit) if jurisdiction)
    return bundled


def infer_jurisdiction_bundle(
    target_jurisdictions: list[str] | tuple[str, ...] | None,
) -> str:
    normalized = tuple(
        normalize_jurisdiction(value)
        for value in _normalize_unique_strings(target_jurisdictions or (), uppercase=True)
        if normalize_jurisdiction(value)
    )
    for bundle_name, bundle_jurisdictions in DEFAULT_JURISDICTION_BUNDLES.items():
        if bundle_name == "custom":
            continue
        if normalized == bundle_jurisdictions:
            return bundle_name
    return "custom"


def counsel_certified_jurisdictions_for_modality(
    modality: object,
    *,
    settings=None,
) -> tuple[str, ...]:
    normalized_modality = normalize_modality(modality)
    policy = certification_policy_from_settings(settings)
    return tuple(policy.counsel_certification_matrix.get(normalized_modality, ()))


def lane_status_for_trust_mode(
    jurisdiction: object,
    *,
    modality: object,
    trust_mode: object,
    settings=None,
) -> str:
    normalized_jurisdiction = normalize_jurisdiction(jurisdiction)
    normalized_trust_mode = normalize_trust_mode(trust_mode)
    certified_jurisdictions = set(
        counsel_certified_jurisdictions_for_modality(modality, settings=settings)
    )
    if normalized_jurisdiction in certified_jurisdictions:
        return "counsel_certified"
    if normalized_trust_mode == "monitor":
        return "monitor_only"
    return "screening_only"


def local_review_required_for_lane(
    jurisdiction: object,
    *,
    modality: object,
    settings=None,
) -> bool:
    normalized_jurisdiction = normalize_jurisdiction(jurisdiction)
    certified_jurisdictions = set(
        counsel_certified_jurisdictions_for_modality(modality, settings=settings)
    )
    return normalized_jurisdiction not in certified_jurisdictions


def filter_runtime_adapter_patent_ids(
    adapter_name: str,
    *,
    target_patent_ids: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    patent_ids = [str(patent_id or "").strip() for patent_id in list(target_patent_ids or [])]
    allowed_jurisdictions = runtime_adapter_allowed_jurisdictions(adapter_name)
    if not allowed_jurisdictions:
        return [patent_id for patent_id in patent_ids if patent_id]

    filtered: list[str] = []
    seen: set[str] = set()
    for patent_id in patent_ids:
        normalized = patent_id.upper()
        if len(normalized) < 2 or normalized[:2] not in allowed_jurisdictions:
            continue
        if patent_id in seen:
            continue
        seen.add(patent_id)
        filtered.append(patent_id)
    return filtered


def filter_certified_runtime_adapters(
    adapter_names: list[str] | tuple[str, ...],
    *,
    settings=None,
    target_patent_ids: list[str] | None = None,
    target_jurisdictions: list[str] | None = None,
) -> list[str]:
    filtered: list[str] = []
    seen: set[str] = set()
    for adapter_name in adapter_names:
        result = certify_runtime_adapter(
            adapter_name,
            settings=settings,
            target_patent_ids=target_patent_ids,
            target_jurisdictions=target_jurisdictions,
        )
        if not result.allowed or result.adapter_name in seen:
            continue
        seen.add(result.adapter_name)
        filtered.append(result.adapter_name)
    return filtered
