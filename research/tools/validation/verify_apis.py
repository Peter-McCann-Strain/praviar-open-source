#!/usr/bin/env python3
"""Quick connectivity check for all configured API keys."""
from __future__ import annotations

import asyncio
import os
import sys

# Load .env from praviar_pipeline directory
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

import httpx

PASS = "✅"
FAIL = "❌"
SKIP = "⏭"


async def check_anthropic() -> tuple[str, str]:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return FAIL, "No key set"
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            timeout=10,
        )
    if r.status_code == 200:
        models = [m["id"] for m in r.json().get("data", [])[:3]]
        return PASS, f"OK — {', '.join(models)}"
    return FAIL, f"HTTP {r.status_code}: {r.text[:100]}"


async def check_bigquery() -> tuple[str, str]:
    project = os.getenv("BIGQUERY_PROJECT_ID", "")
    if not project:
        return FAIL, "BIGQUERY_PROJECT_ID not set"
    try:
        import google.auth
        from google.cloud import bigquery

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/bigquery"]
        )
        client = bigquery.Client(project=project, credentials=creds)
        list(client.query("SELECT 1 AS ok").result())
        return PASS, f"OK — project={project}"
    except Exception as e:
        return FAIL, str(e)[:150]


async def check_epo_ops() -> tuple[str, str]:
    key = os.getenv("OPS_CONSUMER_KEY", "")
    secret = os.getenv("OPS_CONSUMER_SECRET", "")
    if not key or not secret:
        return FAIL, "OPS_CONSUMER_KEY or OPS_CONSUMER_SECRET not set"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://ops.epo.org/3.2/auth/accesstoken",
            data={"grant_type": "client_credentials"},
            auth=(key, secret),
            timeout=15,
        )
    if r.status_code == 200:
        token = r.json().get("access_token", "")[:20]
        return PASS, f"OK — token={token}..."
    return FAIL, f"HTTP {r.status_code}: {r.text[:150]}"


async def check_semantic_scholar() -> tuple[str, str]:
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    headers = {"x-api-key": key} if key else {}
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": "succinic acid biosynthesis", "limit": 1, "fields": "title"},
            headers=headers,
            timeout=15,
        )
    if r.status_code == 200:
        data = r.json().get("data", [])
        title = data[0]["title"][:50] if data else "no results"
        return PASS, f"OK — e.g. '{title}'"
    return FAIL, f"HTTP {r.status_code}: {r.text[:100]}"


async def check_openalex() -> tuple[str, str]:
    key = os.getenv("OPENALEX_API_KEY", "")
    params = {"search": "succinic acid", "per-page": 1}
    if key:
        params["api_key"] = key
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://api.openalex.org/works",
            params=params,
            timeout=15,
        )
    if r.status_code == 200:
        count = r.json().get("meta", {}).get("count", "?")
        return PASS, f"OK — {count} results found"
    return FAIL, f"HTTP {r.status_code}: {r.text[:100]}"


async def check_tavily() -> tuple[str, str]:
    key = os.getenv("TAVILY_API_KEY", "")
    if not key:
        return FAIL, "No key set"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": key, "query": "succinic acid CPC code", "max_results": 1},
            timeout=15,
        )
    if r.status_code == 200:
        results = r.json().get("results", [])
        url = results[0]["url"][:60] if results else "no results"
        return PASS, f"OK — e.g. {url}"
    return FAIL, f"HTTP {r.status_code}: {r.text[:100]}"


async def check_pubchem() -> tuple[str, str]:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/succinic%20acid/JSON",
            timeout=10,
        )
    if r.status_code == 200:
        cid = r.json()["PC_Compounds"][0]["id"]["id"]["cid"]
        return PASS, f"OK — succinic acid CID={cid}"
    return FAIL, f"HTTP {r.status_code}"


async def check_ptab() -> tuple[str, str]:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        r = await client.get(
            "https://developer.uspto.gov/ptab-api/trials?limit=1",
            timeout=10,
        )
    if r.status_code == 200:
        return PASS, "OK — PTAB reachable"
    return FAIL, f"HTTP {r.status_code}: {r.text[:80]}"


async def main() -> None:
    print("\nVerifying API connectivity...\n")

    checks = [
        ("Anthropic (Claude)", check_anthropic()),
        ("BigQuery (GCP)", check_bigquery()),
        ("EPO OPS", check_epo_ops()),
        ("Semantic Scholar", check_semantic_scholar()),
        ("OpenAlex", check_openalex()),
        ("Tavily", check_tavily()),
        ("PubChem", check_pubchem()),
        ("PTAB", check_ptab()),
    ]

    results = await asyncio.gather(*[c for _, c in checks], return_exceptions=True)

    max_name = max(len(n) for n, _ in checks)
    for (name, _), result in zip(checks, results):
        if isinstance(result, Exception):
            icon, msg = FAIL, str(result)[:120]
        else:
            icon, msg = result
        print(f"  {icon}  {name:<{max_name}}  {msg}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
