"""SPECTER2 embedding generation utilities for patent retrieval.

Provides lazy-loaded singleton access to the allenai-specter2 model and
helper functions for both query-time and batch-indexing use cases.

Outputs 768-dimensional float32 embeddings compatible with BigQuery
VECTOR_SEARCH over ARRAY<FLOAT64> columns.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)

_MODEL: Any = None  # SentenceTransformer | None at runtime


def _get_model() -> SentenceTransformer:
    """Return the singleton SPECTER2 model, loading it on first call."""
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        log.info("Loading SPECTER2 model (allenai-specter2) -- one-time cost")
        _MODEL = SentenceTransformer("allenai-specter2")
        log.info("SPECTER2 model loaded")
    return cast("SentenceTransformer", _MODEL)


def embed_patent_query(text: str) -> list[float]:
    """Embed a query string for patent retrieval.

    Intended for single-query use at search time. The embedding is
    L2-normalised so that cosine similarity equals dot product, matching
    the convention expected by BigQuery VECTOR_SEARCH.

    Args:
        text: The query text to embed (e.g. compound name + context).

    Returns:
        A 768-dimensional list of float32 values.
    """
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return cast("list[float]", vector.tolist())


def embed_patent_batch(
    texts: list[str],
    batch_size: int = 64,
) -> list[list[float]]:
    """Embed a batch of patent texts for indexing.

    Intended for offline indexing pipelines, not query time. Uses
    batched inference to amortise model overhead across many documents.

    Args:
        texts: List of patent texts to embed.
        batch_size: Mini-batch size passed to sentence-transformers.
            Tune against available VRAM/RAM.

    Returns:
        A list of 768-dimensional float lists, one per input text,
        in the same order as ``texts``.
    """
    model = _get_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
    )
    return [cast("list[float]", vector.tolist()) for vector in vectors]
