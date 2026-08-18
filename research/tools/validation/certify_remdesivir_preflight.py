"""Strict live-source preflight for the Remdesivir certification run.

This command is intentionally stricter than the general API smoke tests:
every active required source must pass, BigQuery file caching is disabled,
response-cache replay/dry-run modes are rejected, and Lens must be absent
from active runtime scheduling rather than reported as skipped.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_SRC = REPO_ROOT / "praviar_pipeline" / "src"
if str(PIPELINE_SRC) not in sys.path:
    sys.path.insert(0, str(PIPELINE_SRC))

# Certification must prove live BigQuery access. Set this before importing
# settings so the process cannot accidentally pass on cached BigQuery rows.
os.environ["BIGQUERY_CACHE_ENABLED"] = "false"

REM_DESIVIR_NAME = "remdesivir"
REM_DESIVIR_SYNONYMS = ["remdesivir", "GS-5734"]
KNOWN_REMDESIVIR_US_PATENT = "US9724360B2"


class CheckFailed(RuntimeError):
    """A certification check failed in a user-actionable way."""


@dataclass(slots=True)
class CertificationContext:
    settings: Any
    pubchem_props: dict[str, Any] = field(default_factory=dict)
    pubchem_synonyms: list[str] = field(default_factory=list)
    pubchem_patents: list[str] = field(default_factory=list)
    bigquery_patent_id: str = ""


@dataclass(slots=True)
class CheckResult:
    name: str
    status: str
    detail: str
    elapsed_s: float


async def _run_check(
    name: str,
    check: Callable[[CertificationContext], Awaitable[str]],
    ctx: CertificationContext,
) -> CheckResult:
    start = time.monotonic()
    try:
        detail = await check(ctx)
    except Exception as exc:  # noqa: BLE001 - certification reports all failures uniformly.
        detail = f"{type(exc).__name__}: {exc}"
        return CheckResult(name=name, status="FAIL", detail=detail, elapsed_s=time.monotonic() - start)
    return CheckResult(name=name, status="PASS", detail=detail, elapsed_s=time.monotonic() - start)


def _require(value: Any, message: str) -> None:
    if not value:
        raise CheckFailed(message)


def _require_setting(settings: Any, attr: str, env_name: str) -> str:
    value = str(getattr(settings, attr, "") or "")
    if not value:
        raise CheckFailed(f"{env_name} is required for certification")
    return value


def _count_payload(value: Any) -> int:
    if isinstance(value, list | tuple | set | dict):
        return len(value)
    return 1 if value else 0


def _patent_ids_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        candidate = (
            row.get("publication_number")
            or row.get("publicationNumber")
            or row.get("patent_id")
            or row.get("patentId")
            or ""
        )
        if not candidate:
            continue
        patent_id = str(candidate)
        if patent_id not in seen:
            ids.append(patent_id)
            seen.add(patent_id)
    return ids


async def check_runtime_guards(ctx: CertificationContext) -> str:
    settings = ctx.settings
    truthy = {"1", "true", "yes", "on"}
    forbidden_truthy = [
        "NEXT_PUBLIC_DEMO_MODE",
        "NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS",
        "ALLOW_DEV_AUTH_BYPASS",
        "PRAVIAR_DRY_RUN",
    ]
    for env_name in forbidden_truthy:
        if os.environ.get(env_name, "").strip().lower() in truthy:
            raise CheckFailed(f"{env_name} must be false/unset for certification")

    if os.environ.get("APP_ENV", "").strip().lower() == "test":
        raise CheckFailed("APP_ENV=test is not allowed for a live certification preflight")

    cache_modes = {
        os.environ.get("RESPONSE_CACHE_MODE", ""),
        os.environ.get("PRAVIAR_RESPONSE_CACHE_MODE", ""),
    }
    blocked_modes = {"replay", "replay_then_record", "dry_run"}
    enabled_blocked = sorted(mode for mode in cache_modes if mode.strip().lower() in blocked_modes)
    if enabled_blocked:
        raise CheckFailed(f"response-cache mode is blocked for certification: {enabled_blocked}")

    if getattr(settings, "source_failure_policy", "") == "best_effort":
        raise CheckFailed("SOURCE_FAILURE_POLICY=best_effort is not allowed for certification")
    if settings.bigquery_cache_enabled:
        raise CheckFailed("BIGQUERY_CACHE_ENABLED must be false during certification")

    from praviar_pipeline.response_cache import CacheMode, get_current_cache, get_dry_run_provider

    cache = get_current_cache()
    if cache is not None and cache.mode != CacheMode.DISABLED:
        raise CheckFailed(f"active response cache is {cache.mode}, expected disabled")
    if get_dry_run_provider() is not None:
        raise CheckFailed("dry-run provider is installed")

    return (
        "demo/dev-auth/dry-run/replay disabled; "
        f"source_failure_policy={settings.source_failure_policy}; BigQuery cache=false"
    )


async def check_lens_absent(ctx: CertificationContext) -> str:
    from types import SimpleNamespace

    from praviar_pipeline.pipeline.invalidity import scholarly
    from praviar_pipeline.pipeline.search.plan import build_search_plan
    from praviar_pipeline.pipeline.search.source_registry import SOURCE_CAPABILITIES

    if "lens" in SOURCE_CAPABILITIES:
        raise CheckFailed("Lens is still registered as an active search capability")
    if hasattr(scholarly, "_search_lens_scholarly_by_patent"):
        raise CheckFailed("Lens scholarly search is still scheduled by invalidity runtime")

    async def empty(*_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    settings = SimpleNamespace(
        search_enable_pubchem=True,
        search_enable_surechembl=True,
        search_enable_bigquery=True,
        search_enable_patcid=True,
        search_allowed_jurisdictions=["US", "EP", "WO", "KR", "JP"],
        ops_consumer_key="ops-key",
        ops_consumer_secret="ops-secret",
        kipris_api_key="kipris-key",
        patentscope_username="wipo-user",
        patentscope_password="wipo-pass",
        patentsview_api_key="pv-key",
    )
    compound = SimpleNamespace(name=REM_DESIVIR_NAME, synonyms=[], pubchem_cid=0)
    plan = build_search_plan(
        compound=compound,
        expanded_queries=SimpleNamespace(cpc_codes=["A61K"], key_assignees=["Gilead"], process_keywords=[]),
        has_expansion=True,
        settings=settings,
        search_pubchem_sdq=empty,
        search_surechembl=empty,
        search_bigquery=empty,
        search_bigquery_annotations=empty,
        search_patcid=empty,
        search_pubchem_similar=empty,
        search_bigquery_cpc=empty,
        search_bigquery_assignee=empty,
        search_epo_claims=empty,
        search_kipris=empty,
        search_patentscope=empty,
        search_bigquery_translated=empty,
        search_patentsview=empty,
    )
    try:
        scheduled = [source for source, _coro in plan]
        planned = [entry.source for entry in plan.planned_entries]
        if "lens" in scheduled or "lens" in planned:
            raise CheckFailed(f"Lens appeared in active plan: scheduled={scheduled}, planned={planned}")
    finally:
        for _source, coro in plan:
            coro.close()

    return "Lens absent from source registry, Step 2 plan, and invalidity scholarly scheduling"


async def check_anthropic(ctx: CertificationContext) -> str:
    import httpx
    from pydantic import BaseModel

    from praviar_pipeline.clients.claude import ClaudeClient

    key = _require_setting(ctx.settings, "anthropic_api_key", "ANTHROPIC_API_KEY")
    async with httpx.AsyncClient(timeout=20) as http:
        response = await http.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        )
        response.raise_for_status()
        models = response.json().get("data", [])
    _require(models, "Anthropic model list returned no models")

    class Probe(BaseModel):
        compound: str
        certification_ready: bool

    async with ClaudeClient() as client:
        result, usage = await client.complete(
            system="Return only the requested structured fields.",
            user="For a live preflight, identify Remdesivir and mark certification_ready true.",
            response_model=Probe,
            max_tokens=128,
            role="certification_preflight",
        )
    _require(result.certification_ready, "Claude structured-output probe returned false")
    return (
        f"models={len(models)}; structured_output={result.compound}; "
        f"tokens={usage.get('input_tokens', 0)}/{usage.get('output_tokens', 0)}"
    )


async def check_pubchem(ctx: CertificationContext) -> str:
    from praviar_pipeline.clients.pubchem import PubChemClient

    async with PubChemClient() as client:
        props = await client.resolve_by_name(REM_DESIVIR_NAME)
        cid = props.get("CID")
        _require(cid, "PubChem did not resolve Remdesivir to a CID")
        synonyms = await client.get_synonyms(int(cid))
        patents = await client.get_patent_links(int(cid))

    _require(synonyms, "PubChem synonyms lookup returned no rows")
    _require(patents, "PubChem patent-link lookup returned no rows")
    ctx.pubchem_props = props
    ctx.pubchem_synonyms = synonyms
    ctx.pubchem_patents = patents
    return f"CID={cid}; synonyms={len(synonyms)}; patent_links={len(patents)}"


async def check_bigquery(ctx: CertificationContext) -> str:
    from google.cloud import bigquery

    from praviar_pipeline.clients.bigquery import BigQueryClient

    _require_setting(ctx.settings, "bigquery_project_id", "BIGQUERY_PROJECT_ID")
    synonyms = [ctx.pubchem_props.get("IUPACName", ""), *REM_DESIVIR_SYNONYMS]
    synonyms = [value for value in synonyms if value]
    inchikey = str(ctx.pubchem_props.get("InChIKey", "") or "")
    candidates: list[str] = []

    async with BigQueryClient() as client:
        def select_one() -> list[dict[str, Any]]:
            job_config = bigquery.QueryJobConfig(
                maximum_bytes_billed=ctx.settings.bigquery_max_bytes_billed
            )
            rows = client.get_client().query_and_wait("SELECT 1 AS ok", job_config=job_config)
            return [dict(row) for row in rows]

        select_rows = await asyncio.to_thread(select_one)
        _require(select_rows and select_rows[0].get("ok") == 1, "BigQuery SELECT 1 failed")

        compound_rows = await client.search_patents_by_compound(
            synonyms,
            max_results=10,
            jurisdictions=["US", "EP", "WO"],
        )
        _require(compound_rows, "BigQuery compound search returned no rows")
        candidates.extend(_patent_ids_from_rows(compound_rows))

        annotation_rows = await client.search_compound_annotations(
            REM_DESIVIR_NAME,
            inchikey=inchikey,
            max_results=10,
        )
        _require(annotation_rows, "BigQuery annotation lookup returned no rows")
        candidates.extend(_patent_ids_from_rows(annotation_rows))

        cpc_rows = await client.search_by_cpc_and_keywords(
            ["A61K"],
            REM_DESIVIR_SYNONYMS,
            max_results=10,
            jurisdictions=["US", "EP", "WO"],
        )
        _require(cpc_rows, "BigQuery CPC/keyword search returned no rows")
        candidates.extend(_patent_ids_from_rows(cpc_rows))

        assignee_rows = await client.search_by_assignee(
            ["Gilead"],
            max_results=10,
            jurisdictions=["US", "EP", "WO"],
        )
        _require(assignee_rows, "BigQuery assignee search returned no rows")
        candidates.extend(_patent_ids_from_rows(assignee_rows))

        unique_candidates = list(dict.fromkeys(candidates))
        _require(unique_candidates, "BigQuery searches produced no patent IDs for lookup probes")

        lookup_id = ""
        claims_text = ""
        metadata: list[dict[str, Any]] = []
        citations: dict[str, dict[str, list[str]]] = {}
        full_text = ""
        for patent_id in unique_candidates[:10]:
            claims = await client.get_patent_claims_batch([patent_id])
            metadata_rows = await client.get_patent_metadata_batch([patent_id])
            citation_rows = await client.get_examiner_citations_batch([patent_id])
            description = await client.get_patent_full_text(patent_id)
            if claims.get(patent_id) and metadata_rows and description:
                lookup_id = patent_id
                claims_text = claims[patent_id]
                metadata = metadata_rows
                citations = citation_rows
                full_text = description
                break

    _require(lookup_id, "BigQuery claims/metadata/full-text probes found no complete patent row")
    ctx.bigquery_patent_id = lookup_id
    return (
        f"compound={len(compound_rows)}; annotations={len(annotation_rows)}; "
        f"cpc={len(cpc_rows)}; assignee={len(assignee_rows)}; "
        f"lookup={lookup_id}; claims_chars={len(claims_text)}; "
        f"metadata={len(metadata)}; citations={_count_payload(citations)}; "
        f"full_text_chars={len(full_text)}"
    )


async def check_surechembl(ctx: CertificationContext) -> str:
    from praviar_pipeline.clients.surechembl import SureChEMBLClient

    smiles = str(
        ctx.pubchem_props.get("CanonicalSMILES")
        or ctx.pubchem_props.get("ConnectivitySMILES")
        or ""
    )
    _require(smiles, "PubChem did not provide a SMILES string for SureChEMBL")
    async with SureChEMBLClient() as client:
        exact = await client.search_by_smiles(smiles, max_results=10)
        similar = await client.similarity_search(smiles, threshold=0.7)
        substructure = await client.substructure_search(smiles, max_results=10)
    _require(
        exact or similar or substructure,
        "SureChEMBL exact/similarity/substructure probes all returned zero rows",
    )
    return f"exact={len(exact)}; similarity={len(similar)}; substructure={len(substructure)}"


async def check_patcid(ctx: CertificationContext) -> str:
    from praviar_pipeline.clients.patcid import DEFAULT_DB_PATH, PatCIDClient

    inchikey = str(ctx.pubchem_props.get("InChIKey", "") or "")
    _require(inchikey, "PubChem did not provide an InChIKey for PatCID")
    if not DEFAULT_DB_PATH.is_file():
        raise CheckFailed(f"PatCID index is missing at {DEFAULT_DB_PATH}")
    async with PatCIDClient() as client:
        patents = await client.lookup_by_inchikey(inchikey)
    return f"index={DEFAULT_DB_PATH}; rows={len(patents)}"


async def check_epo_ops(ctx: CertificationContext) -> str:
    from praviar_pipeline.clients.epo_ops import EPOOPSClient

    _require_setting(ctx.settings, "ops_consumer_key", "OPS_CONSUMER_KEY")
    _require_setting(ctx.settings, "ops_consumer_secret", "OPS_CONSUMER_SECRET")
    async with EPOOPSClient() as client:
        token = await client._ensure_token()
        _require(token, "EPO OPS OAuth returned an empty token")
        rows = await client.search_published_data(
            claim_keywords=REM_DESIVIR_SYNONYMS,
            applicants=["Gilead"],
            max_results=5,
        )
        _require(rows, "EPO OPS published-data search returned no rows")
        patent_ids = _patent_ids_from_rows(rows)
        _require(patent_ids, "EPO OPS search rows did not include publication numbers")
        claims = ""
        selected = ""
        for patent_id in patent_ids:
            claims = await client.get_claims_text(patent_id)
            if claims:
                selected = patent_id
                break
    _require(selected, "EPO OPS claim lookup returned no claim text for returned patents")
    return f"token_ok=true; search_rows={len(rows)}; claims_patent={selected}; claims_chars={len(claims)}"


async def check_kipris(ctx: CertificationContext) -> str:
    from praviar_pipeline.clients.kipris import KIPRISClient

    _require_setting(ctx.settings, "kipris_api_key", "KIPRIS_API_KEY")
    async with KIPRISClient() as client:
        rows = await client.search_patents(REM_DESIVIR_SYNONYMS, max_results=5)
    _require(rows, "KIPRIS Remdesivir query returned no rows")
    return f"rows={len(rows)}"


async def check_patentscope(ctx: CertificationContext) -> str:
    from praviar_pipeline.clients.patentscope import PatentScopeClient

    _require_setting(ctx.settings, "patentscope_username", "PATENTSCOPE_USERNAME")
    _require_setting(ctx.settings, "patentscope_password", "PATENTSCOPE_PASSWORD")
    async with PatentScopeClient() as client:
        rows = await client.search_patents(REM_DESIVIR_SYNONYMS, jurisdictions=["WO"], max_results=5)
    _require(rows, "PatentScope Remdesivir query returned no rows")
    return f"rows={len(rows)}"


async def check_patentsview(ctx: CertificationContext) -> str:
    from praviar_pipeline.clients.patentsview import PatentsViewClient

    _require_setting(ctx.settings, "patentsview_api_key", "PATENTSVIEW_API_KEY")
    async with PatentsViewClient() as client:
        rows = await client.search_by_compound_keywords(
            REM_DESIVIR_NAME,
            synonyms=REM_DESIVIR_SYNONYMS,
            size=5,
        )
    _require(rows, "PatentsView Remdesivir query returned no rows")
    return f"rows={len(rows)}"


async def check_uspto_and_ptab(ctx: CertificationContext) -> str:
    from praviar_pipeline.clients.ptab import PTABClient
    from praviar_pipeline.clients.uspto_odp import USPTOODPClient

    _require_setting(ctx.settings, "uspto_odp_api_key", "USPTO_ODP_API_KEY")
    patent_number = ctx.bigquery_patent_id or KNOWN_REMDESIVIR_US_PATENT
    async with USPTOODPClient() as odp:
        search = await odp.search_patents(REM_DESIVIR_NAME, limit=5)
        _require(search, "USPTO ODP Remdesivir search returned no payload")
        application = await odp.get_application_data(patent_number)
        _require(application, f"USPTO ODP application lookup returned no data for {patent_number}")
    async with PTABClient() as ptab:
        proceedings = await ptab.get_proceedings(patent_number)
    return (
        f"odp_search_keys={len(search)}; application_patent={patent_number}; "
        f"ptab_proceedings={len(proceedings)}"
    )


async def check_literature_sources(ctx: CertificationContext) -> str:
    from praviar_pipeline.clients.openalex import OpenAlexClient
    from praviar_pipeline.clients.pubmed import PubMedClient
    from praviar_pipeline.clients.semantic_scholar import SemanticScholarClient

    async with SemanticScholarClient() as semantic_scholar:
        semantic_rows = await semantic_scholar.search_papers(
            '"remdesivir"',
            fields_of_study=["Chemistry", "Biology"],
            max_results=5,
        )
    _require(semantic_rows, "Semantic Scholar Remdesivir query returned no rows")

    async with OpenAlexClient() as openalex:
        openalex_rows = await openalex.search_works('"remdesivir"', max_results=5)
    _require(openalex_rows, "OpenAlex Remdesivir query returned no rows")

    async with PubMedClient() as pubmed:
        pubmed_rows = await pubmed.search_compound_literature(
            REM_DESIVIR_NAME,
            synonyms=REM_DESIVIR_SYNONYMS,
            max_results=5,
        )
    _require(pubmed_rows, "PubMed/NCBI Remdesivir query returned no rows")
    return (
        f"semantic_scholar={len(semantic_rows)}; "
        f"openalex={len(openalex_rows)}; pubmed={len(pubmed_rows)}"
    )


async def check_tavily(ctx: CertificationContext) -> str:
    from praviar_pipeline.clients.tavily import TavilyClient

    _require_setting(ctx.settings, "tavily_api_key", "TAVILY_API_KEY")
    async with TavilyClient(required=True) as client:
        rows = await client.search(
            "Remdesivir Gilead patent CPC A61K",
            max_results=3,
            required=True,
        )
    _require(rows, "Tavily grounding query returned no rows")
    return f"rows={len(rows)}"


def _load_settings() -> Any:
    from praviar_pipeline.config import get_settings

    get_settings.cache_clear()
    return get_settings()


async def run_certification(*, json_output: bool = False) -> int:
    checks: list[tuple[str, Callable[[CertificationContext], Awaitable[str]]]] = [
        ("runtime guards", check_runtime_guards),
        ("Lens absent from active runtime", check_lens_absent),
        ("Anthropic live structured output", check_anthropic),
        ("PubChem Remdesivir", check_pubchem),
        ("BigQuery uncached Remdesivir", check_bigquery),
        ("SureChEMBL Remdesivir", check_surechembl),
        ("PatCID local index", check_patcid),
        ("EPO OPS OAuth and claims", check_epo_ops),
        ("KIPRIS bounded query", check_kipris),
        ("PatentScope bounded query", check_patentscope),
        ("PatentsView bounded query", check_patentsview),
        ("USPTO ODP and PTAB", check_uspto_and_ptab),
        ("Semantic Scholar/OpenAlex/PubMed", check_literature_sources),
        ("Tavily grounding", check_tavily),
    ]
    try:
        ctx = CertificationContext(settings=_load_settings())
    except Exception as exc:  # noqa: BLE001 - settings failures are certification failures.
        result = CheckResult(
            name="settings load",
            status="FAIL",
            detail=f"{type(exc).__name__}: {exc}",
            elapsed_s=0.0,
        )
        if json_output:
            import json

            print(
                json.dumps(
                    {
                        "compound": REM_DESIVIR_NAME,
                        "status": "FAIL",
                        "lens_policy": "absent",
                        "bigquery_cache_enabled": False,
                        "results": [asdict(result)],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"{result.status:4s}  {result.name:<38s} {result.elapsed_s:6.2f}s  {result.detail}")
            print("\nCertification preflight failed: settings could not be loaded.")
        return 1

    results: list[CheckResult] = []

    for name, check in checks:
        result = await _run_check(name, check, ctx)
        results.append(result)
        if not json_output:
            print(
                f"{result.status:4s}  {result.name:<38s} "
                f"{result.elapsed_s:6.2f}s  {result.detail}"
            )

    failures = [result for result in results if result.status != "PASS"]
    if json_output:
        import json

        print(
            json.dumps(
                {
                    "compound": REM_DESIVIR_NAME,
                    "status": "FAIL" if failures else "PASS",
                    "lens_policy": "absent",
                    "bigquery_cache_enabled": False,
                    "results": [asdict(result) for result in results],
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif failures:
        print(f"\nCertification preflight failed: {len(failures)} required check(s) failed.")
    else:
        print("\nCertification preflight passed: all active sources passed and Lens is absent.")

    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="certify-remdesivir-preflight")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


async def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return await run_certification(json_output=args.json)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
