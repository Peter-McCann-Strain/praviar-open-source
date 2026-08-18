"""Spreadsheet output safety shared by CSV and XLSX renderers."""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

FORMULA_PREFIXES = ("=", "+", "-", "@")
_XML_ALLOWED_CONTROLS = {"\t", "\n", "\r"}


def _replace_illegal_controls(value: str) -> str:
    return "".join(
        character
        if unicodedata.category(character) != "Cc" or character in _XML_ALLOWED_CONTROLS
        else "\N{REPLACEMENT CHARACTER}"
        for character in value
    )


def _formula_probe(value: str) -> str:
    """Remove leading whitespace/control markers used to hide formulas."""
    index = 0
    while index < len(value):
        character = value[index]
        category = unicodedata.category(character)
        if character.isspace() or category in {"Cc", "Cf"}:
            index += 1
            continue
        break
    return value[index:]


def neutralize_spreadsheet_value(value: Any) -> Any:
    """Prefix potentially executable string cells with a literal marker."""
    if not isinstance(value, str) or not value:
        return value
    safe_value = _replace_illegal_controls(value)
    probe = _formula_probe(safe_value)
    if probe.startswith(FORMULA_PREFIXES):
        return f"'{safe_value}"
    return safe_value


def neutralize_spreadsheet_row(values: Iterable[Any]) -> list[Any]:
    """Neutralize every cell in one CSV/XLSX row."""
    return [neutralize_spreadsheet_value(value) for value in values]


def neutralize_workbook_strings(workbook: Any) -> None:
    """Apply the cell policy to every populated string in an openpyxl workbook."""
    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    cell.value = neutralize_spreadsheet_value(cell.value)


def neutralize_spreadsheet_structure(value: Any) -> Any:
    """Recursively neutralize strings before an XLSX library binds cells."""
    if isinstance(value, str):
        return neutralize_spreadsheet_value(value)
    if isinstance(value, dict):
        return {key: neutralize_spreadsheet_structure(item) for key, item in value.items()}
    if isinstance(value, list):
        return [neutralize_spreadsheet_structure(item) for item in value]
    if isinstance(value, tuple):
        return tuple(neutralize_spreadsheet_structure(item) for item in value)
    return value
