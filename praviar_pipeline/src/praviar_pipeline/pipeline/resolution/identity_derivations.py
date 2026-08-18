"""Bounded, evidence-bearing chemistry derivations for identity review.

Derived structures are search hypotheses only. They never replace the
authoritative structure returned by compound resolution.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from praviar_pipeline.models.compound import (
    DerivedStructureCandidate,
    StructureIntegrityCheck,
    TautomerEnumerationRecord,
)

RDKIT_TAUTOMER_REFERENCE = (
    "https://www.rdkit.org/docs/source/rdkit.Chem.MolStandardize.rdMolStandardize.html"
)
RDKIT_REACTION_REFERENCE = "https://www.rdkit.org/docs/RDKit_Book.html#reaction-smarts"
ESTER_PRODRUG_REFERENCE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC3132824/"
PHOSPHATE_PRODRUG_REFERENCE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC7445155/"
CARBAMATE_REFERENCE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC4393377/"
DERIVATION_RULE_VERSION = "identity-chemistry/1"
DEFAULT_MAX_TAUTOMERS = 32
DEFAULT_MAX_TAUTOMER_TRANSFORMS = 64
DEFAULT_MAX_TAUTOMER_SEARCH_CANDIDATES = 8
DEFAULT_MAX_PRODRUG_SEARCH_CANDIDATES = 4
DEFAULT_MIN_PARENT_HEAVY_ATOM_FRACTION = 0.60
TautomerSourceForm = Literal["canonical", "salt_stripped_largest_fragment"]
TautomerStatus = Literal[
    "completed",
    "max_tautomers_reached",
    "max_transforms_reached",
    "parse_failed",
    "enumeration_failed",
    "not_applicable",
]


@dataclass(frozen=True)
class ProdrugDerivationResult:
    """Result of conservative, bounded prodrug-parent hypothesis generation."""

    candidates: list[DerivedStructureCandidate]
    detected_motifs: list[str]
    unsupported_motifs: list[str]


@dataclass(frozen=True)
class _ProdrugRule:
    rule_id: str
    label: str
    motif_label: str
    reactant_smarts: str
    transform_smarts: str
    evidence_reference: str
    limitation: str


_PRODRUG_RULES = (
    _ProdrugRule(
        rule_id="ester_hydrolysis_acid_parent",
        label="Ester hydrolysis — carboxylic-acid-side parent",
        motif_label="ester_prodrug_candidate",
        reactant_smarts="[C][C](=[O])[O;R0][#6]",
        transform_smarts="[C:5][C:1](=[O:2])[O;R0:3][#6:4]>>[C:5][C:1](=[O:2])O",
        evidence_reference=ESTER_PRODRUG_REFERENCE,
        limitation=(
            "Hydrolysis is a structural hypothesis only; the ester may be the active "
            "pharmacophore and the retained acid-side product may not be pharmacologically active."
        ),
    ),
    _ProdrugRule(
        rule_id="ester_hydrolysis_alcohol_parent",
        label="Ester hydrolysis — alcohol/phenol-side parent",
        motif_label="ester_prodrug_candidate",
        reactant_smarts="[C][C](=[O])[O;R0][#6]",
        transform_smarts="[C:5][C:1](=[O:2])[O;R0:3][#6:4]>>[O:3][#6:4]",
        evidence_reference=ESTER_PRODRUG_REFERENCE,
        limitation=(
            "Hydrolysis is a structural hypothesis only; the ester may be the active "
            "pharmacophore and the retained alcohol/phenol-side product may not be active."
        ),
    ),
    _ProdrugRule(
        rule_id="phosphate_monoester_dephosphorylation",
        label="Simple phosphate monoester — dephosphorylated parent",
        motif_label="phosphate_prodrug_candidate",
        reactant_smarts="[#6][O][P](=[O])([O])[O]",
        transform_smarts="[#6:1][O:2][P:3](=[O:4])([O:5])[O:6]>>[#6:1][O:2]",
        evidence_reference=PHOSPHATE_PRODRUG_REFERENCE,
        limitation=(
            "Only a simple O-phosphate monoester is modeled. Phosphonates, phosphoramidates, "
            "ProTides, cyclic phosphates, and multi-step promoiety activation are unsupported."
        ),
    ),
    _ProdrugRule(
        rule_id="o_carbamate_deprotection",
        label="O-carbamate — alcohol/phenol parent hypothesis",
        motif_label="carbamate_prodrug_candidate",
        reactant_smarts="[#6][O;R0][C](=[O])[N]",
        transform_smarts="[#6:1][O;R0:2][C:3](=[O:4])[N:5]>>[#6:1][O:2]",
        evidence_reference=CARBAMATE_REFERENCE,
        limitation=(
            "Carbamates are frequently active medicinal-chemistry motifs. This deprotection "
            "candidate is included only when the retained parent dominates the source structure."
        ),
    ),
    _ProdrugRule(
        rule_id="n_carbamate_deprotection",
        label="N-carbamate — amine parent hypothesis",
        motif_label="carbamate_prodrug_candidate",
        reactant_smarts="[N][C](=[O])[O;R0][#6]",
        transform_smarts="[N:1][C:2](=[O:3])[O;R0:4][#6:5]>>[N:1]",
        evidence_reference=CARBAMATE_REFERENCE,
        limitation=(
            "Carbamates are frequently active medicinal-chemistry motifs. This deprotection "
            "candidate is included only when the retained parent dominates the source structure."
        ),
    ),
)


def enumerate_tautomer_candidates(
    smiles: str,
    *,
    source_form: str = "canonical",
    max_tautomers: int = DEFAULT_MAX_TAUTOMERS,
    max_transforms: int = DEFAULT_MAX_TAUTOMER_TRANSFORMS,
    max_search_candidates: int = DEFAULT_MAX_TAUTOMER_SEARCH_CANDIDATES,
) -> TautomerEnumerationRecord:
    """Enumerate and validate a bounded deterministic tautomer search set."""
    from rdkit import Chem, rdBase
    from rdkit.Chem.MolStandardize import rdMolStandardize

    resolved_source_form: TautomerSourceForm = (
        "salt_stripped_largest_fragment"
        if source_form == "salt_stripped_largest_fragment"
        else "canonical"
    )
    source = Chem.MolFromSmiles(smiles)
    if source is None or not smiles:
        return _empty_tautomer_record(
            smiles=smiles,
            source_form=resolved_source_form,
            engine_version=rdBase.rdkitVersion,
            score_version=str(rdMolStandardize.TautomerEnumerator.tautomerScoreVersion),
            max_tautomers=max_tautomers,
            max_transforms=max_transforms,
            status="parse_failed",
            limitation="RDKit could not parse the source structure; no tautomer lane was added.",
        )

    source_canonical = Chem.MolToSmiles(source, isomericSmiles=True)
    source_properties = _structure_properties(source)
    enumerator = rdMolStandardize.TautomerEnumerator()
    enumerator.SetMaxTautomers(max_tautomers)
    enumerator.SetMaxTransforms(max_transforms)

    try:
        with rdBase.BlockLogs():
            result = enumerator.Enumerate(source)
    except Exception:
        return _empty_tautomer_record(
            smiles=source_canonical,
            source_form=resolved_source_form,
            engine_version=rdBase.rdkitVersion,
            score_version=str(enumerator.tautomerScoreVersion),
            max_tautomers=max_tautomers,
            max_transforms=max_transforms,
            status="enumeration_failed",
            limitation="RDKit tautomer enumeration failed; no tautomer lane was added.",
        )

    status = _tautomer_status(str(result.status))
    completed = status == "completed"
    tautomer_rows: list[tuple[int, str, Any]] = []
    for tautomer in result.tautomers:
        candidate_smiles = Chem.MolToSmiles(tautomer, isomericSmiles=True)
        tautomer_rows.append((int(enumerator.ScoreTautomer(tautomer)), candidate_smiles, tautomer))
    tautomer_rows.sort(key=lambda row: (-row[0], row[1]))

    canonical_tautomer = enumerator.PickCanonical(result.tautomers)
    canonical_tautomer_smiles = Chem.MolToSmiles(canonical_tautomer, isomericSmiles=True)
    ordered_rows = sorted(
        tautomer_rows,
        key=lambda row: (
            row[1] != canonical_tautomer_smiles,
            -row[0],
            row[1],
        ),
    )

    candidates: list[DerivedStructureCandidate] = []
    seen = {source_canonical}
    for _, candidate_smiles, candidate_mol in ordered_rows:
        if candidate_smiles in seen:
            continue
        seen.add(candidate_smiles)
        integrity = _tautomer_integrity(candidate_mol, source_properties)
        eligible = completed and integrity.passed
        exclusion_reason = ""
        if not completed:
            exclusion_reason = f"enumeration_status_{status}"
        elif not integrity.passed:
            exclusion_reason = "tautomer_property_invariant_failed"
        candidates.append(
            _candidate(
                kind="tautomer",
                label="RDKit enumerated tautomer",
                source_smiles=source_canonical,
                canonical_smiles=candidate_smiles,
                rule_id="rdkit_default_tautomer_enumerator",
                engine="RDKit MolStandardize TautomerEnumerator",
                engine_version=rdBase.rdkitVersion,
                hypothesis=False,
                search_eligible=eligible,
                exclusion_reason=exclusion_reason,
                integrity=integrity,
                evidence_references=[RDKIT_TAUTOMER_REFERENCE],
                limitation=(
                    "RDKit's configured rule set is deterministic but not a proof of every "
                    "solution-phase, solid-state, pH-dependent, or assay-relevant tautomer."
                ),
            )
        )
        if len(candidates) >= max_search_candidates:
            break

    limitation = (
        "Enumeration completed within its configured bounds. Only property-invariant, "
        "sanitized candidates in the bounded reviewer-approved set may expand search."
        if completed
        else (
            "Enumeration hit a configured bound or failed. Alternate tautomers are retained "
            "for audit only and are excluded from search."
        )
    )
    return TautomerEnumerationRecord(
        source_smiles=source_canonical,
        source_form=resolved_source_form,
        engine="RDKit MolStandardize TautomerEnumerator",
        engine_version=rdBase.rdkitVersion,
        score_version=str(enumerator.tautomerScoreVersion),
        max_tautomers=max_tautomers,
        max_transforms=max_transforms,
        status=status,
        enumerated_count=len(result.tautomers),
        canonical_tautomer_smiles=canonical_tautomer_smiles,
        candidates=candidates,
        search_expansion_allowed=completed
        and all(candidate.integrity.passed for candidate in candidates),
        limitation=limitation,
    )


def derive_prodrug_candidates(
    smiles: str,
    *,
    max_search_candidates: int = DEFAULT_MAX_PRODRUG_SEARCH_CANDIDATES,
    min_parent_heavy_atom_fraction: float = DEFAULT_MIN_PARENT_HEAVY_ATOM_FRACTION,
) -> ProdrugDerivationResult:
    """Generate bounded hydrolysis/deprotection hypotheses with strict checks."""
    from rdkit import Chem, rdBase
    from rdkit.Chem import rdChemReactions

    source = Chem.MolFromSmiles(smiles)
    if source is None or not smiles:
        return ProdrugDerivationResult(
            candidates=[],
            detected_motifs=[],
            unsupported_motifs=["source_structure_unparseable"],
        )

    source_smiles = Chem.MolToSmiles(source, isomericSmiles=True)
    source_properties = _structure_properties(source)
    detected: list[str] = []
    unsupported = _detect_unsupported_prodrug_motifs(source)
    complex_phosphorus = any(
        motif.startswith("complex_phosphorus") or motif.startswith("multiester_phosphate")
        for motif in unsupported
    )
    rows: list[DerivedStructureCandidate] = []
    seen: set[str] = {source_smiles}

    for rule in _PRODRUG_RULES:
        pattern = Chem.MolFromSmarts(rule.reactant_smarts)
        if pattern is None or not source.HasSubstructMatch(pattern):
            continue
        if rule.motif_label not in detected:
            detected.append(rule.motif_label)
        if rule.rule_id == "phosphate_monoester_dephosphorylation" and complex_phosphorus:
            continue

        with rdBase.BlockLogs():
            reaction = rdChemReactions.ReactionFromSmarts(rule.transform_smarts)
        if reaction is None:
            continue
        with rdBase.BlockLogs():
            product_sets = reaction.RunReactants((source,))
        for product_set in product_sets:
            for product in product_set:
                try:
                    Chem.SanitizeMol(product)
                except Exception:
                    continue
                product_smiles = Chem.MolToSmiles(product, isomericSmiles=True)
                if product_smiles in seen:
                    continue
                integrity = _prodrug_integrity(
                    product,
                    source=source,
                    source_properties=source_properties,
                    min_parent_heavy_atom_fraction=min_parent_heavy_atom_fraction,
                )
                if not integrity.passed:
                    continue
                seen.add(product_smiles)
                rows.append(
                    _candidate(
                        kind="prodrug_parent_hypothesis",
                        label=rule.label,
                        source_smiles=source_smiles,
                        canonical_smiles=product_smiles,
                        rule_id=rule.rule_id,
                        engine="RDKit ChemicalReaction",
                        engine_version=rdBase.rdkitVersion,
                        transform_smarts=rule.transform_smarts,
                        hypothesis=True,
                        search_eligible=True,
                        integrity=integrity,
                        evidence_references=[
                            RDKIT_REACTION_REFERENCE,
                            rule.evidence_reference,
                        ],
                        limitation=rule.limitation,
                    )
                )

    rows.sort(
        key=lambda candidate: (
            -candidate.integrity.retained_heavy_atom_fraction,
            candidate.rule_id,
            candidate.canonical_smiles,
        )
    )
    selected = rows[:max_search_candidates]

    for motif in detected:
        if not any(_rule_motif(candidate.rule_id) == motif for candidate in selected):
            unsupported.append(f"{motif}:no_dominant_validated_parent_candidate")

    return ProdrugDerivationResult(
        candidates=selected,
        detected_motifs=detected,
        unsupported_motifs=sorted(set(unsupported)),
    )


def _empty_tautomer_record(
    *,
    smiles: str,
    source_form: TautomerSourceForm,
    engine_version: str,
    score_version: str,
    max_tautomers: int,
    max_transforms: int,
    status: TautomerStatus,
    limitation: str,
) -> TautomerEnumerationRecord:
    return TautomerEnumerationRecord(
        source_smiles=smiles,
        source_form=source_form,
        engine="RDKit MolStandardize TautomerEnumerator",
        engine_version=engine_version,
        score_version=score_version,
        max_tautomers=max_tautomers,
        max_transforms=max_transforms,
        status=status,
        enumerated_count=0,
        search_expansion_allowed=False,
        limitation=limitation,
    )


def _tautomer_status(status: str) -> TautomerStatus:
    if status == "Completed":
        return "completed"
    if status == "MaxTautomersReached":
        return "max_tautomers_reached"
    if status == "MaxTransformsReached":
        return "max_transforms_reached"
    return "enumeration_failed"


def _structure_properties(mol: Any) -> dict[str, Any]:
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors

    return {
        "molecular_formula": rdMolDescriptors.CalcMolFormula(mol),
        "exact_mass": float(rdMolDescriptors.CalcExactMolWt(mol)),
        "heavy_atom_count": int(mol.GetNumHeavyAtoms()),
        "atom_count": int(mol.GetNumAtoms()),
        "formal_charge": int(Chem.GetFormalCharge(mol)),
        "fragment_count": len(Chem.GetMolFrags(mol)),
        "radical_electrons": sum(atom.GetNumRadicalElectrons() for atom in mol.GetAtoms()),
        "isotope_inventory": sorted(
            (atom.GetAtomicNum(), atom.GetIsotope()) for atom in mol.GetAtoms() if atom.GetIsotope()
        ),
        "element_counts": _element_counts(mol),
    }


def _tautomer_integrity(
    mol: Any,
    source_properties: dict[str, Any],
) -> StructureIntegrityCheck:
    props = _structure_properties(mol)
    checks = [
        "rdkit_sanitized",
        "single_connected_fragment",
        "molecular_formula_matches_source",
        "exact_mass_matches_source",
        "heavy_atom_count_matches_source",
        "formal_charge_matches_source",
        "isotope_inventory_matches_source",
        "no_radical_electrons",
    ]
    passed = bool(
        props["fragment_count"] == 1
        and props["molecular_formula"] == source_properties["molecular_formula"]
        and abs(props["exact_mass"] - source_properties["exact_mass"]) <= 1e-6
        and props["heavy_atom_count"] == source_properties["heavy_atom_count"]
        and props["formal_charge"] == source_properties["formal_charge"]
        and props["isotope_inventory"] == source_properties["isotope_inventory"]
        and props["radical_electrons"] == 0
    )
    return _integrity_model(props, passed=passed, checks=checks)


def _prodrug_integrity(
    mol: Any,
    *,
    source: Any,
    source_properties: dict[str, Any],
    min_parent_heavy_atom_fraction: float,
) -> StructureIntegrityCheck:
    props = _structure_properties(mol)
    retained_fraction = props["heavy_atom_count"] / source_properties["heavy_atom_count"]
    element_subset = all(
        count <= source_properties["element_counts"].get(atomic_number, 0)
        for atomic_number, count in props["element_counts"].items()
    )
    no_dummy_atoms = all(atom.GetAtomicNum() > 0 for atom in mol.GetAtoms())
    source_match = source.HasSubstructMatch(mol) or mol.HasSubstructMatch(source)
    checks = [
        "rdkit_sanitized",
        "single_connected_fragment",
        "no_new_heavy_elements",
        "no_dummy_atoms",
        "no_radical_electrons",
        "lower_heavy_atom_count_than_source",
        f"retained_heavy_atom_fraction_gte_{min_parent_heavy_atom_fraction:.2f}",
        "source_product_substructure_relation",
    ]
    passed = bool(
        props["fragment_count"] == 1
        and props["radical_electrons"] == 0
        and no_dummy_atoms
        and element_subset
        and 5 <= props["heavy_atom_count"] < source_properties["heavy_atom_count"]
        and retained_fraction >= min_parent_heavy_atom_fraction
        and props["exact_mass"] < source_properties["exact_mass"]
        and source_match
    )
    return _integrity_model(
        props,
        passed=passed,
        checks=checks,
        retained_heavy_atom_fraction=retained_fraction,
    )


def _integrity_model(
    props: dict[str, Any],
    *,
    passed: bool,
    checks: list[str],
    retained_heavy_atom_fraction: float = 1.0,
) -> StructureIntegrityCheck:
    return StructureIntegrityCheck(
        molecular_formula=props["molecular_formula"],
        exact_mass=round(props["exact_mass"], 8),
        heavy_atom_count=props["heavy_atom_count"],
        atom_count=props["atom_count"],
        formal_charge=props["formal_charge"],
        fragment_count=props["fragment_count"],
        radical_electrons=props["radical_electrons"],
        retained_heavy_atom_fraction=round(retained_heavy_atom_fraction, 6),
        passed=passed,
        checks=checks,
    )


def _candidate(
    *,
    kind: str,
    label: str,
    source_smiles: str,
    canonical_smiles: str,
    rule_id: str,
    engine: str,
    engine_version: str,
    hypothesis: bool,
    search_eligible: bool,
    integrity: StructureIntegrityCheck,
    evidence_references: list[str],
    limitation: str,
    transform_smarts: str = "",
    exclusion_reason: str = "",
) -> DerivedStructureCandidate:
    candidate_id = hashlib.sha256(
        "|".join(
            [
                DERIVATION_RULE_VERSION,
                kind,
                rule_id,
                source_smiles,
                canonical_smiles,
            ]
        ).encode("utf-8")
    ).hexdigest()
    return DerivedStructureCandidate(
        candidate_id=candidate_id,
        kind=kind,  # type: ignore[arg-type]
        label=label,
        source_smiles=source_smiles,
        canonical_smiles=canonical_smiles,
        rule_id=rule_id,
        rule_version=DERIVATION_RULE_VERSION,
        engine=engine,
        engine_version=engine_version,
        transform_smarts=transform_smarts,
        hypothesis=hypothesis,
        search_eligible=search_eligible,
        exclusion_reason=exclusion_reason,
        integrity=integrity,
        evidence_references=evidence_references,
        limitation=limitation,
    )


def _element_counts(mol: Any) -> dict[int, int]:
    counts: dict[int, int] = {}
    for atom in mol.GetAtoms():
        atomic_number = atom.GetAtomicNum()
        counts[atomic_number] = counts.get(atomic_number, 0) + 1
    return counts


def _detect_unsupported_prodrug_motifs(mol: Any) -> list[str]:
    from rdkit import Chem

    unsupported: list[str] = []
    for label, smarts in (
        ("acyloxyamide_activation_unsupported", "[N][C](=O)[C][O]"),
        ("carbonate_activation_ambiguous", "[#6][O][C](=O)[O][#6]"),
        ("thioester_activation_unsupported", "[C][C](=O)[S][#6]"),
    ):
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is not None and mol.HasSubstructMatch(pattern):
            unsupported.append(label)

    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 15:
            continue
        neighbors = list(atom.GetNeighbors())
        if any(neighbor.GetAtomicNum() in {6, 7} for neighbor in neighbors):
            unsupported.append(
                "complex_phosphorus_activation_unsupported:phosphonate_or_phosphoramidate"
            )
        organic_oxygen_count = 0
        for neighbor in neighbors:
            if neighbor.GetAtomicNum() != 8:
                continue
            if any(
                other.GetAtomicNum() == 6 and other.GetIdx() != atom.GetIdx()
                for other in neighbor.GetNeighbors()
            ):
                organic_oxygen_count += 1
        if organic_oxygen_count > 1:
            unsupported.append("multiester_phosphate_activation_unsupported")
    return sorted(set(unsupported))


def _rule_motif(rule_id: str) -> str:
    if rule_id.startswith("ester_"):
        return "ester_prodrug_candidate"
    if rule_id.startswith("phosphate_"):
        return "phosphate_prodrug_candidate"
    return "carbamate_prodrug_candidate"
