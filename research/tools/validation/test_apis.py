"""Smoke test all external APIs with a known compound (succinic acid).

Run this first to verify which APIs are accessible before building the pipeline.

Usage:
    python research/tools/validation/test_apis.py
"""

from __future__ import annotations

import asyncio
import os

# Ensure the praviar_pipeline package is importable
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "praviar_pipeline" / "src"))

if "pytest" in sys.modules:
    import pytest

    pytest.importorskip(
        "pytest_asyncio",
        reason="live async API smoke tests require pytest-asyncio",
    )
    pytestmark = pytest.mark.skipif(
        os.environ.get("RUN_LIVE_API_SMOKE_TESTS") != "true",
        reason="live external API smoke tests require RUN_LIVE_API_SMOKE_TESTS=true",
    )


async def smoke_pubchem():
    """Test PubChem PUG REST API."""
    from praviar_pipeline.clients.pubchem import PubChemClient

    client = PubChemClient()
    try:
        start = time.time()
        props = await client.resolve_by_name("succinic acid")
        elapsed = time.time() - start

        if props and "CID" in props:
            cid = props["CID"]
            smiles = props.get("CanonicalSMILES") or props.get("ConnectivitySMILES", "N/A")
            print(f"  PubChem resolve: CID={cid}, SMILES={smiles}")
            print(f"  Response time: {elapsed:.2f}s")

            # Test patent links
            patents = await client.get_patent_links(cid)
            print(f"  Patent links: {len(patents)} patents found")
            if patents:
                print(f"  Sample: {patents[:3]}")

            # Test synonyms
            synonyms = await client.get_synonyms(cid)
            print(f"  Synonyms: {len(synonyms)} found")

            return True
        else:
            print("  FAILED: No CID returned")
            return False
    except Exception as e:
        print(f"  FAILED: {e}")
        return False
    finally:
        await client.close()


async def smoke_surechembl():
    """Test SureChEMBL REST API."""
    from praviar_pipeline.clients.surechembl import SureChEMBLClient

    client = SureChEMBLClient()
    try:
        start = time.time()
        # Succinic acid SMILES
        results = await client.search_by_smiles("OC(=O)CCC(O)=O")
        elapsed = time.time() - start

        print(f"  SureChEMBL exact search: {len(results)} results")
        print(f"  Response time: {elapsed:.2f}s")
        if results:
            print(f"  Sample: {results[0]}")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False
    finally:
        await client.close()


async def smoke_ptab():
    """Test USPTO PTAB API."""
    from praviar_pipeline.clients.ptab import PTABClient

    client = PTABClient()
    try:
        start = time.time()
        # US6,265,190 — known succinic acid patent
        proceedings = await client.get_proceedings("6265190")
        elapsed = time.time() - start

        print(f"  PTAB search for US6265190: {len(proceedings)} proceedings")
        print(f"  Response time: {elapsed:.2f}s")
        if proceedings:
            p = proceedings[0]
            print(
                f"  Sample: {p.get('proceedingNumber', 'N/A')} - {p.get('proceedingStatus', 'N/A')}"
            )
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False
    finally:
        await client.close()


async def smoke_bigquery():
    """Test Google BigQuery (requires credentials)."""
    from praviar_pipeline.config import get_settings

    settings = get_settings()
    if not settings.bigquery_project_id or settings.bigquery_project_id == "your-gcp-project-id":
        print("  SKIPPED: BigQuery project ID not configured")
        return None

    from praviar_pipeline.clients.bigquery import BigQueryClient

    client = BigQueryClient()
    try:
        start = time.time()
        results = await client.search_patents_by_compound(
            ["succinic acid"],
            max_results=5,
        )
        elapsed = time.time() - start

        print(f"  BigQuery search: {len(results)} patents")
        print(f"  Response time: {elapsed:.2f}s")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False
    finally:
        await client.close()


