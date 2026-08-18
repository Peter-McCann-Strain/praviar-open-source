"""Tests for the MarkushGrapher-2 worker's paper-faithful decoding chain.

The worker's ``predict()`` function calls ``model.generate`` and then walks
a three-step decoding chain lifted from the paper's eval.py:

    1. ``MarkushTokenizer.decode_plus_decode_other_tokens(ids)``
    2. ``re.search(r"<cxsmi>(.*?)</cxsmi>", ...)`` to isolate the optimised
       CXSMILES string.
    3. ``CXSMILESTokenizer.convert_opt_to_out(optimised)`` to expand
       R-groups and append the ``|$…$|`` annotation block.

The worker itself cannot be imported under the dev venv because it pulls in
torch, mlx-vlm, and the in-tree ``transformers`` fork that only exists in
``venvs/markushgrapher/``. Mirror the isolation trick from
``test_markushgrapher_worker_resize.py``: we regex out the body of
``predict()`` and exec it in a sandbox with fake torch / tokenizer / PIL /
rdkit modules wired up to exercise the full decoding path without loading a
single real model weight.
"""

from __future__ import annotations

import json
import re
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    pytest.skip("PIL not available in dev venv", allow_module_level=True)

from praviar_pipeline.ocsr.workers.markushgrapher_worker import (
    _aspect_preserving_resize as _real_aspect_preserving_resize,
)


@pytest.fixture(autouse=True)
def _restore_sys_modules():
    """The predict-function loader replaces ``sys.modules['rdkit']`` and
    ``sys.modules['rdkit.Chem']`` with stubs so the worker's in-function
    imports resolve to fakes. Leaving those stubs installed pollutes
    downstream tests that rely on real RDKit (e.g. test_molparser_worker).
    Snapshot + restore around every test in this module.
    """
    saved = {key: sys.modules.get(key) for key in ("torch", "rdkit", "rdkit.Chem")}
    try:
        yield
    finally:
        for key, val in saved.items():
            if val is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = val


WORKER_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "praviar_pipeline"
    / "ocsr"
    / "workers"
    / "markushgrapher_worker.py"
)


# ---------------------------------------------------------------------------
# Test doubles for the heavy runtime dependencies the worker pulls in.
# ---------------------------------------------------------------------------


class _FakeMarkushTokenizer:
    """Return a canned `<markush><cxsmi>...</cxsmi><stable>...</stable></markush>`
    string from ``decode_plus_decode_other_tokens`` so the downstream chain
    gets exercised.
    """

    def __init__(self, decoded_text: str):
        self._decoded_text = decoded_text
        self.calls: list[object] = []

    def decode_plus_decode_other_tokens(self, ids):
        self.calls.append(("decode_plus_decode_other_tokens", list(ids)))
        return self._decoded_text

    def get_stable(self, text):
        self.calls.append(("get_stable", text))
        return {"R1": ["a halogen atom"]}


class _FakeCXSMILESTokenizer:
    """Return a plausible CXSMILES expansion from ``convert_opt_to_out``.

    The real expansion behaviour is exercised by the MG2 venv; here we just
    check that the worker calls it with the extracted optimised string and
    returns the final string to its caller.
    """

    def __init__(self, final_cxsmi: str):
        self._final = final_cxsmi
        self.received: list[str] = []

    def convert_opt_to_out(self, opt: str):
        self.received.append(opt)
        return self._final


class _FakeTensor(list):
    """Very small tensor stand-in supporting ``.to(device)`` and ``len(...)``.

    The worker slices ``generated[0][1:-1]`` then hands that off to the
    MarkushTokenizer mock, so plain Python lists with a ``.to`` no-op are
    sufficient.
    """

    def to(self, _device):  # pragma: no cover - trivial
        return self


class _NoOpCtx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_torch_module():
    torch = types.ModuleType("torch")

    torch.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    torch.no_grad = lambda: _NoOpCtx()

    def _device(name):
        return types.SimpleNamespace(type=name)

    torch.device = _device
    return torch


