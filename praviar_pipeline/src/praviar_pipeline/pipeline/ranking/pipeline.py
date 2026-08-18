"""Ranking-funnel orchestration helpers for Step 2b."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque


class RankedPatentResults(list[dict]):
    """Ranked rows plus complete per-input audit decisions."""

    def __init__(self, rows: list[dict], *, audit_rows: list[dict] | None = None) -> None:
        super().__init__(rows)
        self.audit_rows = audit_rows or []


def _row_sha256(row: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _indices_for_rows(all_rows: list[dict], selected_rows: list[dict]) -> list[int]:
    indices_by_identity: dict[int, deque[int]] = defaultdict(deque)
    for index, row in enumerate(all_rows):
        indices_by_identity[id(row)].append(index)
    selected: list[int] = []
    for row in selected_rows:
        indices = indices_by_identity.get(id(row))
        if not indices:
            raise ValueError("ranking candidate lost its input-row identity")
        selected.append(indices.popleft())
    return selected


def rank_patents_impl(
    sdq_results: list[dict],
    compound,
    *,
    settings,
    logger,
    multi_source_ids: set[str],
    max_results: int,
    collect_audit: bool,
    apply_hard_filters_fn,
    parse_cpc_codes_fn,
    count_cids_fn,
    parse_date_fn,
    compute_composite_score_fn,
    score_cpc_relevance_fn,
    score_compound_count_fn,
    score_recency_fn,
    score_title_keyword_fn,
    score_multi_source_fn,
    bm25_rerank_fn,
    embedding_rerank_fn,
    build_final_ranking_fn,
) -> list[dict]:
    logger.info(
        "ranking_funnel_start",
        input_count=len(sdq_results),
    )

    filtered, rejection_reasons = apply_hard_filters_fn(
        sdq_results,
        include_expired=settings.search_include_expired,
        expired_grace_years=settings.search_expired_grace_years,
        collect_audit=collect_audit,
    )
    logger.info("ranking_hard_filters_done", remaining=len(filtered))

    filtered_indices = _indices_for_rows(sdq_results, filtered)
    audit_rows: list[dict] = []
    if collect_audit:
        filtered_index_set = set(filtered_indices)
        for candidate_index, patent in enumerate(sdq_results):
            if candidate_index in filtered_index_set:
                continue
            patent_id = str(patent.get("publicationnumber", ""))
            reason = rejection_reasons.get(patent_id, "")
            if not reason:
                raise ValueError("hard-filtered candidate has no retained rejection reason")
            audit_rows.append(
                {
                    "patent_id": patent_id,
                    "candidate_index": candidate_index,
                    "disposition": "hard_filter_rejected",
                    "exclusion_stage": "hard_filter",
                    "passed_hard_filter": False,
                    "filter_reason": reason,
                    "included_in_triage": False,
                    "input_row_sha256": _row_sha256(patent),
                }
            )

    if not filtered:
        logger.warning(
            "ranking_all_filtered",
            input_count=len(sdq_results),
        )
        return RankedPatentResults([], audit_rows=audit_rows)

    scored: list[tuple[dict, float, int]] = []
    for patent, candidate_index in zip(filtered, filtered_indices, strict=True):
        ranked_patent = dict(patent) if collect_audit else patent
        if collect_audit:
            ranked_patent["_audit_candidate_index"] = candidate_index
        cpc_codes = parse_cpc_codes_fn(patent.get("classification"))
        cid_count = count_cids_fn(patent.get("cids"))
        priority_date = parse_date_fn(patent.get("prioritydate"))
        title = str(patent.get("title", ""))
        publication_number = str(patent.get("publicationnumber", ""))

        composite = compute_composite_score_fn(
            score_cpc_relevance_fn(cpc_codes),
            score_compound_count_fn(cid_count),
            score_recency_fn(priority_date),
            score_title_keyword_fn(title, compound),
            score_multi_source_fn(publication_number, multi_source_ids),
        )
        scored.append((ranked_patent, composite, candidate_index))

    scored.sort(key=lambda item: item[1], reverse=True)
    pool_size = settings.rank_bm25_pool_size
    bm25_candidates = [patent for patent, _score, _index in scored[:pool_size]]
    composite_scores = {
        (
            f"candidate:{candidate_index}"
            if collect_audit
            else str(patent.get("publicationnumber", ""))
        ): score
        for patent, score, candidate_index in scored[:pool_size]
    }

    logger.info("ranking_composite_done", candidates_for_bm25=len(bm25_candidates))

    bm25_ranked = bm25_rerank_fn(bm25_candidates, compound, top_k=len(bm25_candidates))
    embedding_ranked = embedding_rerank_fn(bm25_candidates, compound)
    full_ranking = build_final_ranking_fn(
        bm25_ranked,
        composite_scores,
        embedding_ranked,
        max_results=(len(bm25_candidates) if collect_audit else max_results),
        blend_composite_3way=settings.rank_blend_composite_3way,
        blend_bm25_3way=settings.rank_blend_bm25_3way,
        blend_embedding_3way=settings.rank_blend_embedding_3way,
        blend_composite_2way=settings.rank_blend_composite_2way,
        blend_bm25_2way=settings.rank_blend_bm25_2way,
    )
    result = (
        [
            {key: value for key, value in patent.items() if key != "_audit_candidate_index"}
            for patent in full_ranking[:max_results]
        ]
        if collect_audit
        else full_ranking
    )

    if collect_audit:
        composite_rank = {
            candidate_index: rank
            for rank, (_patent, _score, candidate_index) in enumerate(scored, start=1)
        }
        bm25_rank = {
            int(patent["_audit_candidate_index"]): rank
            for rank, (patent, _score) in enumerate(bm25_ranked, start=1)
        }
        embedding_rank = {
            int(patent["_audit_candidate_index"]): rank
            for rank, (patent, _score) in enumerate(embedding_ranked or [], start=1)
        }
        pre_cut_by_candidate: dict[int, tuple[int, dict]] = {}
        for rank, patent in enumerate(full_ranking, start=1):
            candidate_index = int(patent["_audit_candidate_index"])
            pre_cut_by_candidate[candidate_index] = (
                rank,
                patent,
            )

        for patent, composite, candidate_index in scored:
            patent_id = str(patent.get("publicationnumber", ""))
            base = {
                "patent_id": patent_id,
                "candidate_index": candidate_index,
                "passed_hard_filter": True,
                "composite_score": composite,
                "composite_rank": composite_rank[candidate_index],
                "included_in_triage": False,
                "input_row_sha256": _row_sha256(
                    {key: value for key, value in patent.items() if key != "_audit_candidate_index"}
                ),
            }
            if candidate_index not in pre_cut_by_candidate:
                audit_rows.append(
                    {
                        **base,
                        "disposition": "composite_pool_cut",
                        "exclusion_stage": "composite_pool",
                        "filter_reason": "composite_pool_cut",
                    }
                )
                continue

            pre_cut_rank, ranked_patent = pre_cut_by_candidate[candidate_index]
            scores = ranked_patent.get("_retrieval_scores", {})
            included = pre_cut_rank <= max_results
            audit_rows.append(
                {
                    **base,
                    "disposition": ("included_in_triage" if included else "final_rank_cut"),
                    "exclusion_stage": "" if included else "final_rank",
                    "filter_reason": "" if included else "rank_cut_max_results",
                    "bm25_score": scores.get("bm25_raw"),
                    "bm25_normalized_score": scores.get("bm25_normalized"),
                    "embedding_score": scores.get("embedding_raw"),
                    "embedding_normalized_score": scores.get("embedding_normalized"),
                    "final_blend_score": scores.get("final_blend"),
                    "bm25_rank": bm25_rank.get(candidate_index),
                    "embedding_rank": embedding_rank.get(candidate_index),
                    "pre_cut_rank": pre_cut_rank,
                    "final_rank": pre_cut_rank if included else None,
                    "included_in_triage": included,
                }
            )
        audit_rows.sort(key=lambda row: int(row["candidate_index"]))

    logger.info(
        "ranking_funnel_complete",
        input_count=len(sdq_results),
        after_hard_filters=len(filtered),
        output_count=len(result),
    )

    return RankedPatentResults(result, audit_rows=audit_rows)