async def smoke_claude():
    """Test Claude API with a simple structured output call."""
    from pydantic import BaseModel

    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.config import get_settings

    settings = get_settings()
    if not settings.anthropic_api_key:
        print("  SKIPPED: Anthropic API key not configured")
        return None

    class TestOutput(BaseModel):
        compound_name: str
        is_organic: bool
        molecular_formula: str

    client = ClaudeClient()
    try:
        start = time.time()
        result, usage = await client.complete(
            system="You are a chemistry assistant.",
            user="What is succinic acid? Return the compound name, whether it's organic, and its molecular formula.",
            response_model=TestOutput,
            max_tokens=256,
        )
        elapsed = time.time() - start

        print(f"  Claude structured output: {result.compound_name}, organic={result.is_organic}")
        print(f"  Formula: {result.molecular_formula}")
        print(f"  Tokens: {usage['input_tokens']} in, {usage['output_tokens']} out")
        print(f"  Response time: {elapsed:.2f}s")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False
    finally:
        await client.close()


async def smoke_rdkit():
    """Test RDKit local library."""
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem, MACCSkeys

        mol = Chem.MolFromSmiles("OC(=O)CCC(O)=O")
        if mol is None:
            print("  FAILED: Could not parse succinic acid SMILES")
            return False

        # Morgan fingerprint
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
        on_bits = fp.GetNumOnBits()

        # MACCS keys
        maccs = MACCSkeys.GenMACCSKeys(mol)

        # Canonical SMILES
        canonical = Chem.MolToSmiles(mol)

        print(f"  RDKit SMILES: {canonical}")
        print(f"  Morgan FP: 2048 bits, {on_bits} on-bits")
        print(f"  MACCS keys: {maccs.GetNumOnBits()} on-bits")
        return True
    except ImportError:
        print("  FAILED: RDKit not installed")
        return False
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def smoke_patcid():
    """Test PatCID local index."""
    from praviar_pipeline.clients.patcid import PatCIDClient

    client = PatCIDClient()
    try:
        # Succinic acid InChIKey
        results = await client.lookup_by_inchikey("KDYFGRWQOYBRFD-UHFFFAOYSA-N")
        if results:
            print(f"  PatCID lookup: {len(results)} patents found")
            print(f"  Sample: {results[:3]}")
        else:
            print("  PatCID: No results (database may not be indexed yet)")
        return True
    except Exception as e:
        print(f"  SKIPPED: {e}")
        return None
    finally:
        await client.close()


async def main():
    print("=" * 60)
    print("Praviar Pipeline API Smoke Tests")
    print("=" * 60)

    tests = [
        ("PubChem PUG REST", smoke_pubchem),
        ("RDKit (local)", smoke_rdkit),
        ("SureChEMBL REST", smoke_surechembl),
        ("USPTO PTAB v3", smoke_ptab),
        ("PatCID (local)", smoke_patcid),
        ("Google BigQuery", smoke_bigquery),
        ("Claude API", smoke_claude),
    ]

    results = {}
    for name, test_fn in tests:
        print(f"\n--- {name} ---")
        result = await test_fn()
        results[name] = result

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, result in results.items():
        if result is True:
            status = "PASS"
        elif result is False:
            status = "FAIL"
        else:
            status = "SKIP"
        print(f"  {status:4s}  {name}")

    passed = sum(1 for r in results.values() if r is True)
    failed = sum(1 for r in results.values() if r is False)
    skipped = sum(1 for r in results.values() if r is None)
    print(f"\n  {passed} passed, {failed} failed, {skipped} skipped")


if "pytest" in sys.modules:

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("name", "smoke_fn"),
        [
            ("PubChem PUG REST", smoke_pubchem),
            ("RDKit (local)", smoke_rdkit),
            ("SureChEMBL REST", smoke_surechembl),
            ("USPTO PTAB v3", smoke_ptab),
            ("PatCID (local)", smoke_patcid),
            ("Google BigQuery", smoke_bigquery),
            ("Claude API", smoke_claude),
        ],
    )
    async def test_live_external_api_smoke(name, smoke_fn):
        result = await smoke_fn()
        if result is None:
            pytest.skip(f"{name} is not configured in this environment")
        assert result is True


if __name__ == "__main__":
    asyncio.run(main())
