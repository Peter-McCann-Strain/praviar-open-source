"""Tests for the Doc2SAR Pydantic models (Phase B5 preparation).

Pins the schema for `SubstituentTableRow` and `Doc2SARResult` so downstream
consumers (worker, ensemble wiring, report renderer) don't have to guess the
shape. Tests only the pure data models — worker + integration come later.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from praviar_pipeline.models.drawing import Doc2SARResult, SubstituentTableRow


class TestSubstituentTableRow:
    def test_minimal(self):
        row = SubstituentTableRow(row_index=0)
        assert row.row_index == 0
        assert row.rgroup_labels == {}
        assert row.resolved_smiles == ""
        assert row.confidence == 0.0

    def test_populated(self):
        row = SubstituentTableRow(
            row_index=3,
            rgroup_labels={"R1": "OCH3", "R2": "Cl"},
            resolved_smiles="COc1ccc(Cl)cc1",
            confidence=0.82,
        )
        assert row.rgroup_labels == {"R1": "OCH3", "R2": "Cl"}
        assert row.resolved_smiles == "COc1ccc(Cl)cc1"

    def test_extra_forbidden(self):
        with pytest.raises(ValidationError):
            SubstituentTableRow(row_index=0, bogus=1)  # type: ignore[call-arg]

    def test_roundtrip_serialisation(self):
        row = SubstituentTableRow(
            row_index=1,
            rgroup_labels={"R1": "Cl"},
            resolved_smiles="Clc1ccccc1",
            confidence=0.9,
        )
        dumped = row.model_dump()
        restored = SubstituentTableRow.model_validate(dumped)
        assert restored.row_index == 1
        assert restored.rgroup_labels == {"R1": "Cl"}


class TestDoc2SARResult:
    def test_minimal(self):
        result = Doc2SARResult(scaffold_smiles="", confidence=0.0)
        assert result.scaffold_smiles == ""
        assert result.substituent_table == []
        assert result.enumerated_species == []
        assert result.tool == "doc2sar"
        assert result.latency_ms == 0
        assert result.error == ""
        assert result.overflowed is False

    def test_happy_path(self):
        rows = [
            SubstituentTableRow(row_index=0, rgroup_labels={"R1": "F"}),
            SubstituentTableRow(row_index=1, rgroup_labels={"R1": "Cl"}),
        ]
        result = Doc2SARResult(
            scaffold_smiles="[*:1]c1ccccc1",
            substituent_table=rows,
            enumerated_species=["Fc1ccccc1", "Clc1ccccc1"],
            confidence=0.87,
            latency_ms=4200,
        )
        assert len(result.substituent_table) == 2
        assert len(result.enumerated_species) == 2
        assert not result.overflowed

    def test_overflow_path(self):
        """When the cross-product exceeds drawing_doc2sar_max_enumerations the
        worker sets overflowed=True and leaves enumerated_species empty."""
        result = Doc2SARResult(
            scaffold_smiles="[*:1]c1ccc([*:2])cc1",
            substituent_table=[
                SubstituentTableRow(row_index=i, rgroup_labels={}) for i in range(1200)
            ],
            enumerated_species=[],  # abstained
            confidence=0.0,
            overflowed=True,
            error="enumeration_overflow",
        )
        assert result.overflowed
        assert result.enumerated_species == []
        assert result.error == "enumeration_overflow"

    def test_extra_forbidden(self):
        with pytest.raises(ValidationError):
            Doc2SARResult(scaffold_smiles="", confidence=0.0, foo="bar")  # type: ignore[call-arg]

    def test_roundtrip_through_pydantic(self):
        result = Doc2SARResult(
            scaffold_smiles="[*:1]c1ccccc1",
            substituent_table=[
                SubstituentTableRow(row_index=0, rgroup_labels={"R1": "F"}, confidence=0.9)
            ],
            enumerated_species=["Fc1ccccc1"],
            confidence=0.9,
        )
        dumped = result.model_dump()
        restored = Doc2SARResult.model_validate(dumped)
        assert restored.scaffold_smiles == "[*:1]c1ccccc1"
        assert len(restored.substituent_table) == 1
        assert restored.substituent_table[0].rgroup_labels == {"R1": "F"}


class TestConfigFlagsPresent:
    """DrawingPipelineSettingsMixin is a plain annotation-mixin (not a
    BaseModel itself). The pydantic Field defaults live in class `__dict__`
    and annotations, so we inspect those directly."""

    def test_drawing_doc2sar_enabled_flag(self):
        from praviar_pipeline.config_sections import DrawingPipelineSettingsMixin

        assert "drawing_doc2sar_enabled" in DrawingPipelineSettingsMixin.__annotations__
        field_info = DrawingPipelineSettingsMixin.__dict__["drawing_doc2sar_enabled"]
        # pydantic.Field returns a FieldInfo whose default attribute is the literal default.
        assert field_info.default is False

    def test_drawing_doc2sar_max_enumerations_default(self):
        from praviar_pipeline.config_sections import DrawingPipelineSettingsMixin

        assert "drawing_doc2sar_max_enumerations" in DrawingPipelineSettingsMixin.__annotations__
        field_info = DrawingPipelineSettingsMixin.__dict__["drawing_doc2sar_max_enumerations"]
        assert field_info.default == 500
