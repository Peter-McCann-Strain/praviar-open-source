"""Zero-spend dry-run harness for the Praviar Pipeline pipeline.

This module installs a context-managed harness that replaces every external
call boundary with a canned response provider. The goal is to smoke-test
**pipeline orchestration** — does the runtime actually run end-to-end without
crashing? — without touching the real Anthropic, PubChem, BigQuery, EPO, Lens,
SureChEMBL, etc. APIs.

Design
------
Two interception points carry the entire surface:

1. **The response cache.** Every cache-aware client (Claude LLM and every
   HTTP client that opts in via :func:`response_cache.get_current_cache`)
   funnels into ``ResponseCache.wrap(source=..., method=..., url=...,
   body=..., call=...)``. We add a new :class:`CacheMode.DRY_RUN` mode that
   short-circuits ``call()`` and dispatches to a registered
   :class:`DryRunProvider` keyed on ``source``.

2. **Direct httpx paths.** A handful of methods (notably
   :meth:`PubChemClient.similarity_search` and :func:`poll_list_key`) hit
   ``httpx`` directly instead of routing through the cache. The harness
   monkey-patches these on enter and restores them on exit.

The Claude side is fully covered by (1): the LLM cache wraps every
``complete`` / ``complete_text`` / ``complete_with_thinking`` call and tags
the source as ``claude:<role>``. Our provider parses the cache body to learn
the ``kind`` (which completion family) and ``response_model`` (class path)
and synthesises an envelope that mirrors what the live cache would return.

What this is not
----------------
This is not a guarantee that the pipeline produces *useful* output — the
canned data is intentionally minimal. It is a contract that the orchestration
layer (config wiring, step plumbing, model construction, verification, report
serialisation) does not crash on a happy-path single-compound run.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import unquote

from pydantic import BaseModel

from praviar_pipeline.clients.claude_response_cache import (
    LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
)
from praviar_pipeline.response_cache import (
    CacheMode,
    ResponseCache,
    set_current_cache,
    set_dry_run_provider,
)
from praviar_pipeline.showcase_fixture import (
    load_showcase_fixture,
    showcase_fixture_receipt,
    showcase_publication_id,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DryRunError(Exception):
    """Base class for dry-run harness failures."""


class DryRunAssertionError(DryRunError):
    """Raised when a post-pipeline invariant fails in dry-run mode.

    The failing field path is exposed so the caller can print a focused
    diagnostic instead of wading through the full report.
    """

    def __init__(self, field_path: str, detail: str) -> None:
        self.field_path = field_path
        self.detail = detail
        super().__init__(f"DryRun assertion failed: {field_path}: {detail}")


# ---------------------------------------------------------------------------
# Canned data shapes — the minimum viable downstream input per source
# ---------------------------------------------------------------------------


_SHOWCASE = load_showcase_fixture()
_SHOWCASE_PAYLOAD = _SHOWCASE["payload"]
_SHOWCASE_ANALYSIS = _SHOWCASE_PAYLOAD["analysis"]
_SHOWCASE_COMPOUND = _SHOWCASE_PAYLOAD["compound"]
_SHOWCASE_FAMILY = _SHOWCASE_ANALYSIS["families"][0]
SHOWCASE_DRY_RUN_INPUT = str(_SHOWCASE_COMPOUND["submitted_identity"])
_CANNED_PATENT_ID = showcase_publication_id()
_SHOWCASE_SYNTHETIC_CID = 900_000_042
_SHOWCASE_COMPOUND_FIXTURE: dict[str, Any] = {
    "CID": _SHOWCASE_SYNTHETIC_CID,
    "IUPACName": str(_SHOWCASE_COMPOUND["display_name"]),
    "MolecularFormula": "*2",
    "MolecularWeight": "0",
    # Two RDKit dummy atoms provide a parser-safe orchestration token without
    # representing or redistributing any real chemical structure.
    "CanonicalSMILES": "[*:42]~[*:43]",
    "InChI": "",
    "InChIKey": "FICTIONALPVXAB-DEMOFIXTUR-N",
    "Synonym": [
        SHOWCASE_DRY_RUN_INPUT,
        str(_SHOWCASE_COMPOUND["display_name"]),
    ],
    "PatentID": [
        showcase_publication_id(index)
        for index, _family in enumerate(_SHOWCASE_ANALYSIS["families"])
    ],
    "sdq_patent": {
        "publicationnumber": _CANNED_PATENT_ID,
        "title": str(_SHOWCASE_FAMILY["title"]),
        "abstract": str(_SHOWCASE_FAMILY["claims"][0]["text"]),
        "prioritydate": str(_SHOWCASE_FAMILY["priority_date"]),
        "publicationdate": str(_SHOWCASE_FAMILY["priority_date"]),
        "classification": ["FICTIONAL-SHOWCASE"],
        "cids": [_SHOWCASE_SYNTHETIC_CID],
        "assignees": [str(_SHOWCASE_FAMILY["assignee"])],
        "familycount": 1,
    },
}
_COMPOUND_FIXTURES: dict[str, dict[str, Any]] = {
    "showcase": _SHOWCASE_COMPOUND_FIXTURE,
}
_FIXTURE_BY_CID = {str(v["CID"]): v for v in _COMPOUND_FIXTURES.values()}


def _fixture_for_token(token: str) -> dict[str, Any]:
    normalized = unquote(token).strip().lower()
    for fixture in _COMPOUND_FIXTURES.values():
        aliases = [
            str(fixture["CID"]),
            fixture["IUPACName"],
            fixture["CanonicalSMILES"],
            fixture["InChIKey"],
            *fixture["Synonym"],
        ]
        if normalized in {str(alias).strip().lower() for alias in aliases}:
            return fixture
    raise DryRunError(
        f"dry-run accepts only the canonical fictional input {SHOWCASE_DRY_RUN_INPUT!r}"
    )


def _pubchem_properties_for_fixtures(fixtures: list[dict[str, Any]]) -> dict:
    keys = (
        "CID",
        "IUPACName",
        "MolecularFormula",
        "MolecularWeight",
        "CanonicalSMILES",
        "InChI",
        "InChIKey",
    )
    return {
        "PropertyTable": {
            "Properties": [{key: fixture[key] for key in keys} for fixture in fixtures]
        }
    }


def _canned_pubchem_property() -> dict:
    return _pubchem_properties_for_fixtures([_SHOWCASE_COMPOUND_FIXTURE])


def _canned_pubchem_sdq() -> dict:
    row = deepcopy(_SHOWCASE_COMPOUND_FIXTURE["sdq_patent"])
    return {
        "SDQOutputSet": [
            {
                "rows": [row],
                "totalCount": 1,
            }
        ]
    }


def _canned_lens() -> dict:
    return {
        "data": [],
        "results": 0,
        "total": 0,
    }


def _canned_surechembl() -> dict:
    return {"results": []}


def _canned_bigquery() -> list[dict]:
    # BigQuery returns a list of row-dicts. Downstream normalisers iterate
    # and call ``row.get(...)``; returning ``[]`` keeps the shape correct
    # without faking any hits.
    return []


def _canned_bigquery_for_url(url: str) -> Any:
    if url in {"get_patent_claims_batch", "get_examiner_citations_batch"}:
        return {}
    if url == "get_patent_full_text":
        return (
            f"{_SHOWCASE_FAMILY['title']}\n\n"
            f"{_SHOWCASE_FAMILY['claims'][0]['text']}\n\n"
            f"{_SHOWCASE_PAYLOAD['disclaimer']}"
        )
    empty_result_queries = {
        "search_by_assignee_cached",
        "search_by_cpc_and_keywords_cached",
        "search_compound_annotations_cached",
        "search_patents_by_compound_cached",
        "search_translated_patents_cached",
    }
    if url in empty_result_queries:
        return _canned_bigquery()
    raise DryRunError(f"dry-run has no canonical BigQuery response for url={url!r}")


def _canned_epo_ops() -> dict:
    return {"ops:world-patent-data": {}}


def _canned_uspto_odp() -> dict:
    return {"patentBag": []}


def _canned_patentscope() -> dict:
    return {"results": []}


def _canned_patentsview() -> dict:
    return {"patents": [], "count": 0, "total_patent_count": 0}


def _canned_kipris() -> list[dict[str, Any]]:
    # KIPRIS wraps its parsed-list boundary in ResponseCache, not the raw XML
    # transport, so the canonical response must already be normalized rows.
    return []


def _canned_patcid_for_url(url: str) -> list[Any]:
    if url.startswith("inchikey_prefix="):
        prefix = url.split("=", 1)[1]
        for fixture in _COMPOUND_FIXTURES.values():
            if fixture["InChIKey"].startswith(prefix):
                return [
                    {"inchikey": fixture["InChIKey"], "patent_id": pid}
                    for pid in fixture["PatentID"]
                ]
        return []
    if url.startswith("inchikey="):
        inchikey = url.split("=", 1)[1]
        for fixture in _COMPOUND_FIXTURES.values():
            if fixture["InChIKey"] == inchikey:
                return list(fixture["PatentID"])
    return []


def _canned_pubmed() -> dict:
    return {"esearchresult": {"idlist": []}}


def _canned_semantic_scholar() -> dict:
    return {"data": [], "total": 0}


def _canned_openalex() -> dict:
    return {"results": [], "meta": {"count": 0}}


def _canned_ptab() -> dict:
    return {"results": []}


def _canned_orange_book() -> dict:
    return {"results": []}


def _canned_purple_book() -> dict:
    return {"results": []}


def _canned_tavily() -> dict:
    return {"results": []}


# Source -> canned-response factory. Unknown sources fail closed: adding a new
# production integration must never silently turn the showcase into a partial
# or accidentally live run.
_HTTP_SOURCE_FACTORIES: dict[str, Any] = {
    "pubchem": _canned_pubchem_property,
    "pubchem_sdq": _canned_pubchem_sdq,
    "lens": _canned_lens,
    "surechembl": _canned_surechembl,
    "bigquery": _canned_bigquery,
    "epo_ops": _canned_epo_ops,
    "uspto_odp": _canned_uspto_odp,
    "patentscope": _canned_patentscope,
    "patentsview": _canned_patentsview,
    "kipris": _canned_kipris,
    "pubmed": _canned_pubmed,
    "semantic_scholar": _canned_semantic_scholar,
    "openalex": _canned_openalex,
    "ptab": _canned_ptab,
    "orange_book": _canned_orange_book,
    "purple_book": _canned_purple_book,
    "tavily": _canned_tavily,
}


def _pubchem_response_for_path(url: str) -> Any:
    """Pick the right pubchem canned shape based on the request path."""
    if "/compound/name/" in url and "/property/" in url:
        token = url.split("/compound/name/", 1)[1].split("/property/", 1)[0]
        return _pubchem_properties_for_fixtures([_fixture_for_token(token)])
    if "/compound/smiles/" in url and "/property/" in url:
        token = url.split("/compound/smiles/", 1)[1].split("/property/", 1)[0]
        return _pubchem_properties_for_fixtures([_fixture_for_token(token)])
    if "/compound/inchikey/" in url and "/property/" in url:
        token = url.split("/compound/inchikey/", 1)[1].split("/property/", 1)[0]
        return _pubchem_properties_for_fixtures([_fixture_for_token(token)])
    if "/synonyms/" in url:
        cid = url.split("/compound/cid/", 1)[1].split("/synonyms/", 1)[0]
        fixture = _FIXTURE_BY_CID.get(cid, _SHOWCASE_COMPOUND_FIXTURE)
        return {
            "InformationList": {
                "Information": [{"CID": fixture["CID"], "Synonym": fixture["Synonym"]}]
            }
        }
    if "/xrefs/PatentID/" in url:
        cid = url.split("/compound/cid/", 1)[1].split("/xrefs/", 1)[0]
        fixture = _FIXTURE_BY_CID.get(cid, _SHOWCASE_COMPOUND_FIXTURE)
        return {
            "InformationList": {
                "Information": [{"CID": fixture["CID"], "PatentID": fixture["PatentID"]}]
            }
        }
    if "/compound/cid/" in url and "/property/" in url:
        cid_text = url.split("/compound/cid/", 1)[1].split("/property/", 1)[0]
        fixtures = [
            _FIXTURE_BY_CID[cid] for cid in cid_text.split(",") if cid in _FIXTURE_BY_CID
        ] or [_SHOWCASE_COMPOUND_FIXTURE]
        return _pubchem_properties_for_fixtures(fixtures)
    raise DryRunError(f"dry-run has no canonical PubChem response for url={url!r}")


def _pubchem_sdq_response_for_body(body: str | bytes | None) -> dict:
    if not body:
        raise DryRunError("dry-run PubChem SDQ request body was empty")
    try:
        query = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise DryRunError("dry-run PubChem SDQ request body was not valid JSON") from None
    where = query.get("where", {}) if isinstance(query, dict) else {}
    conditions = where.get("ands", []) if isinstance(where, dict) else []
    fixture = next(
        (
            _FIXTURE_BY_CID[str(condition.get("cid", ""))]
            for condition in conditions
            if isinstance(condition, dict) and str(condition.get("cid", "")) in _FIXTURE_BY_CID
        ),
        None,
    )
    if fixture is None:
        raise DryRunError("dry-run PubChem SDQ request did not target the showcase CID")
    row = deepcopy(fixture["sdq_patent"])
    return {"SDQOutputSet": [{"rows": [row], "totalCount": 1}]}


# ---------------------------------------------------------------------------
# Claude provider — synthesise the LLM cache envelope for any role
# ---------------------------------------------------------------------------


def _import_class(class_path: str) -> type:
    """Import a class by its cache-key path.

    ``claude_response_cache._class_path`` emits ``"module:ClassName"``
    (colon-separated) so we prefer that delimiter and fall back to the
    dotted form for any caller that passes the more familiar shape.
    """
    if ":" in class_path:
        module_name, _, class_name = class_path.rpartition(":")
    else:
        module_name, _, class_name = class_path.rpartition(".")
    module = importlib.import_module(module_name)
    return cast("type", getattr(module, class_name))


def _patent_ids_from_payload(payload: dict[str, Any]) -> list[str]:
    user_prompt = str(payload.get("user", ""))
    return re.findall(r"^Patent ID:\s*(\S+)", user_prompt, flags=re.MULTILINE)


def _build_canned_pydantic(
    cls: type[BaseModel],
    *,
    request_payload: dict[str, Any] | None = None,
) -> BaseModel:
    """Construct a minimally-valid instance of ``cls`` for dry-run.

    Strategy: introspect the class for known role-aligned classes and build
    them by hand. For unknown classes, attempt ``cls()`` (works for models
    where every field has a default) and fall back to a synthesised payload
    derived from the field annotations.
    """
    # Local import to avoid cycles at module import time.
    from praviar_pipeline.models.analysis import (
        AnalysisEvaluation,
        ClaimAnalysis,
        ClaimElement,
        ElementStatus,
        PatentAnalysis,
        RiskLevel,
    )
    from praviar_pipeline.models.equivalents import (
        ChemicalEquivalenceContext,
        DoEAssessment,
        EstoppelResult,
        FWRAssessment,
    )
    from praviar_pipeline.models.invalidity import InvalidityAssessment, InvalidityLLMResponse
    from praviar_pipeline.models.report_sections import VerificationReport
    from praviar_pipeline.models.triage import Relevance, TriageBatch, TriageResult
    from praviar_pipeline.models.verification import VerificationCheck, VerificationResult

    name = cls.__name__
    patent_ids = _patent_ids_from_payload(request_payload or {}) or [_CANNED_PATENT_ID]
    patent_id = patent_ids[0]

    if name == "TriageResult":
        return TriageResult(
            patent_id=patent_id,
            relevance=Relevance.RELEVANT,
            reason="dry-run canned",
            blocking_potential="dry-run canned",
            key_claims=[1],
            confidence=0.5,
        )
    if name == "TriageBatch":
        return TriageBatch(
            results=[
                TriageResult(
                    patent_id=current_patent_id,
                    relevance=Relevance.RELEVANT,
                    reason="dry-run canned",
                    blocking_potential="dry-run canned",
                    key_claims=[1],
                    confidence=0.5,
                )
                for current_patent_id in patent_ids
            ]
        )
    if name == "PatentAnalysis":
        return PatentAnalysis(
            patent_id=patent_id,
            title=str(_SHOWCASE_FAMILY["title"]),
            assignee=str(_SHOWCASE_FAMILY["assignee"]),
            risk_level=RiskLevel.MEDIUM,
            risk_summary=(
                "Canonical fictional evidence contains a candidate overlap; "
                "qualified review is required and no legal conclusion is represented."
            ),
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    elements=[
                        ClaimElement(
                            element_number=1,
                            element_text=str(_SHOWCASE_FAMILY["claims"][0]["text"]),
                            status=ElementStatus.UNCLEAR,
                            reasoning="Synthetic fixture mapping requires qualified review.",
                            confidence=0.5,
                            evidence=str(_SHOWCASE_FAMILY["evidence_ids"][0]),
                        )
                    ],
                    overall_status=ElementStatus.UNCLEAR,
                    overall_confidence=0.5,
                    reasoning="Canonical fictional candidate overlap only.",
                )
            ],
        )
    if name == "AnalysisEvaluation":
        return AnalysisEvaluation(issues=[], overall_quality="good")
    if name == "ClaimAnalysis":
        return ClaimAnalysis(
            claim_number=1,
            claim_type="independent",
            elements=[
                ClaimElement(
                    element_number=1,
                    element_text="A canned element",
                    status=ElementStatus.UNCLEAR,
                    reasoning="dry-run canned",
                    confidence=0.5,
                    evidence="dry-run canned evidence",
                )
            ],
            overall_status=ElementStatus.UNCLEAR,
            overall_confidence=0.5,
        )
    if name == "DoEAssessment":
        return DoEAssessment(
            patent_id=patent_id,
            claim_number=1,
            element_number=1,
            element_text="dry-run canned",
            estoppel=EstoppelResult(file_wrapper_available=False),
            fwr=FWRAssessment(
                same_function=False,
                function_reasoning="dry-run",
                same_way=False,
                way_reasoning="dry-run",
                same_result=False,
                result_reasoning="dry-run",
                equivalent=False,
                chemical_context=ChemicalEquivalenceContext(),
            ),
            overall_equivalent=False,
            confidence=0.5,
            confidence_band="LOW",
            reasoning="dry-run canned",
        )
    if name == "InvalidityAssessment":
        return InvalidityAssessment(
            patent_id=patent_id,
            overall_invalidity_strength="weak",
            reasoning="dry-run canned",
            confidence=0.5,
            confidence_band="LOW",
        )
    if name == "InvalidityLLMResponse":
        return InvalidityLLMResponse(
            arguments=[],
            overall_strength="weak",
            overall_reasoning="dry-run canned",
        )
    if name == "VerificationResult":
        return VerificationResult(
            checks=[
                VerificationCheck(
                    check_name="dry_run_check",
                    passed=True,
                    severity="pass",
                    details="dry-run canned",
                )
            ],
            all_citations_valid=True,
            all_claims_grounded=True,
            all_entities_valid=True,
            dates_consistent=True,
            risk_levels_justified=True,
        )
    if name == "VerificationCheck":
        return VerificationCheck(
            check_name="dry_run_check",
            passed=True,
            severity="pass",
            details="dry-run canned",
        )
    if name == "VerificationReport":
        return VerificationReport(
            total_claims_checked=1,
            claims_correct=1,
            overall_assessment="PASS",
        )

    # Fallback: try the no-arg constructor. This works whenever every field
    # has a default and no ``model_validator(mode="after")`` raises.
    try:
        return cls()
    except Exception:
        # Last resort — synthesise a payload of empty values and hope the
        # field validators tolerate it. Surface a clear error if not.
        try:
            return cls.model_validate({})
        except Exception as exc:
            from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

            raise DryRunError(
                f"No canned response factory for response_model={name!r}; "
                "and no-arg construction failed "
                f"({safe_exception_type(exc)})"
            ) from None


def _build_claude_envelope(*, body: str | bytes | None) -> dict[str, Any]:
    """Synthesise the JSON envelope ``cache.wrap`` returns for a Claude call.

    The Claude cache layer expects ``{"parsed_envelope": ..., "usage": {},
    "extras": {}}`` from the cache's stored value (see
    :func:`claude_response_cache.wrap_llm_call`). We rebuild that envelope
    here from the cache key body, which carries the request kind and (for
    structured calls) the response_model class path.
    """
    if not body:
        raise DryRunError("Claude cache request body was empty — cannot dispatch")
    payload = json.loads(body if isinstance(body, str) else body.decode("utf-8"))

    kind = payload.get("kind")
    response_model_path = payload.get("response_model")

    if kind == "complete_text":
        return {
            "parsed_envelope": {
                "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
                "kind": "str",
                "data": "Dry-run canned text response.",
            },
            "usage": _zero_usage(),
            "extras": {},
        }

    if not response_model_path:
        # Structured call without a response_model is unusual — degrade to text.
        return {
            "parsed_envelope": {
                "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
                "kind": "str",
                "data": "Dry-run canned text response.",
            },
            "usage": _zero_usage(),
            "extras": {},
        }

    cls = _import_class(response_model_path)
    if not isinstance(cls, type) or not issubclass(cls, BaseModel):
        raise DryRunError(f"Cached response_model is not a BaseModel: {response_model_path}")

    instance = _build_canned_pydantic(cls, request_payload=payload)
    envelope = {
        "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
        "kind": "pydantic",
        "class_path": response_model_path,
        "data": instance.model_dump(mode="json"),
    }
    extras: dict[str, Any] = {}
    if kind == "complete_with_thinking":
        extras = {"thinking_text": "Dry-run canned thinking."}

    return {
        "parsed_envelope": envelope,
        "usage": _zero_usage(),
        "extras": extras,
    }


def _zero_usage() -> dict[str, Any]:
    return {
        "model": "dry-run",
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


def dry_run_provider(
    *,
    source: str,
    method: str,
    url: str,
    body: str | bytes | None,
) -> Any:
    """Dispatch a cache-wrapped call to its canned response."""
    if source.startswith("claude:"):
        return _build_claude_envelope(body=body)

    if source == "pubchem":
        return _pubchem_response_for_path(url)
    if source == "pubchem_sdq":
        return _pubchem_sdq_response_for_body(body)
    if source == "patcid":
        return _canned_patcid_for_url(url)
    if source == "bigquery":
        return _canned_bigquery_for_url(url)

    factory = _HTTP_SOURCE_FACTORIES.get(source)
    if factory is None:
        raise DryRunError(f"dry-run has no canonical provider for source={source!r}")
    return factory()


# ---------------------------------------------------------------------------
# Direct-httpx monkey-patches for paths that bypass the cache
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _PatchRecord:
    """Tracks one monkey-patch so we can restore the original on exit."""

    target: Any
    attr: str
    original: Any


@dataclass(slots=True)
class _DryRunState:
    """Mutable state for one harness invocation."""

    cache: ResponseCache | None = None
    patches: list[_PatchRecord] = field(default_factory=list)
    previous_cache: ResponseCache | None = None
    previous_provider: Any = None
    env_overrides: dict[str, str | None] | None = None
    blocked_external_calls: int = 0


def _apply_patch(state: _DryRunState, target: Any, attr: str, replacement: Any) -> None:
    if not hasattr(target, attr):
        return
    state.patches.append(_PatchRecord(target=target, attr=attr, original=getattr(target, attr)))
    setattr(target, attr, replacement)


def _install_pubchem_patches(state: _DryRunState) -> None:
    """Replace direct-httpx PubChem methods with canned coroutines."""
    from praviar_pipeline.clients import pubchem as pubchem_mod

    async def _canned_similarity_search(self, smiles, threshold=0.7, max_records=50):
        fixture = _fixture_for_token(smiles)
        return [
            {
                "cid": fixture["CID"],
                "CID": fixture["CID"],
                "iupac_name": fixture["IUPACName"],
                "canonical_smiles": fixture["CanonicalSMILES"],
                "molecular_formula": fixture["MolecularFormula"],
                "molecular_weight": float(fixture["MolecularWeight"]),
                "tanimoto_similarity": 1.0,
            }
        ]

    async def _canned_poll_list_key(self, list_key, *, max_records=50, max_polls=None):
        return []

    _apply_patch(state, pubchem_mod.PubChemClient, "similarity_search", _canned_similarity_search)
    _apply_patch(state, pubchem_mod.PubChemClient, "_poll_list_key", _canned_poll_list_key)


def _install_epo_ops_patches(state: _DryRunState) -> None:
    """Stub EPO OPS auth + direct-httpx family lookups.

    The EPO client fetches an access token via a direct ``httpx.post`` in
    :meth:`_ensure_token` (not routed through the cache), so DRY_RUN mode
    must short-circuit it before any real credential is required.
    """
    try:
        from praviar_pipeline.clients import epo_ops as epo_mod
    except ImportError:
        return

    async def _canned_ensure_token(self):
        return "dryrun-epo-token"

    async def _canned_get_family(self, patent_id):
        return {"ops:world-patent-data": {}}

    async def _canned_get_biblio(self, patent_id):
        return {"ops:world-patent-data": {}}

    async def _canned_get_register(self, patent_id):
        return {"ops:world-patent-data": {}}

    async def _canned_search_published_data(
        self,
        cpc_codes=None,
        claim_keywords=None,
        applicants=None,
        max_results=100,
    ):
        return []

    _apply_patch(state, epo_mod.EPOOPSClient, "_ensure_token", _canned_ensure_token)
    _apply_patch(state, epo_mod.EPOOPSClient, "get_family", _canned_get_family)
    _apply_patch(
        state,
        epo_mod.EPOOPSClient,
        "search_published_data",
        _canned_search_published_data,
    )
    if hasattr(epo_mod.EPOOPSClient, "get_biblio"):
        _apply_patch(state, epo_mod.EPOOPSClient, "get_biblio", _canned_get_biblio)
    if hasattr(epo_mod.EPOOPSClient, "get_register"):
        _apply_patch(state, epo_mod.EPOOPSClient, "get_register", _canned_get_register)


def _install_query_expansion_patches(state: _DryRunState) -> None:
    """Keep explicit synthetic expansion out of live-grounding policy lanes."""
    from praviar_pipeline.pipeline import step1b_expand, step1b_expand_helpers

    def _synthetic_grounding_not_required(_settings: Any) -> bool:
        return False

    _apply_patch(
        state,
        step1b_expand,
        "query_expansion_requires_grounding",
        _synthetic_grounding_not_required,
    )
    _apply_patch(
        state,
        step1b_expand_helpers,
        "query_expansion_requires_grounding",
        _synthetic_grounding_not_required,
    )


def _install_regulatory_patches(state: _DryRunState) -> None:
    """Prevent downloaded regulatory indexes in the zero-spend showcase."""
    from datetime import datetime

    from praviar_pipeline.clients import orange_book, pte_data

    async def _empty_orange_book(_cache_path=None):
        return orange_book.OrangeBookIndex({})

    async def _empty_pte_dataset():
        return pte_data.PTECertificateDataset(
            records=[],
            source_url="showcase://fictional/pte",
            official_page_url="showcase://fictional/pte",
            coverage_scope="synthetic_records_only",
            coverage_note="Canonical fictional showcase fixture; no live retrieval.",
            retrieved_at=datetime.fromisoformat(str(_SHOWCASE_PAYLOAD["clock"])),
        )

    _apply_patch(state, orange_book, "load_orange_book", _empty_orange_book)
    _apply_patch(state, pte_data, "fetch_pte_certificate_dataset", _empty_pte_dataset)


def _install_live_collector_patches(state: _DryRunState) -> None:
    """Keep live-only evidence collectors explicit in the synthetic profile.

    The canonical showcase deliberately performs no live file-wrapper or EPO
    register retrieval.  Those collectors may still be planned by the normal
    adaptive runtime, so record them as intentionally skipped instead of
    invoking a provider or manufacturing authoritative coverage.
    """
    from praviar_pipeline.models.report import SourceHealthEntry, SourceStatus
    from praviar_pipeline.pipeline.runtime import (
        live_collector_execution,
        live_collectors,
    )

    async def _skip_uspto_runtime_context(
        *,
        patent_ids,
        prosecution_cache,
        fetch_prosecution_context_fn,
    ):
        del patent_ids, fetch_prosecution_context_fn
        return (
            SourceHealthEntry(
                source="uspto_odp",
                status=SourceStatus.SKIPPED,
                attempted_count=0,
                covered_count=0,
                error_message="Canonical fictional showcase; no live retrieval.",
            ),
            dict(prosecution_cache),
        )

    original_counting_collector = live_collector_execution.collect_counting_enrichment_runtime

    async def _skip_live_register_collection(
        *,
        source,
        patent_hits,
        collector_fn,
    ):
        if source == "epo_register":
            return SourceHealthEntry(
                source=source,
                status=SourceStatus.SKIPPED,
                attempted_count=0,
                covered_count=0,
                error_message="Canonical fictional showcase; no live retrieval.",
            )
        return await original_counting_collector(
            source=source,
            patent_hits=patent_hits,
            collector_fn=collector_fn,
        )

    _apply_patch(
        state,
        live_collectors,
        "collect_uspto_odp_runtime_context_impl",
        _skip_uspto_runtime_context,
    )
    _apply_patch(
        state,
        live_collector_execution,
        "collect_counting_enrichment_runtime",
        _skip_live_register_collection,
    )


def _install_network_guard(state: _DryRunState) -> None:
    """Block and count outbound transports missed by explicit adapters.

    Patching only ``httpx.AsyncClient`` is not a process-wide boundary: a new
    synchronous client, ``urllib``, or a raw socket could otherwise reach the
    network without incrementing the showcase receipt.  The socket patches are
    the final fail-closed layer for Python transports; the httpx patches reject
    earlier and produce a single, deterministic counter increment.
    """
    import socket
    import ssl

    import httpx

    def _record_blocked_call() -> None:
        state.blocked_external_calls += 1
        if state.cache is not None:
            cast("Any", state.cache).showcase_blocked_external_calls = state.blocked_external_calls

    async def _blocked_send(self, request, *args, **kwargs):
        _record_blocked_call()
        raise DryRunError("dry-run blocked an uncanned external HTTP request")

    def _blocked_sync_send(self, request, *args, **kwargs):
        _record_blocked_call()
        raise DryRunError("dry-run blocked an uncanned external HTTP request")

    def _blocked_socket_operation(*args, **kwargs):
        _record_blocked_call()
        raise DryRunError("dry-run blocked an uncanned external network request")

    _apply_patch(state, httpx.AsyncClient, "send", _blocked_send)
    _apply_patch(state, httpx.Client, "send", _blocked_sync_send)
    _apply_patch(state, socket, "create_connection", _blocked_socket_operation)
    _apply_patch(state, socket, "getaddrinfo", _blocked_socket_operation)
    for operation in (
        "gethostbyaddr",
        "gethostbyname",
        "gethostbyname_ex",
        "getnameinfo",
    ):
        _apply_patch(state, socket, operation, _blocked_socket_operation)
    for operation in ("connect", "connect_ex"):
        _apply_patch(state, socket.socket, operation, _blocked_socket_operation)

    # A socket connected before the harness, or a UDP ``sendto`` using a
    # numeric address, never crosses the patched connection/name-resolution
    # methods.  Guard writes on Internet-family sockets while preserving
    # AF_UNIX socketpairs used by asyncio for internal wakeups.
    internet_families = {socket.AF_INET, socket.AF_INET6}
    for operation in ("send", "sendall", "sendto", "sendmsg", "sendfile"):
        original = getattr(socket.socket, operation, None)
        if original is None:
            continue

        def _guarded_socket_write(
            sock,
            *args,
            _original=original,
            **kwargs,
        ):
            if sock.family in internet_families:
                return _blocked_socket_operation()
            return _original(sock, *args, **kwargs)

        _apply_patch(state, socket.socket, operation, _guarded_socket_write)

    # TLS sockets override base methods and perform native I/O through their
    # ``_sslobj``. Handshake-on-read and close-notify during ``unwrap`` can
    # write on an already-established connection without reaching socket.send.
    for operation in (
        "send",
        "sendall",
        "sendfile",
        "write",
        "do_handshake",
        "read",
        "recv",
        "recv_into",
        "recvfrom",
        "recvfrom_into",
        "recvmsg",
        "recvmsg_into",
        "unwrap",
        "verify_client_post_handshake",
        "shutdown",
    ):
        original = getattr(ssl.SSLSocket, operation, None)
        if original is None:
            continue

        def _guarded_tls_operation(
            sock,
            *args,
            _original=original,
            **kwargs,
        ):
            if sock.family in internet_families:
                return _blocked_socket_operation()
            return _original(sock, *args, **kwargs)

        _apply_patch(state, ssl.SSLSocket, operation, _guarded_tls_operation)


def _install_analysis_patches(state: _DryRunState) -> None:
    """Replace only the provider-backed adaptive analysis boundary.

    The normal Step 4 batch planner, escalation routing, evaluator, audit
    stamping, and downstream gates still execute. The direct research-agent
    transport is the one Step 4 path that does not use ``ResponseCache``.
    """
    from praviar_pipeline.models.reasoning import ReasoningTrace
    from praviar_pipeline.pipeline import step4_analyze
    from praviar_pipeline.pipeline.analysis.context_binding import analysis_context_sha256

    async def _canonical_agentic_analysis(
        _claude,
        patent,
        compound,
        _triage,
        product_context=None,
        intended_actions=None,
        target_jurisdictions=None,
        development_stage=None,
    ):
        analysis = cast(
            "Any",
            _build_canned_pydantic(
                _import_class("praviar_pipeline.models.analysis:PatentAnalysis"),
                request_payload={"user": f"Patent ID: {patent.patent_id}"},
            ),
        )
        analysis.analysis_context_sha256 = analysis_context_sha256(
            patent_id=patent.patent_id,
            compound_identity=compound,
            product_context=product_context,
            intended_actions=intended_actions,
            target_jurisdictions=target_jurisdictions,
            development_stage=development_stage,
        )
        analysis.model_used = "canonical-showcase-fixture"
        analysis.input_tokens = 0
        analysis.output_tokens = 0
        return analysis, ReasoningTrace(
            agent_type="claim_analysis",
            model="canonical-showcase-fixture",
            patent_id=patent.patent_id,
            self_critique="Synthetic fixture output; qualified review remains required.",
            final_output_summary="Canonical fictional candidate overlap.",
            confidence=0.5,
        )

    _apply_patch(
        state,
        step4_analyze,
        "_analyze_single_patent_agentic",
        _canonical_agentic_analysis,
    )


def _showcase_section_content(section_id: str) -> str:
    """Return validator-safe narrative sourced only from the fixture."""
    patent_id = _CANNED_PATENT_ID
    shared = (
        "This is a wholly fictional research preview generated from a canonical "
        "synthetic fixture. It performs no live patent retrieval, expresses no "
        "legal conclusion, and requires review by a qualified professional before "
        "any external use. The record is deliberately limited to synthetic evidence."
    )
    content = {
        "executive_summary": (
            "Overall Risk: MEDIUM\n\n"
            f"{shared} The synthetic record for {patent_id} contains one candidate "
            "claim overlap concerning Example Molecule Alpha. The medium classification "
            "means uncertainty remains; it is not a finding of infringement, validity, "
            "enforceability, clearance, or freedom to operate. One fictional register "
            "is marked partial, so source coverage is expressly incomplete. The named "
            "family and organization are invented. A reviewer must confirm scope, claim "
            "construction, legal status, and searched coverage before relying on any "
            "workflow output. Export remains blocked pending that independent review. "
            "The appropriate next action is evidence confirmation, not a commercial or "
            "legal decision. All identifiers and facts in this preview are synthetic."
        ),
        "key_patents": (
            f"{shared} {patent_id} is the parser-safe identifier derived from the "
            "fictional matter reference. Its synthetic family is titled Fictional "
            "substituted scaffold compositions and the recorded owner is Fictional "
            "Meridian Therapeutics. Claim 1 is mapped as a candidate overlap with "
            "medium confidence. The mapping remains unresolved and must be reviewed."
        ),
        "damages_injunction": (
            f"{shared} No damages exposure, injunction probability, litigation history, "
            "market value, or enforceability conclusion can be inferred from this "
            "demonstration. Those issues are intentionally outside the synthetic record."
        ),
        "invalidity": (
            f"{shared} The fixture supplies no real prior art, prosecution record, PTAB "
            "history, estoppel position, or jurisdiction-specific equivalents analysis. "
            "Any generated assessment is therefore a workflow exercise only."
        ),
        "recommendations": (
            f"{shared} Confirm that the searched record is sufficient, review the "
            "candidate construction and current status, document an independent decision, "
            "and keep export blocked until qualified review is complete. Do not substitute "
            "this demonstration for professional legal or scientific diligence."
        ),
        "data_quality": (
            f"{shared} Synthetic Register A is represented as complete for its invented "
            "records while Synthetic Register B is explicitly partial. No accuracy, "
            "completeness, freshness, or jurisdictional coverage is represented."
        ),
    }
    return content.get(section_id, shared)


def _install_report_patches(state: _DryRunState) -> None:
    """Use canonical prose at the report-provider boundary and retain checks."""
    from praviar_pipeline.models.report_sections import ReportSection, VerificationReport
    from praviar_pipeline.pipeline import step8_unified_report
    from praviar_pipeline.pipeline.report.deterministic_checks import run_deterministic_checks
    from praviar_pipeline.pipeline.report.verification_flow import VerificationFlowResult

    async def _canonical_section(
        _claude,
        section_id,
        section_title,
        _prompt_file,
        _max_tokens,
        _toolkit,
        _context,
    ):
        content = _showcase_section_content(section_id)
        patents = [_CANNED_PATENT_ID] if _CANNED_PATENT_ID in content else []
        return ReportSection(
            section_id=section_id,
            section_title=section_title,
            content=content,
            patents_referenced=patents,
            word_count=len(content.split()),
            input_tokens=0,
            output_tokens=0,
        )

    async def _canonical_verification(
        _claude,
        sections,
        data_store,
        *,
        total_input,
        total_output,
    ):
        deterministic_results = run_deterministic_checks(sections, data_store)
        verification = VerificationReport(
            total_claims_checked=1,
            claims_correct=1,
            overall_assessment="PASS",
            deterministic_check_results=deterministic_results,
        )
        return VerificationFlowResult(
            verification_report=verification,
            verify_input=0,
            verify_output=0,
            total_input=total_input,
            total_output=total_output,
        )

    _apply_patch(
        state,
        step8_unified_report,
        "_generate_section_unified",
        _canonical_section,
    )
    _apply_patch(
        state,
        step8_unified_report,
        "_run_report_verification_flow",
        _canonical_verification,
    )


# ---------------------------------------------------------------------------
# Public API — context manager
# ---------------------------------------------------------------------------


_DRY_RUN_ENV_STUBS: dict[str, str] = {
    "ANTHROPIC_API_KEY": "sk-ant-dryrun",
    "PATENTSVIEW_API_KEY": "dryrun-pv",
    "USPTO_ODP_API_KEY": "dryrun-odp",
    "OPS_CONSUMER_KEY": "dryrun-ops-key",
    "OPS_CONSUMER_SECRET": "dryrun-ops-secret",
    "KIPRIS_API_KEY": "dryrun-kipris",
    "PATENTSCOPE_USERNAME": "dryrun-patentscope",
    "PATENTSCOPE_PASSWORD": "dryrun-patentscope",
    "SEMANTIC_SCHOLAR_API_KEY": "dryrun-s2",
    "OPENALEX_API_KEY": "dryrun@example.com",
    "LENS_API_KEY": "dryrun-lens",
    "TAVILY_API_KEY": "",
    "BIGQUERY_PROJECT_ID": "",
    "EMBEDDING_RANKING_ENABLED": "false",
    "SEARCH_CITATION_TRAVERSAL_ENABLED": "false",
    "SEARCH_ENABLE_PUBCHEM_GENUS": "false",
    "SEARCH_ENABLE_SURECHEMBL": "false",
    "BIGQUERY_CACHE_ENABLED": "false",
    "CRITIC_ENABLED": "false",
    "MULTI_PERSPECTIVE_ENABLED": "false",
    "DRAWING_ANALYSIS_ENABLED": "false",
    "HYBRID_RETRIEVAL_ENABLED": "false",
    "LITERATURE_SEARCH_ENABLED": "true",
    "CONTINUATION_EXPANSION_ENABLED": "true",
    "SEARCH_ENABLE_NCBI_PATENT_SEQUENCE": "false",
    "SOURCE_FAILURE_POLICY": "coverage_aware",
    "DETERMINISTIC_SEED": "42",
    "PIPELINE_LLM_HARD_BUDGET_USD": "50",
    "HITL_ENABLED": "false",
    "IDENTITY_REVIEW_REQUIRED": "false",
    "RESPONSE_CACHE_MODE": "record",
    "RESPONSE_CACHE_DIR": "",
    "RESPONSE_CACHE_EXPECTED_DIGEST": "",
    "RESPONSE_CACHE_EXPECTED_HMAC": "",
    "RESPONSE_CACHE_EXPECTED_KEY_ID": "",
    "PIPELINE_CHECKPOINT_HMAC_SECRET": (
        '{"active_key_id":"dryrun-v1","keys":'
        '{"dryrun-v1":"dryrun-pipeline-checkpoint-hmac-key-not-for-production"}}'
    ),
}


def showcase_runtime_overrides(*, output_dir: Path) -> dict[str, Any]:
    """Return the canonical profile, independent of valid production env values."""
    return {
        "claude_triage_model": "claude-haiku-4-5-20251001",
        "claude_analysis_model": "claude-sonnet-4-6",
        "claude_deep_model": "claude-sonnet-4-6",
        "output_dir": str(output_dir),
        "search_jurisdictions": ["US", "WO", "EP", "JP", "KR", "CN", "IN", "CA", "AU"],
        "search_max_ranked_results": 1000,
        "search_tanimoto_threshold": 0.55,
        "include_expired": True,
        "enable_pubchem": True,
        "enable_bigquery": True,
        "enable_surechembl": False,
        "enable_patcid": True,
        "search_expired_grace_years": 5,
        "citation_traversal_enabled": False,
        "citation_max_depth": 2,
        "search_loop_enabled": False,
        "hitl_enabled": False,
        "hitl_checkpoints": [],
        "hitl_auto_skip_minutes": 60,
        "identity_review_required": False,
        "max_analysis_patents": 100,
        "max_doe_candidates": 15,
        "triage_batch_size": 10,
        "matter_type": "small_molecule",
        "trust_mode": "explorer",
        "intended_actions": [],
        "product_context": {},
        "target_jurisdictions": [],
        "jurisdiction_bundle": "us_ep",
        "development_stage": "discovery",
        "asset_type_hint": "unknown",
        "jurisdiction_policy": "us_ep_core",
        "clearance_threshold_profile": "world_class_us_ep",
        "max_run_duration_hours": 24,
        "source_authority_policy": "official_plus_licensed",
        "required_record_components": [],
        "require_verified_manual_markush": True,
        "markush_evidence_max_age_days": 35,
        "markush_evidence_receipt": None,
    }


def _install_env_stubs(state: _DryRunState) -> None:
    """Set placeholder env vars + clear the settings cache.

    Dry-run never spends a real key, but :func:`get_settings` raises if the
    Anthropic key is absent. The stubs unblock construction; we restore the
    original env on exit and re-clear the cache so subsequent code uses
    real settings again.
    """
    import os

    from praviar_pipeline.config import clear_settings_cache

    state.env_overrides = {}
    for key, val in _DRY_RUN_ENV_STUBS.items():
        state.env_overrides[key] = os.environ.get(key)
        os.environ[key] = val
    clear_settings_cache()


def _restore_env_stubs(state: _DryRunState) -> None:
    import os

    from praviar_pipeline.config import clear_settings_cache

    for key, original in (state.env_overrides or {}).items():
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original
    clear_settings_cache()


@contextlib.contextmanager
def install_dry_run_harness(
    *,
    cache_dir: Path | None = None,
    checkpoint_dir: Path | None = None,
) -> Iterator[ResponseCache]:
    """Install the dry-run harness for the duration of the context.

    On enter:
      * Set placeholder env vars so :func:`get_settings` succeeds.
      * Build a :class:`ResponseCache` in :attr:`CacheMode.DRY_RUN` mode.
      * Register :func:`dry_run_provider` as the global provider.
      * Monkey-patch known direct-client paths and install a socket-level guard.

    On exit:
      * Restore every monkey-patched attribute.
      * Restore the original environment.
      * Restore the previously active dry-run provider.
      * Restore (or clear) the previous active cache.

    Yields the installed cache so tests can introspect it.
    """
    from praviar_pipeline.pipeline.ranking.scoring import use_ranking_reference_date
    from praviar_pipeline.response_cache import get_current_cache, get_dry_run_provider

    state = _DryRunState()
    state.previous_cache = get_current_cache()
    state.previous_provider = get_dry_run_provider()

    try:
        _install_env_stubs(state)
        if checkpoint_dir is not None:
            import os

            assert state.env_overrides is not None
            state.env_overrides["CHECKPOINT_DIR"] = os.environ.get("CHECKPOINT_DIR")
            os.environ["CHECKPOINT_DIR"] = str(checkpoint_dir)

        # The harness stores synthetic responses only; this stable path makes
        # repeated local dry runs deterministic and is never a production cache.
        cache_dir = cache_dir or Path("/tmp/praviar_pipeline-dryrun-cache")  # nosec B108
        cache_dir.mkdir(parents=True, exist_ok=True)
        state.cache = ResponseCache(cache_dir=cache_dir, mode=CacheMode.DRY_RUN)
        cast("Any", state.cache).showcase_blocked_external_calls = 0

        set_dry_run_provider(dry_run_provider)
        set_current_cache(state.cache)
        # Establish the process-wide transport boundary before importing any
        # optional adapter modules in the installers below. Import-time client
        # behaviour must not get a window in which it can reach the network.
        _install_network_guard(state)
        _install_pubchem_patches(state)
        _install_epo_ops_patches(state)
        _install_query_expansion_patches(state)
        _install_regulatory_patches(state)
        _install_live_collector_patches(state)
        _install_analysis_patches(state)
        _install_report_patches(state)
        fixture_reference_date = date.fromisoformat(str(_SHOWCASE_PAYLOAD["clock"])[:10])
        with use_ranking_reference_date(fixture_reference_date):
            yield state.cache
    finally:
        for patch in reversed(state.patches):
            setattr(patch.target, patch.attr, patch.original)
        set_dry_run_provider(state.previous_provider)
        set_current_cache(state.previous_cache)
        if state.env_overrides is not None:
            _restore_env_stubs(state)


# ---------------------------------------------------------------------------
# Post-run assertions
# ---------------------------------------------------------------------------


_REQUIRED_STAGE_TIMINGS = (
    "step1_resolve",
    "step2_search",
    "step3_triage",
    "step4_analyze",
    "step5_doe",
    "step6_invalid",
    "step7_verify",
)
SHOWCASE_COMPLETED_STAGES = (*_REQUIRED_STAGE_TIMINGS, "step8_report")


def validate_showcase_input(user_input: str) -> None:
    """Fail closed unless the CLI was given the canonical fixture identity."""
    if str(user_input).strip() != SHOWCASE_DRY_RUN_INPUT:
        raise DryRunError(
            f"dry-run accepts only the canonical fictional input {SHOWCASE_DRY_RUN_INPUT!r}"
        )


def _showcase_stage_names(report: dict[str, Any]) -> list[str]:
    audit = report.get("audit_trail") or {}
    timings = audit.get("timing_data") if isinstance(audit, dict) else []
    return [
        str(timing.get("step_name", "")) for timing in timings or [] if isinstance(timing, dict)
    ]


def showcase_substantive_payload(report: dict[str, Any]) -> dict[str, Any]:
    """Project all stable business output for cross-run golden comparison.

    New top-level report fields enter the digest by default.  Only values that
    are intentionally run-specific are excluded, so a newly added output cannot
    silently evade the golden contract.
    """
    run_specific_fields = {
        "audit_trail",
        "generated_at",
        "manifest",
        "report_id",
        "showcase_run",
    }
    completed_stages = [
        stage for stage in _showcase_stage_names(report) if stage in SHOWCASE_COMPLETED_STAGES
    ]
    return {
        "schema_version": "praviar.showcase-dry-run.v2",
        "fixture": showcase_fixture_receipt(),
        "business_output": {
            key: report[key] for key in sorted(report) if key not in run_specific_fields
        },
        "completed_stages": completed_stages,
    }


def showcase_substantive_digest(report: dict[str, Any]) -> str:
    """Return a stable digest excluding run IDs, clocks, and durations."""
    encoded = json.dumps(
        showcase_substantive_payload(report),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assert_zero_usage_and_cost(report: dict[str, Any]) -> None:
    """Require present zero totals and reject non-zero nested accounting."""
    manifest = report.get("manifest")
    if not isinstance(manifest, dict):
        raise DryRunAssertionError("manifest", "missing or not a dict")
    required_metrics = (
        (report, "total_input_tokens", "total_input_tokens"),
        (report, "total_output_tokens", "total_output_tokens"),
        (report, "estimated_cost_usd", "estimated_cost_usd"),
        (manifest, "total_cost_usd", "manifest.total_cost_usd"),
        (manifest, "cost_breakdown", "manifest.cost_breakdown"),
    )
    for container, key, path in required_metrics:
        if key not in container:
            raise DryRunAssertionError(path, "missing")

    metric_names = {
        "input_tokens",
        "output_tokens",
        "total_input_tokens",
        "total_output_tokens",
        "estimated_cost_usd",
        "total_cost_usd",
    }

    def _visit(value: Any, path: str = "report") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if key in metric_names or key.endswith("_cost_usd"):
                    if not isinstance(child, (int, float)) or isinstance(child, bool):
                        raise DryRunAssertionError(child_path, "expected numeric zero")
                    if float(child) != 0.0:
                        raise DryRunAssertionError(child_path, f"expected zero, got {child!r}")
                _visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                _visit(child, f"{path}[{index}]")

    _visit(report)


def attach_showcase_run_receipt(
    report: dict[str, Any],
    *,
    blocked_external_calls: int,
) -> dict[str, Any]:
    """Validate the eight-stage zero-provider run and attach its receipt."""
    # Keep the receipt API fail-closed even when called outside the CLI, which
    # performs the same validation before reaching this function.
    assert_report_valid(report)
    validate_showcase_input(str((report.get("compound") or {}).get("original_input", "")))
    observed = _showcase_stage_names(report)
    missing = [stage for stage in SHOWCASE_COMPLETED_STAGES if stage not in observed]
    if missing:
        raise DryRunAssertionError("audit_trail.timing_data", f"missing stages: {missing}")
    duplicate = [stage for stage in SHOWCASE_COMPLETED_STAGES if observed.count(stage) != 1]
    if duplicate:
        raise DryRunAssertionError(
            "audit_trail.timing_data",
            f"showcase stages must be recorded exactly once: {duplicate}",
        )
    completed_stages = [stage for stage in observed if stage in SHOWCASE_COMPLETED_STAGES]
    if completed_stages != list(SHOWCASE_COMPLETED_STAGES):
        raise DryRunAssertionError(
            "audit_trail.timing_data",
            "showcase stages are not recorded in execution order",
        )
    if blocked_external_calls:
        raise DryRunAssertionError(
            "showcase.external_provider_calls",
            f"blocked {blocked_external_calls} uncanned HTTP request(s)",
        )
    _assert_zero_usage_and_cost(report)
    report["showcase_run"] = {
        **showcase_fixture_receipt(),
        "fictional": True,
        "input": SHOWCASE_DRY_RUN_INPUT,
        "completed_stages": completed_stages,
        "external_provider_calls": 0,
        "total_cost_usd": 0.0,
        "substantive_sha256": showcase_substantive_digest(report),
    }
    return report


def assert_report_valid(report: dict) -> None:
    """Verify the dry-run report shape after the pipeline returns.

    Checks:
      * ``report`` round-trips through ``json.dumps``.
      * A patents-shaped key (``patents`` or ``patent_analyses``), an
        analyses-shaped key (``analyses``, ``patent_analyses``, or
        ``doe_assessments``), and ``risk_summary`` are present.
      * Every ``source_health`` entry status is ``ok`` or ``skipped`` and at
        least one source is ``ok`` — no unavailable or evidence-free runs.
      * Manifest contains ``pipeline_version``, ``generated_at``,
        non-empty ``prompt_hashes``, populated ``model_versions`` and
        ``cost_breakdown``, plus tool provenance schema fields.
    """
    if not isinstance(report, dict):
        raise DryRunAssertionError("report", f"expected dict, got {type(report).__name__}")

    serialization_error_type: str | None = None
    try:
        json.dumps(report, default=str)
    except (TypeError, ValueError) as exc:
        from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

        serialization_error_type = safe_exception_type(exc)
    if serialization_error_type is not None:
        raise DryRunAssertionError(
            "report",
            f"not JSON-serialisable ({serialization_error_type})",
        ) from None

    patents_keys = ("patents", "patent_analyses", "patent_details")
    analyses_keys = ("analyses", "patent_analyses", "doe_assessments")
    if not any(k in report for k in patents_keys):
        raise DryRunAssertionError("report.patents", f"missing (expected one of {patents_keys})")
    if not any(k in report for k in analyses_keys):
        raise DryRunAssertionError("report.analyses", f"missing (expected one of {analyses_keys})")
    if "risk_summary" not in report:
        raise DryRunAssertionError("report.risk_summary", "missing")

    health = report.get("source_health")
    entries_value: Any
    if isinstance(health, list):
        entries_value = health
    elif isinstance(health, dict):
        entries_value = health.get("entries")
    else:
        entries_value = None
    if not isinstance(entries_value, list) or not entries_value:
        raise DryRunAssertionError("source_health.entries", "missing or empty")
    entries = entries_value
    has_successful_source = False
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise DryRunAssertionError(
                f"source_health.entries[{index}]",
                "expected a source-health mapping",
            )
        status = str(entry.get("status", "")).strip().lower()
        if status not in {"ok", "skipped"}:
            source = str(entry.get("source", "?") or "?")
            raise DryRunAssertionError(
                f"source_health.entries[{index}].status",
                f"source {source!r} has disallowed status {status!r}",
            )
        has_successful_source = has_successful_source or status == "ok"
    if not has_successful_source:
        raise DryRunAssertionError(
            "source_health.entries",
            "contains no successful source execution",
        )

    manifest = report.get("manifest")
    if not isinstance(manifest, dict):
        raise DryRunAssertionError("report.manifest", "missing or not a dict")

    for key in ("pipeline_version", "generated_at"):
        if not manifest.get(key):
            raise DryRunAssertionError(f"manifest.{key}", "missing or empty")

    prompt_hashes = manifest.get("prompt_hashes")
    if not prompt_hashes:
        raise DryRunAssertionError("manifest.prompt_hashes", "empty")

    if not manifest.get("model_versions"):
        raise DryRunAssertionError("manifest.model_versions", "missing or empty")

    if not manifest.get("tool_trace_digest"):
        raise DryRunAssertionError("manifest.tool_trace_digest", "missing or empty")

    for key in ("tool_call_count", "tool_definition_hashes"):
        if key not in manifest:
            raise DryRunAssertionError(f"manifest.{key}", "missing")

    if "cost_breakdown" not in manifest:
        raise DryRunAssertionError("manifest.cost_breakdown", "missing")
