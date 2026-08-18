"""BM25 and embedding rerankers for Step 2b patent ranking."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound

logger = structlog.get_logger()


def bm25_rerank(
    patents: list[dict],
    compound: ResolvedCompound,
    top_k: int = 500,
) -> list[tuple[dict, float]]:
    """Re-rank patents using BM25 on title, abstract, and claims."""
    import bm25s

    if not patents:
        return []

    corpus = []
    for patent in patents:
        title = str(patent.get("title", ""))
        abstract = str(patent.get("abstract", ""))
        claims = str(patent.get("claims_text", ""))
        corpus.append(f"{title} {abstract} {claims}")

    settings = get_settings()
    query_parts = [compound.name]
    query_parts.extend(compound.synonyms[: settings.rank_bm25_synonyms])
    query_parts.extend(compound.cas_numbers[: settings.rank_bm25_cas])
    query_text = " ".join(query_parts)

    corpus_tokens = bm25s.tokenize(corpus, stopwords="en")
    retriever = bm25s.BM25()
    retriever.index(corpus_tokens)

    query_tokens = bm25s.tokenize([query_text], stopwords="en")
    k = min(top_k, len(patents))
    results, scores = retriever.retrieve(query_tokens, k=k)

    ranked: list[tuple[dict, float]] = []
    for idx, score in zip(results[0], scores[0], strict=False):
        ranked.append((patents[int(idx)], float(score)))

    return ranked


def embedding_rerank(
    patents: list[dict],
    compound: ResolvedCompound,
    top_k: int = 500,
) -> list[tuple[dict, float]] | None:
    """Re-rank patents using PaECTER/SPECTER2 embeddings when enabled."""
    settings = get_settings()
    if not settings.embedding_ranking_enabled:
        return None

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ConfigurationError(
            "sentence-transformers is required when embedding ranking is enabled",
            source="embedding_ranking",
            step="ranking",
        ) from None

    if not patents:
        return []

    model_name = settings.specter_model_name
    cache_dir = settings.specter_cache_dir or None

    from pathlib import Path

    if cache_dir:
        model_path = Path(cache_dir) / model_name.replace("/", "--")
        if not model_path.exists():
            logger.warning(
                "embedding_model_not_cached",
                model=model_name,
            )

    logger.info("embedding_rerank_start", model=model_name, patents=len(patents))

    failure_type: str | None = None
    try:
        model = SentenceTransformer(model_name, cache_folder=cache_dir)

        corpus = [f"{pat.get('title', '')} {pat.get('abstract', '')}" for pat in patents]
        query = f"{compound.name} {' '.join(compound.synonyms[:5])}"

        query_embedding = model.encode([query], convert_to_tensor=True)
        corpus_embeddings = model.encode(corpus, convert_to_tensor=True, batch_size=64)

        from sentence_transformers.util import cos_sim

        scores = cos_sim(query_embedding, corpus_embeddings)[0].tolist()
    except Exception as exc:
        failure_type = type(exc).__name__
        logger.warning("embedding_ranking_failed", error_type=failure_type)
    if failure_type is not None:
        raise SourceUnavailableError("embedding_ranking", "embedding rerank failed") from None
    ranked = sorted(
        zip(patents, scores, strict=True),
        key=lambda item: item[1],
        reverse=True,
    )
    return ranked[:top_k]
