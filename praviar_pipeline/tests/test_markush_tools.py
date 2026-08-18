"""Tests for agents/tools/markush_tools.py (Phase E.2)."""

from __future__ import annotations

import pytest

pytest.importorskip("praviar_pipeline.agents.tools.markush_tools")

from praviar_pipeline.agents.tools.markush_tools import (
    DEFAULT_MAX_ENUMERATION,
    agent_tool_definitions,
    dispatch_tool,
    normalise_rgroup_label,
    rdkit_canonical,
    rdkit_smarts_match,
    rdkit_substructure_match,
    rgroup_enumerate,
)


class TestRdkitCanonical:
    def test_empty(self):
        assert rdkit_canonical("") == ""

    def test_invalid(self):
        assert rdkit_canonical("NOT_SMILES") == ""

    def test_ethanol(self):
        assert rdkit_canonical("CCO") == "CCO"

    def test_benzene_kekulized(self):
        # Upper-case ring form should canonicalize to aromatic lowercase.
        assert rdkit_canonical("C1=CC=CC=C1") == "c1ccccc1"


class TestSubstructureMatch:
    def test_benzene_in_toluene(self):
        assert rdkit_substructure_match("c1ccccc1", "Cc1ccccc1")

    def test_toluene_not_in_benzene(self):
        assert not rdkit_substructure_match("Cc1ccccc1", "c1ccccc1")

    def test_invalid_pattern(self):
        assert not rdkit_substructure_match("NOPE", "CCO")

    def test_empty_inputs(self):
        assert not rdkit_substructure_match("", "CCO")
        assert not rdkit_substructure_match("CCO", "")


class TestSmartsMatch:
    def test_halogen_matches_chlorobenzene(self):
        # [F,Cl,Br,I] should match any halogen-bearing compound
        assert rdkit_smarts_match("[F,Cl,Br,I]", "Clc1ccccc1")
        assert rdkit_smarts_match("[F,Cl,Br,I]", "Fc1ccccc1")
        assert rdkit_smarts_match("[F,Cl,Br,I]", "Brc1ccccc1")

    def test_halogen_rejects_unsubstituted(self):
        assert not rdkit_smarts_match("[F,Cl,Br,I]", "c1ccccc1")

    def test_alkyl_smarts_matches(self):
        assert rdkit_smarts_match("[CX4]", "CCO")  # ethanol has sp3 carbons

    def test_invalid_pattern(self):
        assert not rdkit_smarts_match("!@#$", "CCO")


class TestRgroupEnumerate:
    def test_no_rgroups_returns_scaffold_canonical(self):
        result = rgroup_enumerate("CCO", {})
        assert result.hits == ["CCO"]
        assert not result.overflowed

    def test_empty_scaffold(self):
        result = rgroup_enumerate("", {"1": ["C"]})
        assert result.hits == []
        assert not result.overflowed

    def test_single_rgroup_enumeration(self):
        # Benzene with one substituent placeholder
        result = rgroup_enumerate("[*:1]c1ccccc1", {"1": ["C", "F", "Cl"]})
        assert not result.overflowed
        assert len(result.hits) == 3
        # Canonical forms of methylbenzene / fluorobenzene / chlorobenzene
        assert "Cc1ccccc1" in result.hits
        assert "Fc1ccccc1" in result.hits
        assert "Clc1ccccc1" in result.hits

    def test_two_rgroup_cartesian(self):
        result = rgroup_enumerate(
            "[*:1]c1ccc([*:2])cc1",
            {"1": ["C", "F"], "2": ["O", "Cl"]},
        )
        assert not result.overflowed
        assert len(result.hits) == 4  # 2 x 2 combinations

    def test_overflow_aborts(self):
        # 3 x 4 x 1000 = 12,000 -> overflow
        subs = {
            "1": ["C", "F", "Cl"],
            "2": ["O", "N", "S", "P"],
            "3": [f"C{'C' * (i % 8)}" for i in range(1000)],
        }
        result = rgroup_enumerate("[*:1]c1ccc([*:2])c([*:3])c1", subs, max_enumerations=10_000)
        assert result.overflowed
        assert result.hits == []
        assert result.total_generated == 12_000
        assert "cardinality" in result.reason.lower()

    def test_custom_cap_respected(self):
        subs = {"1": ["C"] * 50}
        result = rgroup_enumerate("[*:1]c1ccccc1", subs, max_enumerations=10)
        assert result.overflowed

    def test_invalid_variants_skipped(self):
        # Second option is not a valid SMILES fragment → skipped silently
        result = rgroup_enumerate("[*:1]CC", {"1": ["C", "GARBAGE", "F"]})
        assert not result.overflowed
        assert len(result.hits) == 2  # only the 2 valid ones

    def test_duplicates_deduplicated(self):
        # Both "C" and "[CH3]" canonicalize to the same SMILES
        result = rgroup_enumerate("[*:1]CC", {"1": ["C", "[CH3]"]})
        canon = rdkit_canonical("CCC")
        assert result.hits.count(canon) == 1


