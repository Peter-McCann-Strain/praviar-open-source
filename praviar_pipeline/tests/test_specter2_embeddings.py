"""Unit tests for praviar_pipeline.utils.specter2_embeddings.

The actual SPECTER2 model is never loaded during tests. We patch
``_get_model`` so that all public functions receive a lightweight stub
that returns deterministic numpy arrays. This avoids a ``sentence_transformers``
import at test-collection time.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DIM = 768
_PATCH_TARGET = "praviar_pipeline.utils.specter2_embeddings._get_model"


def _make_fake_model(dim: int = _DIM) -> MagicMock:
    """Return a mock whose encode() returns deterministic numpy arrays."""
    model = MagicMock()

    def _encode(input_, batch_size=32, normalize_embeddings=False):
        if isinstance(input_, str):
            return np.ones(dim, dtype=np.float32)
        return np.ones((len(input_), dim), dtype=np.float32)

    model.encode.side_effect = _encode
    return model


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_singleton():
    """Ensure the module-level singleton is reset between tests."""
    import praviar_pipeline.utils.specter2_embeddings as mod

    original = mod._MODEL
    mod._MODEL = None
    yield
    mod._MODEL = original


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEmbedPatentQuery:
    def test_returns_list_of_floats(self):
        fake_model = _make_fake_model()
        with patch(_PATCH_TARGET, return_value=fake_model):
            from praviar_pipeline.utils.specter2_embeddings import embed_patent_query

            result = embed_patent_query("aspirin")

        assert isinstance(result, list)
        assert len(result) == _DIM
        assert all(isinstance(v, float) for v in result)

    def test_encode_called_with_normalize(self):
        fake_model = _make_fake_model()
        with patch(_PATCH_TARGET, return_value=fake_model):
            from praviar_pipeline.utils.specter2_embeddings import embed_patent_query

            embed_patent_query("ibuprofen")

        fake_model.encode.assert_called_once_with("ibuprofen", normalize_embeddings=True)


class TestEmbedPatentBatch:
    def test_returns_correct_shape(self):
        fake_model = _make_fake_model()
        texts = ["patent one", "patent two", "patent three"]
        with patch(_PATCH_TARGET, return_value=fake_model):
            from praviar_pipeline.utils.specter2_embeddings import embed_patent_batch

            result = embed_patent_batch(texts)

        assert isinstance(result, list)
        assert len(result) == len(texts)
        for row in result:
            assert isinstance(row, list)
            assert len(row) == _DIM
            assert all(isinstance(v, float) for v in row)

    def test_batch_size_forwarded(self):
        fake_model = _make_fake_model()
        texts = ["a", "b"]
        with patch(_PATCH_TARGET, return_value=fake_model):
            from praviar_pipeline.utils.specter2_embeddings import embed_patent_batch

            embed_patent_batch(texts, batch_size=16)

        fake_model.encode.assert_called_once_with(texts, batch_size=16, normalize_embeddings=True)

    def test_empty_batch_returns_empty_list(self):
        fake_model = _make_fake_model()
        with patch(_PATCH_TARGET, return_value=fake_model):
            from praviar_pipeline.utils.specter2_embeddings import embed_patent_batch

            result = embed_patent_batch([])

        assert result == []


class TestSingletonPattern:
    def test_model_loaded_only_once_across_queries(self):
        """_get_model must be called for each encode, but the model
        constructor itself is called only once across repeated queries."""
        import praviar_pipeline.utils.specter2_embeddings as mod

        fake_model = _make_fake_model()
        call_count = 0

        def fake_get_model():
            nonlocal call_count
            # Simulate real singleton: populate _MODEL on first call.
            if mod._MODEL is None:
                call_count += 1
                mod._MODEL = fake_model
            return mod._MODEL

        with patch(_PATCH_TARGET, side_effect=fake_get_model):
            from praviar_pipeline.utils.specter2_embeddings import embed_patent_query

            embed_patent_query("query one")
            embed_patent_query("query two")
            embed_patent_query("query three")

        # The underlying model constructor was invoked only once.
        assert call_count == 1

    def test_model_loaded_only_once_across_query_and_batch(self):
        import praviar_pipeline.utils.specter2_embeddings as mod

        fake_model = _make_fake_model()
        call_count = 0

        def fake_get_model():
            nonlocal call_count
            if mod._MODEL is None:
                call_count += 1
                mod._MODEL = fake_model
            return mod._MODEL

        with patch(_PATCH_TARGET, side_effect=fake_get_model):
            from praviar_pipeline.utils.specter2_embeddings import (
                embed_patent_batch,
                embed_patent_query,
            )

            embed_patent_query("single query")
            embed_patent_batch(["batch item"])

        assert call_count == 1

    def test_get_model_uses_correct_model_name(self):
        """_get_model must request 'allenai-specter2' from SentenceTransformer."""
        import praviar_pipeline.utils.specter2_embeddings as mod

        fake_model = _make_fake_model()

        # Patch the import *inside* _get_model by supplying a mock module.
        import sys
        from types import ModuleType

        fake_st_module = ModuleType("sentence_transformers")
        mock_cls = MagicMock(return_value=fake_model)
        fake_st_module.SentenceTransformer = mock_cls  # type: ignore[attr-defined]

        with patch.dict(sys.modules, {"sentence_transformers": fake_st_module}):
            # Reset singleton so _get_model runs the constructor path.
            mod._MODEL = None
            from praviar_pipeline.utils.specter2_embeddings import _get_model

            _get_model()

        mock_cls.assert_called_once_with("allenai-specter2")
