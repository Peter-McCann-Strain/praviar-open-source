"""E-SMILES (Extended SMILES) parsing + conversion utilities for MolParser.

MolParser-Base (arXiv 2411.11098, ICCV 2025) emits a custom string
format called **E-SMILES** — a superset of SMILES that wraps Markush
annotations in XML-like tags so the seq2seq decoder can produce them
unambiguously alongside chemistry. The tags MolParser emits are:

* ``<a>...</a>``   — atom label (rare; for heteroatom placeholders not
                     expressible in standard SMILES)
* ``<r>R1</r>``    — Markush R-group placeholder (bond to a variable
                     substituent named ``R1``). Standard CXSMILES form
                     is ``[*:1]`` with an annotation block ``|$;;;R1$|``
* ``<c>label</c>`` — atomic / fragment connection point (e.g. polymer
                     endpoints, biologic attachment sites)
* ``<dum>``        — dummy atom that carries no chemistry and should be
                     dropped when round-tripping to canonical SMILES.

RDKit cannot parse E-SMILES directly — we have to strip or translate
the tags first. The functions in this module are pure Python and have
no torch / transformers dependency; they run inside the main
``praviar_pipeline`` venv and are exercised by unit tests without the
MolParser worker venv installed.

Degenerate empty inputs retain explicit empty semantics. Missing chemistry
dependencies and failed conversions raise typed errors so invalid output is
never persisted as if it were a usable CXSMILES value.
"""

from __future__ import annotations

import re
from typing import Any


class ESmilesConversionError(ValueError):
    """E-SMILES could not be converted to a chemically valid representation."""


class ESmilesDependencyError(ImportError):
    """A required E-SMILES chemistry dependency is unavailable."""


# ---------------------------------------------------------------------------
# Tag grammar
# ---------------------------------------------------------------------------

# Paired tags: ``<a>...</a>``, ``<r>...</r>``, ``<c>...</c>``. The inner
# label is captured so callers can rebuild a Markush tag map.
_TAG_PATTERN = re.compile(r"<(a|r|c)>([^<]*)</\1>")

# Self-closing dummy tag: ``<dum>``. MolParser emits this for explicit
# dummy atoms that carry no chemistry; they are stripped on the
# round-trip to RDKit.
_DUM_PATTERN = re.compile(r"<dum\s*/?>", re.IGNORECASE)

# Any stray / unmatched tag we couldn't interpret — stripped defensively
# so RDKit gets clean SMILES. Never raises.
_STRAY_TAG_PATTERN = re.compile(r"<[^<>]*>")


def _empty_result(raw_esmiles: str = "") -> dict[str, Any]:
    """Return a well-formed empty parse result."""
    return {
        "core_smiles": "",
        "markush_tags": {},
        "is_markush": False,
        "raw_esmiles": raw_esmiles,
    }


def parse_esmiles(esmiles: str) -> dict[str, Any]:
    """Tokenize an E-SMILES string into a core SMILES + Markush tag map.

    Args:
        esmiles: Raw E-SMILES emitted by MolParser-Base. May contain
            ``<a>``, ``<r>``, ``<c>``, or ``<dum>`` tags. Whitespace is
            tolerated; leading/trailing whitespace is stripped.

    Returns:
        Dict with keys:
          * ``core_smiles`` — SMILES with Markush tags replaced by
            ``[*:N]`` placeholders (N increments from 1 in order of
            first appearance per distinct label).
          * ``markush_tags`` — map ``{"r1": "R1", "c1": "endpoint-a"}``
            where the key is ``<tagtype><index>`` and the value is the
            label found between the tags.
          * ``is_markush`` — True iff at least one ``<r>`` or ``<c>``
            tag was seen (``<a>`` alone or ``<dum>`` alone does **not**
            mark the molecule Markush).
          * ``raw_esmiles`` — the original input, trimmed of outer
            whitespace, for audit/debugging.

    Never raises. Empty / ``None`` / whitespace-only inputs return
    ``_empty_result``.
    """
    if not esmiles or not isinstance(esmiles, str):
        return _empty_result("")

    trimmed = esmiles.strip()
    if not trimmed:
        return _empty_result("")

    tags: dict[str, str] = {}
    # Per-tag-type counters for stable naming.
    counters: dict[str, int] = {"a": 0, "r": 0, "c": 0}
    # Per-label -> placeholder index so repeated ``<r>R1</r>`` maps to
    # the same ``[*:N]`` — that's what CXSMILES expects.
    rgroup_index: dict[str, int] = {}
    next_rgroup_idx = [1]

    is_markush = False

    def _sub_paired(match: re.Match[str]) -> str:
        nonlocal is_markush
        tag_type = match.group(1)
        label = (match.group(2) or "").strip()
        counters[tag_type] += 1
        key = f"{tag_type}{counters[tag_type]}"
        tags[key] = label

        if tag_type in ("r", "c"):
            is_markush = True
            # Collapse identical labels to the same index so
            # ``<r>R1</r>...<r>R1</r>`` becomes ``[*:1]...[*:1]``.
            if label and label in rgroup_index:
                idx = rgroup_index[label]
            else:
                idx = next_rgroup_idx[0]
                next_rgroup_idx[0] += 1
                if label:
                    rgroup_index[label] = idx
            return f"[*:{idx}]"
        # ``<a>`` — best-effort: drop the tag wrapping but keep whatever
        # is inside so RDKit can try to parse it.
        return label

    core = _TAG_PATTERN.sub(_sub_paired, trimmed)
    # Drop ``<dum>`` tokens entirely.
    core = _DUM_PATTERN.sub("", core)
    # Any stray tags that weren't recognised → strip, don't raise.
    core = _STRAY_TAG_PATTERN.sub("", core)
    core = core.strip()

    return {
        "core_smiles": core,
        "markush_tags": tags,
        "is_markush": is_markush,
        "raw_esmiles": trimmed,
    }