def _fake_rdkit_module():
    rdkit = types.ModuleType("rdkit")
    chem = types.ModuleType("rdkit.Chem")

    class _Mol:
        pass

    def _from_smiles(s):
        # Treat anything non-empty and containing at least one alphabetic
        # atom character as a "valid" molecule. The test is not about
        # chemistry correctness — it's about whether the worker wires the
        # decoding chain together.
        if s and any(c.isalpha() for c in s):
            return _Mol()
        return None

    def _to_smiles(_mol):
        return "CANONICAL"

    chem.MolFromSmiles = _from_smiles
    chem.MolToSmiles = _to_smiles
    rdkit.Chem = chem
    return rdkit, chem


def _load_predict_function(
    decoded_text: str,
    final_cxsmi: str,
    generated_sequence=None,
):
    """Exec the worker's ``predict`` function with a synthetic environment."""
    source = WORKER_PATH.read_text()
    match = re.search(
        r"^def predict\(image_path: str\) -> dict:.*?(?=^def _run_persistent)",
        source,
        re.DOTALL | re.MULTILINE,
    )
    if match is None:  # pragma: no cover
        raise RuntimeError("Could not extract predict() from the worker source")
    predict_src = match.group(0)

    ns: dict = {
        "__name__": "markushgrapher_worker_under_test",
        "time": __import__("time"),
        "sys": sys,
        "re": re,
        "json": json,
        "safe_worker_error": lambda operation, error: (
            f"{operation} failed ({type(error).__name__})"
        ),
        "_UPSTREAM_IMAGE_SIZE": 512,
        "_validate_decoded_structure": lambda smiles: (
            False,
            "|" in smiles,
            "reference_required" if "|" in smiles else "passed",
        ),
    }

    # Stub torch / rdkit via sys.modules so the worker's in-function imports
    # pick them up without touching the real packages.
    torch_mod = _fake_torch_module()
    rdkit_mod, chem_mod = _fake_rdkit_module()
    sys.modules.setdefault("torch", torch_mod)
    sys.modules["rdkit"] = rdkit_mod
    sys.modules["rdkit.Chem"] = chem_mod

    markush_tok = _FakeMarkushTokenizer(decoded_text)
    cxsmiles_tok = _FakeCXSMILESTokenizer(final_cxsmi)

    fake_model = MagicMock()
    sequence = (
        generated_sequence
        if generated_sequence is not None
        else [
            1,
            101,
            102,
            103,
            104,
            2,
        ]
    )
    fake_model.generate.return_value = [_FakeTensor(sequence)]

    fake_tokenizer = MagicMock()
    fake_processor = MagicMock(
        return_value={
            "input_ids": _FakeTensor([0, 0, 0]),
            "attention_mask": _FakeTensor([1, 1, 1]),
            "bbox": _FakeTensor([[0, 0, 0, 0]]),
            "pixel_values": _FakeTensor([0.0]),
        }
    )
    fake_device = types.SimpleNamespace(type="cpu")

    def _get_model():
        return (
            fake_model,
            fake_tokenizer,
            fake_processor,
            fake_device,
            markush_tok,
            cxsmiles_tok,
        )

    # OCR is exercised separately — give back an empty result.
    def _run_ocr(_img):
        fake_processor.ocr_input_image = _img
        return [], []

    ns["get_model"] = _get_model
    ns["run_ocr"] = _run_ocr
    ns["_aspect_preserving_resize"] = _real_aspect_preserving_resize

    exec(predict_src, ns)
    return (
        ns["predict"],
        markush_tok,
        cxsmiles_tok,
        fake_model,
        fake_processor,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_image(tmp_path):
    path = tmp_path / "fake.png"
    Image.new("RGB", (256, 512), "white").save(path)
    return path


class TestMarkushDecoderChain:
    @pytest.mark.parametrize("size", [(1024, 256), (256, 1024)])
    def test_ocr_boxes_and_visual_encoder_share_letterboxed_frame(self, tmp_path, size):
        image_path = tmp_path / f"{size[0]}x{size[1]}.png"
        Image.new("RGB", size, "black").save(image_path)
        decoded = "<markush><cxsmi>*C</cxsmi></markush>"
        final = "*C |$R1;$|"
        predict, _mtok, _ctok, _model, processor = _load_predict_function(
            decoded_text=decoded,
            final_cxsmi=final,
        )

        predict(str(image_path))

        visual_input = processor.call_args.kwargs["images"]
        assert processor.ocr_input_image is visual_input
        assert visual_input.size == (512, 512)
        assert visual_input.getpixel((0, 0)) == (255, 255, 255)

    def test_predict_fails_closed_without_reference_decoder_components(self, tmp_image):
        source = WORKER_PATH.read_text()
        predict_src = re.search(
            r"^def predict\(image_path: str\) -> dict:.*?(?=^def _run_persistent)",
            source,
            re.DOTALL | re.MULTILINE,
        ).group(0)
        ns = {
            "__name__": "markushgrapher_worker_under_test",
            "time": __import__("time"),
            "sys": sys,
            "re": re,
            "json": json,
            "_ALLOW_NO_OCR_FALLBACK": False,
            "_UPSTREAM_IMAGE_SIZE": 512,
            "_aspect_preserving_resize": _real_aspect_preserving_resize,
            "run_ocr": lambda _img: ([], []),
            "get_model": lambda: (
                MagicMock(),
                MagicMock(),
                MagicMock(),
                types.SimpleNamespace(type="cpu"),
            ),
            "safe_worker_error": lambda operation, error: (
                f"{operation} failed ({type(error).__name__})"
            ),
        }
        exec(predict_src, ns)

        result = ns["predict"](str(tmp_image))

        assert result["valid"] is False
        assert result["confidence_available"] is False
        assert result["error"] == "Model load failed (RuntimeError)"

    def test_predict_fails_closed_when_chemicalocr_fails(self, tmp_image):
        source = WORKER_PATH.read_text()
        predict_src = re.search(
            r"^def predict\(image_path: str\) -> dict:.*?(?=^def _run_persistent)",
            source,
            re.DOTALL | re.MULTILINE,
        ).group(0)

        ns: dict = {
            "__name__": "markushgrapher_worker_under_test",
            "time": __import__("time"),
            "sys": sys,
            "re": re,
            "json": json,
            "_ALLOW_NO_OCR_FALLBACK": False,
            "_UPSTREAM_IMAGE_SIZE": 512,
            "_aspect_preserving_resize": lambda img, target=512: img,
            "safe_worker_error": lambda operation, error: (
                f"{operation} failed ({type(error).__name__})"
            ),
        }

        get_model = MagicMock()

        def _raise_ocr(_img):
            raise RuntimeError("checksum mismatch")

        ns["run_ocr"] = _raise_ocr
        ns["get_model"] = get_model

        exec(predict_src, ns)
        result = ns["predict"](str(tmp_image))

        assert result["valid"] is False
        assert result["error"] == "ChemicalOCR failed (RuntimeError)"
        assert result["ocr_words"] == 0
        get_model.assert_not_called()

    def test_predict_calls_paper_decoder_chain(self, tmp_image):
        decoded = "<markush><cxsmi>*C1=CC=C(*)C=C1</cxsmi><stable>R1:F<ns>R2:Cl</stable></markush>"
        final = "*C1=CC=C(*)C=C1 |$R1;;;R2;;;$|"

        predict, mtok, ctok, _model, _processor = _load_predict_function(
            decoded_text=decoded,
            final_cxsmi=final,
        )

        predict(str(tmp_image))

        # decode_plus_decode_other_tokens MUST have been called with the
        # interior slice of the generated sequence (paper slices [1:-1]).
        decoder_calls = [c for c in mtok.calls if c[0] == "decode_plus_decode_other_tokens"]
        assert len(decoder_calls) == 1, (
            f"Expected exactly one decode_plus_decode_other_tokens call, got {decoder_calls}"
        )
        # Generator produced [1, 101, 102, 103, 104, 2]; after [1:-1] slice
        # we expect [101, 102, 103, 104].
        assert list(decoder_calls[0][1]) == [101, 102, 103, 104]

        # convert_opt_to_out must have received the <cxsmi>…</cxsmi> interior
        # with whitespace and </s> markers stripped.
        assert ctok.received == ["*C1=CC=C(*)C=C1"]

    def test_predict_returns_cxsmiles_shape(self, tmp_image):
        decoded = "<markush><cxsmi>*C1=CC=C(*)C=C1</cxsmi><stable>R1:F<ns>R2:Cl</stable></markush>"
        final = "*C1=CC=C(*)C=C1 |$R1;;;R2;;;$|"

        predict, *_ = _load_predict_function(
            decoded_text=decoded,
            final_cxsmi=final,
        )
        result = predict(str(tmp_image))

        assert result["tool"] == "markushgrapher"
        assert result["error"] == ""
        # Markush-aware output: wildcard placeholder + annotation block.
        assert "*" in result["smiles"]
        assert "|$" in result["smiles"] and "$|" in result["smiles"]
        assert result["is_markush"] is True
        assert result["valid"] is False
        assert result["confidence"] == 0.0
        assert result["confidence_available"] is False
        assert result["markush_validation"] == "reference_required"
        # Return-shape contract: all keys the runner expects.
        for key in (
            "smiles",
            "confidence",
            "confidence_available",
            "valid",
            "latency_ms",
            "tool",
            "error",
            "is_markush",
            "ocr_words",
            "ocr_time_ms",
        ):
            assert key in result, f"missing key {key} in predict() result"

    def test_predict_handles_missing_cxsmi_block(self, tmp_image):
        # Model emitted a garbage sequence with no <cxsmi> block.  The paper
        # decoder contract is mandatory, so the worker must fail closed.
        decoded = "some noise without tags"
        final = "CCO"  # bare SMILES, not CXSMILES

        predict, _mtok, ctok, *_ = _load_predict_function(
            decoded_text=decoded,
            final_cxsmi=final,
        )
        result = predict(str(tmp_image))

        assert result["error"] == "Inference failed (ValueError)"
        assert result["smiles"] == ""
        assert result["valid"] is False
        assert result["confidence_available"] is False
        assert ctok.received == []

    def test_predict_handles_convert_opt_to_out_failure(self, tmp_image):
        decoded = "<markush><cxsmi>garbage</cxsmi></markush>"

        class _BrokenTok(_FakeCXSMILESTokenizer):
            def convert_opt_to_out(self, opt):
                self.received.append(opt)
                return None  # paper signal for "could not expand"

        _predict, _mtok, _ctok, *_ = _load_predict_function(
            decoded_text=decoded,
            final_cxsmi="",  # unused
        )
        # Swap in the broken CXSMILES tokenizer by re-loading with a patched
        # get_model — easiest to rebuild from scratch.
        source = WORKER_PATH.read_text()
        predict_src = re.search(
            r"^def predict\(image_path: str\) -> dict:.*?(?=^def _run_persistent)",
            source,
            re.DOTALL | re.MULTILINE,
        ).group(0)

        ns: dict = {
            "__name__": "markushgrapher_worker_under_test",
            "time": __import__("time"),
            "sys": sys,
            "re": re,
            "json": json,
            "safe_worker_error": lambda operation, error: (
                f"{operation} failed ({type(error).__name__})"
            ),
            "_UPSTREAM_IMAGE_SIZE": 512,
            "_validate_decoded_structure": lambda smiles: (
                False,
                "|" in smiles,
                "reference_required",
            ),
        }
        torch_mod = _fake_torch_module()
        rdkit_mod, chem_mod = _fake_rdkit_module()
        sys.modules.setdefault("torch", torch_mod)
        sys.modules["rdkit"] = rdkit_mod
        sys.modules["rdkit.Chem"] = chem_mod

        mtok = _FakeMarkushTokenizer(decoded)
        ctok = _BrokenTok("")
        fake_model = MagicMock()
        fake_model.generate.return_value = [_FakeTensor([1, 101, 2])]
        fake_processor = MagicMock(
            return_value={
                "input_ids": _FakeTensor([0]),
                "attention_mask": _FakeTensor([1]),
                "bbox": _FakeTensor([[0, 0, 0, 0]]),
                "pixel_values": _FakeTensor([0.0]),
            }
        )
        ns["get_model"] = lambda: (
            fake_model,
            MagicMock(),
            fake_processor,
            types.SimpleNamespace(type="cpu"),
            mtok,
            ctok,
        )
        ns["run_ocr"] = lambda _img: ([], [])
        ns["_aspect_preserving_resize"] = lambda img, target=512: img

        exec(predict_src, ns)
        result = ns["predict"](str(tmp_image))

        # Return shape intact and no raise.
        assert result["error"] == "Inference failed (ValueError)"
        assert result["smiles"] == ""
        assert result["valid"] is False
        assert result["confidence_available"] is False
