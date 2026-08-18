"""Tool functions exposed to the MarkushScopeAgent (Phase E).

These are deterministic, non-LLM functions the agent calls to ground its
reasoning in RDKit/OPSIN/PubChem facts instead of hallucinating a scope
verdict from claim text alone. Each function has a narrow contract: pure
function, serialisable inputs/outputs, suitable for Anthropic tool-use.

Distinction from the sibling `markush.py`: that file parses claim text into
a naive SMARTS pattern using a ~40-entry R-group lookup. These tools are
lower-level primitives the agent combines to decide scope membership.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from rdkit import Chem

# R-group enumeration cap. 10K variants is the Phase E plan's abstention
# trigger - larger Markush scopes (e.g. alkyl(C1-C20) x halogen x 5 R-groups)
# combinatorially explode and are better flagged for human review than
# truncated silently.
DEFAULT_MAX_ENUMERATION = 10_000


@dataclass(slots=True, frozen=True)
class EnumerationResult:
    """Output of rgroup_enumerate. `overflowed=True` means truncated or aborted."""

    hits: list[str]
    total_generated: int
    overflowed: bool
    reason: str = ""


def rdkit_canonical(smiles: str) -> str:
    """Return canonical SMILES or empty string on failure."""
    if not smiles:
        return ""
    mol = Chem.MolFromSmiles(smiles)
    return Chem.MolToSmiles(mol) if mol else ""


def rdkit_substructure_match(pattern_smiles: str, target_smiles: str) -> bool:
    """True iff `target_smiles` contains `pattern_smiles` as a substructure.

    Uses RDKit's `HasSubstructMatch`. Both arguments canonicalised on entry.
    Either empty/invalid → False.
    """
    if not pattern_smiles or not target_smiles:
        return False
    pat = Chem.MolFromSmiles(pattern_smiles)
    tgt = Chem.MolFromSmiles(target_smiles)
    if pat is None or tgt is None:
        return False
    try:
        return bool(tgt.HasSubstructMatch(pat))
    except Exception:
        return False


def rdkit_smarts_match(smarts_pattern: str, target_smiles: str) -> bool:
    """True iff `target_smiles` matches the SMARTS pattern.

    SMARTS allows query features (`[F,Cl,Br,I]`, `[CX4]`, etc.) that raw
    SMILES does not. Used by the agent to check Markush-style R-group
    constraints like `[F,Cl,Br,I]` for `halogen`.
    """
    if not smarts_pattern or not target_smiles:
        return False
    pat = Chem.MolFromSmarts(smarts_pattern)
    tgt = Chem.MolFromSmiles(target_smiles)
    if pat is None or tgt is None:
        return False
    try:
        return bool(tgt.HasSubstructMatch(pat))
    except Exception:
        return False


def rgroup_enumerate(
    scaffold_smiles: str,
    r_group_substitutions: dict[str, list[str]],
    max_enumerations: int = DEFAULT_MAX_ENUMERATION,
) -> EnumerationResult:
    """Enumerate concrete SMILES from a scaffold template + R-group options.

    Input:
      scaffold_smiles — scaffold with placeholders like `[*:1]`, `[*:2]`, ...
      r_group_substitutions — {"1": ["C", "CC", "F"], "2": ["[OH]", "Cl"]}
      max_enumerations — hard cap; abstain with overflowed=True if exceeded.

    Output: EnumerationResult with canonicalised SMILES hits. Invalid
    variants (RDKit parse failure) are silently skipped.

    Strategy: cartesian product across R-group options, string-substitute
    `[*:N]` → substituent SMILES, RDKit-canonicalise. If the total product
    count would exceed the cap, return overflowed=True without enumerating.
    """
    if not scaffold_smiles:
        return EnumerationResult(
            hits=[], total_generated=0, overflowed=False, reason="empty_scaffold"
        )

    if not r_group_substitutions:
        canon = rdkit_canonical(scaffold_smiles)
        return EnumerationResult(
            hits=[canon] if canon else [],
            total_generated=1 if canon else 0,
            overflowed=False,
        )

    # Combinatorial cardinality check BEFORE enumerating.
    cardinality = 1
    for subs in r_group_substitutions.values():
        cardinality *= max(len(subs), 1)
    if cardinality > max_enumerations:
        return EnumerationResult(
            hits=[],
            total_generated=cardinality,
            overflowed=True,
            reason=f"cartesian cardinality {cardinality} exceeds cap {max_enumerations}",
        )

    keys = sorted(r_group_substitutions.keys())
    options: list[list[str]] = [r_group_substitutions[k] for k in keys]

    hits: list[str] = []
    seen: set[str] = set()
    for combo in itertools.product(*options):
        template = scaffold_smiles
        for k, sub in zip(keys, combo, strict=True):
            # Replace [*:N] placeholder with substituent (wrapped to avoid
            # adjacent-atom ambiguity; RDKit will canonicalise).
            template = template.replace(f"[*:{k}]", sub)
        canon = rdkit_canonical(template)
        if canon and canon not in seen:
            seen.add(canon)
            hits.append(canon)

    return EnumerationResult(
        hits=hits,
        total_generated=len(hits),
        overflowed=False,
    )


_PUNCT_STRIP = re.compile(r"[^\w\s\-]+")


def normalise_rgroup_label(label: str) -> str:
    """Canonicalise a Markush R-group label for agent consumption.

    Strips punctuation, normalises whitespace, lowercases. Used to
    reconcile `R1`, `r1`, `R-1`, `(R1)` etc.
    """
    if not label:
        return ""
    return _PUNCT_STRIP.sub("", label.lower()).strip()


def agent_tool_definitions() -> list[dict]:
    """Return Anthropic tool-use JSON schemas for the agent harness.

    Single source of truth for tool shapes. The agent harness passes these
    verbatim in the `tools` field of messages.create(). Keep names/descriptions
    short — they get cache-busted if they change.
    """
    return [
        {
            "name": "rdkit_substructure_match",
            "description": (
                "Return True iff the target SMILES contains the pattern SMILES "
                "as a substructure. Use to check if a target compound's core "
                "matches a Markush scaffold."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern_smiles": {"type": "string"},
                    "target_smiles": {"type": "string"},
                },
                "required": ["pattern_smiles", "target_smiles"],
            },
        },
        {
            "name": "rdkit_smarts_match",
            "description": (
                "Return True iff the target SMILES matches a SMARTS pattern. "
                "Use for R-group constraint checks e.g. '[F,Cl,Br,I]' for halogen."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "smarts_pattern": {"type": "string"},
                    "target_smiles": {"type": "string"},
                },
                "required": ["smarts_pattern", "target_smiles"],
            },
        },
        {
            "name": "rdkit_canonical",
            "description": "Return the canonical SMILES for an input SMILES. Empty if invalid.",
            "input_schema": {
                "type": "object",
                "properties": {"smiles": {"type": "string"}},
                "required": ["smiles"],
            },
        },
        {
            "name": "rgroup_enumerate",
            "description": (
                "Enumerate concrete compound SMILES from a scaffold template with "
                "[*:N] placeholders and per-placeholder substitution options. Hard "
                "cap 10,000 variants; returns overflowed=True if exceeded."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "scaffold_smiles": {"type": "string"},
                    "r_group_substitutions": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "max_enumerations": {"type": "integer", "default": 10000},
                },
                "required": ["scaffold_smiles", "r_group_substitutions"],
            },
        },
    ]


def dispatch_tool(name: str, args: dict) -> dict:
    """Dispatch a tool call from the agent to the actual Python function.

    Returns a JSON-serialisable dict — never raises (errors wrapped).
    """
    try:
        if name == "rdkit_substructure_match":
            return {
                "matched": rdkit_substructure_match(
                    args.get("pattern_smiles", ""),
                    args.get("target_smiles", ""),
                )
            }
        if name == "rdkit_smarts_match":
            return {
                "matched": rdkit_smarts_match(
                    args.get("smarts_pattern", ""),
                    args.get("target_smiles", ""),
                )
            }
        if name == "rdkit_canonical":
            return {"canonical": rdkit_canonical(args.get("smiles", ""))}
        if name == "rgroup_enumerate":
            result = rgroup_enumerate(
                args.get("scaffold_smiles", ""),
                args.get("r_group_substitutions", {}),
                max_enumerations=int(args.get("max_enumerations", DEFAULT_MAX_ENUMERATION)),
            )
            return {
                "hits": result.hits,
                "total_generated": result.total_generated,
                "overflowed": result.overflowed,
                "reason": result.reason,
            }
        return {"error": f"unknown tool: {name}"}
    except Exception:  # pragma: no cover — defensive boundary
        return {"error": "markush tool execution failed"}


class MarkushToolkit:
    """Toolkit conforming to clients.claude.Toolkit Protocol for the
    MarkushScopeAgent. Wraps the module-level `agent_tool_definitions` +
    `dispatch_tool` so the agent can use the standard ClaudeClient tool-use
    loop.

    State: toolkit tracks a call counter so the agent output can report
    how many tool invocations grounded the verdict.
    """

    def __init__(self) -> None:
        self.call_count = 0

    @property
    def tool_definitions(self) -> list[dict]:
        return agent_tool_definitions()

    async def execute(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call and return a JSON-serialised result string.

        Signature matches Toolkit Protocol: async def execute(name, input) -> str.
        Returns a compact JSON string so the ClaudeClient tool-use loop can
        embed it in the next turn's tool_result content block.
        """
        import json as _json

        self.call_count += 1
        result = dispatch_tool(tool_name, tool_input)
        return _json.dumps(result, separators=(",", ":"))