def esmiles_to_rdkit(esmiles: str) -> str:
    """Convert an E-SMILES string to canonical RDKit SMILES, if possible.

    For pure (non-Markush) E-SMILES the result is the RDKit-canonical
    SMILES of the underlying molecule. For Markush E-SMILES — where the
    core contains ``[*:N]`` placeholders — RDKit parses the structure
    but cannot produce a "canonical" form that preserves the label
    mapping cleanly, so we return an empty string and let the caller
    fall back to ``esmiles_to_cxsmiles`` + ``is_markush=True``.

    Args:
        esmiles: E-SMILES string.

    Returns:
        RDKit-canonical SMILES, or ``""`` if the input is Markush,
        empty, or unparseable.
    """
    parsed = parse_esmiles(esmiles)
    core = parsed["core_smiles"]
    if not core:
        return ""
    # Markush structures are not representable as canonical SMILES in a
    # lossless way; caller should use CXSMILES.
    if parsed["is_markush"]:
        return ""

    try:
        from rdkit import Chem
    except ImportError:
        raise ESmilesDependencyError("RDKit is required for E-SMILES conversion") from None

    try:
        mol = Chem.MolFromSmiles(core)
    except Exception:
        raise ESmilesConversionError("E-SMILES parsing failed") from None
    if mol is None:
        raise ESmilesConversionError("E-SMILES core is not chemically parseable")
    try:
        return Chem.MolToSmiles(mol)
    except Exception:
        raise ESmilesConversionError("E-SMILES serialization failed") from None


def esmiles_to_cxsmiles(esmiles: str) -> str:
    """Convert an E-SMILES string to CXSMILES (best effort).

    CXSMILES appends a ``|$...$|`` annotation block to a SMILES string
    listing atom labels in atom-order. MolParser's ``<r>R1</r>`` maps
    to ``[*:1]`` with an annotation ``R1`` at the position of that
    placeholder. The output shape is:

        ``<core_smiles> |$;;;;R1;$|``

    The leading semicolons correspond to the real atoms in the
    molecule that carry no label; the ``Rn`` entries sit at the
    ``[*:n]`` positions.

    Missing RDKit or an unparseable core raises instead of returning a raw
    tagged core that is not a valid CXSMILES representation.

    Args:
        esmiles: E-SMILES string.

    Returns:
        CXSMILES string, or ``""`` for degenerate input.
    """
    parsed = parse_esmiles(esmiles)
    core = parsed["core_smiles"]
    if not core:
        return ""

    # Non-Markush → CXSMILES is just the canonical SMILES (no annotation).
    if not parsed["is_markush"]:
        return esmiles_to_rdkit(esmiles)

    # Markush path: build an annotation block keyed by atom order.
    try:
        from rdkit import Chem
    except ImportError:
        raise ESmilesDependencyError("RDKit is required for E-SMILES conversion") from None

    try:
        mol = Chem.MolFromSmiles(core)
    except Exception:
        raise ESmilesConversionError("Markush E-SMILES parsing failed") from None
    if mol is None:
        raise ESmilesConversionError("Markush E-SMILES core is not chemically parseable")

    # Map ``[*:N]`` atoms → their R-group label from the tag map.
    # parse_esmiles gives us ``tags["r1"] = "R1"`` etc.; we need label
    # keyed by placeholder index.
    idx_to_label: dict[int, str] = {}
    # Reconstruct the index assignment the same way parse_esmiles did.
    seen: dict[str, int] = {}
    next_idx = 1
    # Walk the tag map in insertion order — dicts preserve it in 3.7+.
    for key, label in parsed["markush_tags"].items():
        if not key.startswith(("r", "c")):
            continue
        if not label:
            idx_to_label[next_idx] = ""
            next_idx += 1
            continue
        if label in seen:
            # Repeated label reuses its original index; do not advance.
            idx_to_label[seen[label]] = label
            continue
        seen[label] = next_idx
        idx_to_label[next_idx] = label
        next_idx += 1

    labels: list[str] = []
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 0:
            # Dummy atom — fetch the atom map number we assigned.
            map_num = atom.GetAtomMapNum()
            labels.append(idx_to_label.get(map_num, ""))
        else:
            labels.append("")

    try:
        base = Chem.MolToSmiles(mol)
    except Exception:
        raise ESmilesConversionError("Markush CXSMILES serialization failed") from None

    annotation = ";".join(labels)
    if annotation.strip(";"):
        return f"{base} |$" + annotation + "$|"
    return base
