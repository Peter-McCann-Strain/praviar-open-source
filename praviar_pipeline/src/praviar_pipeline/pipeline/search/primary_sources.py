"""Primary source adapters for the Step 2 patent search pipeline."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.clients.bigquery import BigQueryClient
from praviar_pipeline.clients.patcid import PatCIDClient
from praviar_pipeline.clients.pubchem import PubChemClient
from praviar_pipeline.clients.surechembl import SureChEMBLClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.models.patent import PatentSource
from praviar_pipeline.utils.patent_ids import canonical_publication_id
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound

logger = structlog.get_logger()

_surechembl_similarity_cache: dict[str, dict] = {}


def clear_surechembl_similarity_cache() -> None:
    _surechembl_similarity_cache.clear()


def get_surechembl_similarity_metadata(patent_id: str) -> dict | None:
    return _surechembl_similarity_cache.get(patent_id)


async def search_pubchem_sdq(compound: ResolvedCompound) -> list[dict]:
    if compound.pubchem_cid is None:
        return []
    async with PubChemClient() as client:
        result: list[dict] = await client.sdq_search_patents(compound.pubchem_cid)
        return result


async def search_surechembl(compound: ResolvedCompound) -> list[tuple[str, PatentSource]]:
    settings = get_settings()
    async with SureChEMBLClient() as client:
        results: list[tuple[str, PatentSource]] = []

        # Build the ordered list of additional SMILES forms to query.
        # The canonical SMILES is always searched first.  Additional forms are
        # searched only when they are non-empty and differ from the canonical SMILES
        # so that we do not issue duplicate requests.
        smiles_forms: list[tuple[str, str]] = []
        seen_smiles: set[str] = set()

        def _append_smiles_form(label: str, smiles: str) -> None:
            if not smiles or smiles in seen_smiles:
                return
            seen_smiles.add(smiles)
            smiles_forms.append((label, smiles))

        _append_smiles_form("canonical", compound.canonical_smiles)
        for label, smiles in [
            ("free_base", compound.free_base_smiles),
            ("stereo_stripped", compound.stereo_stripped_smiles),
            ("scaffold", compound.scaffold_smiles),
        ]:
            _append_smiles_form(label, smiles)
        if (
            compound.tautomer_enumeration is not None
            and compound.tautomer_enumeration.search_expansion_allowed
        ):
            for candidate in compound.tautomer_enumeration.candidates:
                if candidate.search_eligible and candidate.integrity.passed:
                    _append_smiles_form(
                        f"tautomer:{candidate.candidate_id[:16]}",
                        candidate.canonical_smiles,
                    )
        for candidate in compound.prodrug_candidates:
            if candidate.search_eligible and candidate.integrity.passed:
                _append_smiles_form(
                    f"prodrug_hypothesis:{candidate.candidate_id[:16]}",
                    candidate.canonical_smiles,
                )

        if len(smiles_forms) > 1:
            logger.debug(
                "surechembl_additional_smiles_forms",
            )

        for _, smiles in smiles_forms:
            exact = await client.search_by_smiles(smiles)
            for hit in exact:
                for pat in hit.get("patents", []):
                    pid = pat.get("patent_id", pat.get("id", ""))
                    if pid:
                        results.append((pid, PatentSource.SURECHEMBL))

        if not compound.canonical_smiles:
            return results

        similar = await client.similarity_search(
            compound.canonical_smiles,
            threshold=settings.search_tanimoto_threshold,
        )
        for hit in similar:
            similarity = hit.get("similarity", hit.get("score", None))
            for pat in hit.get("patents", []):
                pid = pat.get("patent_id", pat.get("id", ""))
                if pid:
                    results.append((pid, PatentSource.SURECHEMBL))
                    if similarity is not None:
                        _surechembl_similarity_cache[pid] = {
                            "tanimoto_score": float(similarity),
                            "match_type": "similarity",
                        }

        if settings.search_surechembl_substructure_enabled:
            substruct = await client.substructure_search(
                compound.canonical_smiles,
                max_results=settings.search_surechembl_max_results,
            )
            for hit in substruct:
                for pat in hit.get("patents", []):
                    pid = pat.get("patent_id", pat.get("id", ""))
                    if pid:
                        results.append((pid, PatentSource.SURECHEMBL))
                        if pid not in _surechembl_similarity_cache:
                            _surechembl_similarity_cache[pid] = {
                                "match_type": "substructure",
                            }

        return results


async def search_pubchem_similar(compound: ResolvedCompound) -> list[tuple[str, PatentSource]]:
    settings = get_settings()
    async with PubChemClient() as client:
        similar_compounds = await client.similarity_search(
            compound.canonical_smiles,
            threshold=settings.search_tanimoto_threshold,
            max_records=20,
        )
        if not similar_compounds:
            return []

        results: list[tuple[str, PatentSource]] = []
        for comp in similar_compounds:
            cid = comp.get("CID")
            if not cid or cid == compound.pubchem_cid:
                continue
            try:
                patent_ids = await client.get_patent_links(cid)
                for pid in patent_ids[:10]:
                    results.append((pid, PatentSource.PUBCHEM))
            except Exception as exc:
                logger.warning(
                    "pubchem_similar_patent_link_failed",
                    error_type=safe_exception_type(exc),
                )
                continue

        logger.info(
            "pubchem_similar_search_complete",
            similar_compounds=len(similar_compounds),
            patent_results=len(results),
        )
        return results


async def search_pubchem_genus(
    compound: ResolvedCompound,
    *,
    client_factory=PubChemClient,
) -> list[dict]:
    """Expand a small-molecule scaffold across PubChem's developed structures.

    This is a corpus-level genus-candidate lane, not a true Markush search.
    """
    if compound.compound_type != "small_molecule":
        return []
    initial_query_smiles = compound.scaffold_smiles or compound.canonical_smiles
    if not initial_query_smiles:
        from praviar_pipeline.errors import ConfigurationError

        raise ConfigurationError(
            "No resolved scaffold or canonical structure is available",
            source="pubchem_genus",
            step="search",
        )

    settings = get_settings()
    retrieved_at = datetime.now(UTC)
    async with client_factory() as client:
        query_candidates = [
            (
                initial_query_smiles,
                "murcko_scaffold" if compound.scaffold_smiles else "canonical_fallback",
            )
        ]
        if (
            compound.scaffold_smiles
            and compound.canonical_smiles
            and compound.canonical_smiles != compound.scaffold_smiles
        ):
            query_candidates.append(
                (
                    compound.canonical_smiles,
                    "canonical_refinement_after_scaffold_cap",
                )
            )

        selected: tuple[str, str, list[int]] | None = None
        for query_smiles, query_role in query_candidates:
            cids = await client.substructure_search_cids(
                query_smiles,
                max_records=settings.pubchem_genus_max_compounds,
                max_seconds=settings.pubchem_genus_max_seconds,
            )
            if len(cids) < settings.pubchem_genus_max_compounds:
                selected = (query_smiles, query_role, cids)
                break
            logger.warning(
                "pubchem_genus_query_saturated",
                query_role=query_role,
                compound_cap=settings.pubchem_genus_max_compounds,
            )

        if selected is None:
            from praviar_pipeline.errors import SourceUnavailableError

            raise SourceUnavailableError(
                "pubchem_genus",
                "all bounded substructure queries reached the configured compound cap",
            )
        query_smiles, query_role, cids = selected
        mappings = await client.get_patent_links_for_cids(cids)

    query_sha256 = hashlib.sha256(query_smiles.encode("utf-8")).hexdigest()

    allowed = tuple(settings.search_allowed_jurisdictions)
    matches_by_patent: dict[str, list[dict]] = {}
    for mapping in mappings:
        cid = int(mapping["cid"])
        patent_ids = sorted(set(mapping["patent_ids"]))
        result_sha256 = hashlib.sha256(
            json.dumps(
                {"cid": cid, "patent_ids": patent_ids},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        for patent_id in patent_ids:
            try:
                normalized = canonical_publication_id(patent_id)
            except ValueError:
                logger.warning("pubchem_genus_invalid_publication_id")
                continue
            if not normalized.startswith(allowed):
                continue
            matches_by_patent.setdefault(normalized, []).append(
                {
                    "query_sha256": query_sha256,
                    "query_role": query_role,
                    "matched_pubchem_cid": cid,
                    "result_sha256": result_sha256,
                    "retrieved_at": retrieved_at,
                    "artifact_locator": (
                        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/"
                        f"cid/{cid}/xrefs/PatentID/JSON#sha256={result_sha256}"
                    ),
                }
            )

    if len(matches_by_patent) > settings.pubchem_genus_max_patents:
        from praviar_pipeline.errors import SourceUnavailableError

        raise SourceUnavailableError(
            "pubchem_genus",
            "patent mapping result exceeded the configured patent cap",
        )

    return [
        {
            "publication_number": patent_id,
            "match_type": "substructure",
            "genus_matches": sorted(
                matches,
                key=lambda match: int(match["matched_pubchem_cid"]),
            ),
        }
        for patent_id, matches in sorted(matches_by_patent.items())
    ]


async def search_bigquery(compound: ResolvedCompound) -> list[dict]:
    async with BigQueryClient() as client:
        settings = get_settings()
        search_terms = [compound.name, *compound.synonyms[: settings.search_max_synonyms_bigquery]]
        if compound.cas_numbers:
            search_terms.extend(compound.cas_numbers[: settings.search_max_cas_bigquery])

        result: list[dict] = await client.search_patents_by_compound(
            search_terms,
            jurisdictions=settings.search_allowed_jurisdictions,
        )
        return result


async def search_bigquery_annotations(
    compound: ResolvedCompound,
) -> list[tuple[str, PatentSource]]:
    async with BigQueryClient() as client:
        settings = get_settings()
        rows = await client.search_compound_annotations(
            name=compound.name,
            inchikey=compound.inchi_key,
            max_results=settings.search_bigquery_max_results,
        )
        return [
            (row["publication_number"], PatentSource.BIGQUERY)
            for row in rows
            if row.get("publication_number")
        ]


async def search_patcid(compound: ResolvedCompound) -> list[tuple[str, PatentSource]]:
    async with PatCIDClient() as client:
        patent_ids = await client.lookup_by_inchikey(compound.inchi_key)
        results = [(pid, PatentSource.PATCID) for pid in patent_ids]

        prefix = compound.inchi_key.split("-")[0] if "-" in compound.inchi_key else ""
        if prefix:
            prefix_results = await client.lookup_by_inchikey_prefix(prefix)
            for row in prefix_results:
                if row.get("inchikey") != compound.inchi_key:
                    pid = row.get("patent_id", "")
                    if not pid:
                        logger.warning("patcid_missing_patent_id")
                        continue
                    results.append((pid, PatentSource.PATCID))

        return results
