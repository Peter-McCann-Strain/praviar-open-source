"""Final score normalization and blending helpers for Step 2b ranking."""

from __future__ import annotations

import math


def _ranking_key(patent: dict) -> str:
    candidate_index = patent.get("_audit_candidate_index")
    if isinstance(candidate_index, int):
        return f"candidate:{candidate_index}"
    return str(patent.get("publicationnumber", ""))


def _normalize_ranked_scores(ranked: list[tuple[dict, float]]) -> dict[str, float]:
    """Normalize finite ranking scores to 0.0-1.0.

    BM25 is non-negative, while cosine similarity may be negative. Preserve
    ratio-to-maximum behavior for non-negative signals and use min-max scaling
    when a signal crosses below zero.
    """
    raw_scores = [float(score) for _, score in ranked]
    if any(not math.isfinite(score) for score in raw_scores):
        raise ValueError("ranking signal contains a non-finite score")
    if not raw_scores:
        return {}

    min_score = min(raw_scores)
    max_score = max(raw_scores)

    normalized: dict[str, float] = {}
    for patent, score in ranked:
        pub_num = _ranking_key(patent)
        if max_score == min_score:
            value = 1.0
        elif min_score < 0:
            value = (score - min_score) / (max_score - min_score)
        elif max_score > 0:
            value = score / max_score
        else:
            value = 0.0
        normalized[pub_num] = min(1.0, max(0.0, value))
    return normalized


def build_final_ranking(
    bm25_ranked: list[tuple[dict, float]],
    composite_scores: dict[str, float],
    embedding_ranked: list[tuple[dict, float]] | None,
    *,
    max_results: int,
    blend_composite_3way: float,
    blend_bm25_3way: float,
    blend_embedding_3way: float,
    blend_composite_2way: float,
    blend_bm25_2way: float,
) -> list[dict]:
    """Blend normalized rank signals and return the final patent ordering."""
    bm25_scores = _normalize_ranked_scores(bm25_ranked)
    embedding_scores = _normalize_ranked_scores(embedding_ranked) if embedding_ranked else {}
    bm25_raw_scores = {_ranking_key(patent): score for patent, score in bm25_ranked}
    embedding_raw_scores = {
        _ranking_key(patent): score for patent, score in (embedding_ranked or [])
    }
    use_embeddings = bool(embedding_scores)

    final_scored: list[tuple[dict, float]] = []
    for patent, _ in bm25_ranked:
        pub_num = _ranking_key(patent)
        comp_score = composite_scores.get(pub_num, 0.0)
        norm_bm25 = bm25_scores.get(pub_num, 0.0)

        if use_embeddings:
            norm_emb = embedding_scores.get(pub_num, 0.0)
            final = (
                blend_composite_3way * comp_score
                + blend_bm25_3way * norm_bm25
                + blend_embedding_3way * norm_emb
            )
        else:
            final = blend_composite_2way * comp_score + blend_bm25_2way * norm_bm25

        ranked_patent = dict(patent)
        ranked_patent["_retrieval_scores"] = {
            "composite": comp_score,
            "bm25_raw": bm25_raw_scores.get(pub_num),
            "bm25_normalized": norm_bm25,
            "embedding_raw": embedding_raw_scores.get(pub_num),
            "embedding_normalized": (embedding_scores.get(pub_num) if use_embeddings else None),
            "final_blend": final,
        }
        final_scored.append((ranked_patent, final))

    final_scored.sort(key=lambda item: item[1], reverse=True)
    return [patent for patent, _ in final_scored[:max_results]]
