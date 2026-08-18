"""Clean optional-feature install contracts for configured runtime capabilities."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

FEATURE_IMPORTS = {
    "drawings": {
        "Pillow": "PIL",
        "opencv-python-headless": "cv2",
        "pypdfium2": "pypdfium2",
        "scikit-image": "skimage",
    },
    "regulatory": {
        "pdfplumber": "pdfplumber",
        "xlrd": "xlrd",
    },
}


def _declared_distribution_names(extra: str) -> set[str]:
    payload = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = [
        *payload["project"]["dependencies"],
        *payload["project"]["optional-dependencies"][extra],
    ]
    return {
        requirement.split("<", 1)[0].split(">", 1)[0].split("=", 1)[0].strip()
        for requirement in requirements
    }


@pytest.mark.parametrize("extra", sorted(FEATURE_IMPORTS))
def test_configured_feature_dependencies_are_declared(extra: str):
    assert set(FEATURE_IMPORTS[extra]) <= _declared_distribution_names(extra)


@pytest.mark.parametrize(
    ("extra", "module_name"),
    [
        (extra, module_name)
        for extra, distributions in FEATURE_IMPORTS.items()
        for module_name in distributions.values()
    ],
)
def test_clean_feature_install_import_smoke(extra: str, module_name: str):
    """CI installs both extras before this import smoke executes."""
    imported = pytest.importorskip(
        module_name,
        reason=f"{extra} optional feature is not installed in this test environment",
    )
    assert imported is not None, f"{extra} extra did not make {module_name} importable"