class TestNormaliseRgroupLabel:
    def test_empty(self):
        assert normalise_rgroup_label("") == ""

    def test_strips_punctuation(self):
        assert normalise_rgroup_label("(R1)") == "r1"
        assert normalise_rgroup_label("R-1") == "r-1"

    def test_lowercases(self):
        assert normalise_rgroup_label("R1") == "r1"
        assert normalise_rgroup_label("X") == "x"


class TestAgentToolDefinitions:
    def test_returns_list_of_dicts(self):
        defs = agent_tool_definitions()
        assert isinstance(defs, list)
        assert all(isinstance(d, dict) for d in defs)

    def test_required_keys_present(self):
        for d in agent_tool_definitions():
            assert "name" in d
            assert "description" in d
            assert "input_schema" in d
            assert d["input_schema"]["type"] == "object"

    def test_names_unique(self):
        names = [d["name"] for d in agent_tool_definitions()]
        assert len(names) == len(set(names))

    def test_contains_core_tools(self):
        names = {d["name"] for d in agent_tool_definitions()}
        assert "rdkit_substructure_match" in names
        assert "rdkit_smarts_match" in names
        assert "rdkit_canonical" in names
        assert "rgroup_enumerate" in names


class TestDispatchTool:
    def test_unknown_tool_returns_error(self):
        result = dispatch_tool("not_a_tool", {})
        assert "error" in result

    def test_dispatch_canonical(self):
        result = dispatch_tool("rdkit_canonical", {"smiles": "C1=CC=CC=C1"})
        assert result["canonical"] == "c1ccccc1"

    def test_dispatch_substructure_match(self):
        result = dispatch_tool(
            "rdkit_substructure_match",
            {"pattern_smiles": "c1ccccc1", "target_smiles": "Cc1ccccc1"},
        )
        assert result == {"matched": True}

    def test_dispatch_smarts_halogen(self):
        result = dispatch_tool(
            "rdkit_smarts_match",
            {"smarts_pattern": "[F,Cl,Br,I]", "target_smiles": "Clc1ccccc1"},
        )
        assert result == {"matched": True}

    def test_dispatch_enumerate(self):
        result = dispatch_tool(
            "rgroup_enumerate",
            {
                "scaffold_smiles": "[*:1]c1ccccc1",
                "r_group_substitutions": {"1": ["C", "F"]},
            },
        )
        assert result["overflowed"] is False
        assert len(result["hits"]) == 2

    def test_dispatch_enumerate_overflow(self):
        subs = {"1": ["C"] * 100, "2": ["F"] * 200}
        result = dispatch_tool(
            "rgroup_enumerate",
            {
                "scaffold_smiles": "[*:1]c1ccc([*:2])cc1",
                "r_group_substitutions": subs,
                "max_enumerations": 1000,
            },
        )
        assert result["overflowed"] is True

    def test_dispatch_missing_args_defaults_gracefully(self):
        result = dispatch_tool("rdkit_canonical", {})
        assert result == {"canonical": ""}


def test_default_max_enumeration_sanity():
    assert DEFAULT_MAX_ENUMERATION == 10_000
