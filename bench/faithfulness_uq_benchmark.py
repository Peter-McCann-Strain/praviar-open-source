"""Deterministic synthetic smoke fixture for Faithfulness-Aware UQ (T3-02).

Paper: arXiv:2505.21072 - Vashurin, Fadeeva et al., "Faithfulness-Aware
Uncertainty Quantification for Fact-Checking the Output of Retrieval
Augmented Generation" (May 2025). https://arxiv.org/abs/2505.21072

This fixture checks two code paths on five programmed synthetic
(claim, evidence) pairs. It is not an empirical benchmark:

    Implementation A (existing behaviour, control):
        No per-evidence faithfulness scoring. The fixture match rate against
        the programmed labels is the rate at which
        a constant-NEUTRAL classifier matches the ground truth - i.e. 0%
        on a balanced supported/unsupported set, since NEUTRAL is never
        the correct label here.

    Implementation B (new behaviour, behind the PRAVIAR_FAITHFULNESS_UQ_ENABLED
    flag): Score each pair with Claude Haiku via the NLI prompt defined in
        ``api.services.faithfulness_uq``. The match rate is the share of pairs
        whose programmed response matches the fixture label.

The fixture reports a deterministic match-rate delta so wiring regressions are
visible. The treatment responses are encoded below, so the result is not a
measurement of a model, the product, or the paper's claimed gain. It must not
be used as performance or release evidence.

Reproducibility
---------------

To run with the real Haiku model::

    cd api
    PRAVIAR_FAITHFULNESS_UQ_ENABLED=1 APP_ENV=dev \\
        ANTHROPIC_API_KEY=sk-... \\
        PYTHONPATH=src python -m pytest tests/test_faithfulness_uq.py::test_faithfulness_uq_real_model_diagnostic -q

To run only the mock-based benchmark (the path used in CI and on developers'
machines without an API key)::

    cd api
    PYTHONPATH=src python -m pytest tests/test_faithfulness_uq.py -q

This module's ``main()`` runs the synthetic fixture and writes a JSON summary
to stdout. The output is useful only for deterministic smoke testing.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def _add_api_to_path() -> None:
    """Make the api/src tree importable without an editable install."""
    here = Path(__file__).resolve().parent
    api_src = (here.parent / "api" / "src").resolve()
    if str(api_src) not in sys.path:
        sys.path.insert(0, str(api_src))


_add_api_to_path()


from api.services.faithfulness_uq import score_pair  # noqa: E402


SYNTHETIC_PAIRS: list[tuple[str, str, str]] = [
    (
        "ENTAILED",
        "Aspirin is acetylsalicylic acid, a salicylate used for its "
        "anti-inflammatory and antiplatelet effects.",
        "Aspirin (acetylsalicylic acid) is the prototype of the salicylate "
        "drug class and is widely used for its anti-inflammatory and "
        "antiplatelet activity.",
    ),
    (
        "ENTAILED",
        "Claim 1 of US12345678 covers any pharmaceutical composition "
        "comprising the compound of formula I in a unit dosage form.",
        "Claim 1: A pharmaceutical composition comprising a compound of "
        "formula I, formulated as a unit dosage form.",
    ),
    (
        "ENTAILED",
        "The patent application has a priority date of 2018-03-15.",
        "Application US12/345,678 was filed on 15 March 2018 claiming priority "
        "from provisional 61/987,654 filed 16 March 2017.",
    ),
    (
        "CONTRADICTS",
        "The patent expressly covers all aryl-substituted variants of the "
        "compound of formula I.",
        "Claim 1 explicitly disclaims aryl substituents and restricts the "
        "scope to alkyl substituents only.",
    ),
    (
        "CONTRADICTS",
        "The compound is described as a stable solid at room temperature.",
        "The compound was found to decompose rapidly above 0 degrees Celsius, "
        "rendering room-temperature storage impossible without refrigeration.",
    ),
]


@dataclass
class BenchmarkRow:
    expected: str
    predicted: str
    confidence: float
    correct: bool


@dataclass
class BenchmarkSummary:
    implementation: str
    total_pairs: int
    correct: int
    accuracy: float
    rows: list[BenchmarkRow]


def _control_score_pair_factory() -> Any:
    """Implementation A: constant-NEUTRAL classifier representing the
    pre-T3-02 behaviour (no faithfulness signal). Returns whatever the
    Anthropic client returns, but models the absence of scoring as
    "always NEUTRAL with 0.0 confidence" for this programmed fixture.
    """

    class _NullClient:
        def __init__(self) -> None:
            self.messages = self  # so messages.create is reachable

        def create(self, **_kwargs: Any) -> Any:  # noqa: ANN401
            class _Block:
                text = json.dumps({"verdict": "NEUTRAL", "confidence": 0.0})

            return type("Resp", (), {"content": [_Block()]})()

    return _NullClient()


def _treatment_score_pair_factory() -> Any:
    """Implementation B: a deterministic mock that emits the correct verdict
    for the synthetic pairs above with high confidence. This stands in for
    the real Claude Haiku call on CI and on developer machines without an
    API key. The real-model benchmark lives in
    ``tests/test_faithfulness_uq.py::test_faithfulness_uq_real_model_diagnostic``
    and exercises the same pairs against the live model.

    The mock returns a different programmed verdict for one pair so the smoke
    fixture exercises both matching and non-matching rows. No empirical
    behaviour is represented.
    """
    # Pair index 4 is deliberately mapped to NEUTRAL so this deterministic
    # smoke fixture exercises both matching and non-matching rows. The ratio
    # is programmed behavior, not a threshold or performance claim.
    pair_to_response: dict[str, dict[str, Any]] = {
        SYNTHETIC_PAIRS[0][1]: {"verdict": "ENTAILED", "confidence": 0.94},
        SYNTHETIC_PAIRS[1][1]: {"verdict": "ENTAILED", "confidence": 0.92},
        SYNTHETIC_PAIRS[2][1]: {"verdict": "ENTAILED", "confidence": 0.88},
        SYNTHETIC_PAIRS[3][1]: {"verdict": "CONTRADICTS", "confidence": 0.91},
        SYNTHETIC_PAIRS[4][1]: {"verdict": "NEUTRAL", "confidence": 0.55},
    }

    class _MockClient:
        def __init__(self) -> None:
            self.messages = self

        def create(self, *, messages: list[dict], **_kwargs: Any) -> Any:  # noqa: ANN401
            # Recover the claim from the prompt body. The prompt template
            # places "CLAIM:\n" before the claim text; we find that marker.
            prompt = messages[0]["content"]
            for claim_text, payload in pair_to_response.items():
                if claim_text in prompt:
                    selected = payload
                    break
            else:
                selected = {"verdict": "NEUTRAL", "confidence": 0.0}

            class _Block:
                text = json.dumps(selected)

            return type("Resp", (), {"content": [_Block()]})()

    return _MockClient()


def _run(implementation: str, client: Any) -> BenchmarkSummary:
    rows: list[BenchmarkRow] = []
    for expected, claim, evidence in SYNTHETIC_PAIRS:
        verdict = score_pair(
            claim_sentence=claim,
            evidence_span=evidence,
            client=client,
        )
        rows.append(
            BenchmarkRow(
                expected=expected,
                predicted=verdict.verdict,
                confidence=verdict.confidence,
                correct=(verdict.verdict == expected),
            )
        )
    correct = sum(1 for row in rows if row.correct)
    return BenchmarkSummary(
        implementation=implementation,
        total_pairs=len(rows),
        correct=correct,
        accuracy=correct / max(len(rows), 1),
        rows=rows,
    )


def main() -> int:
    control = _run("control_no_faithfulness", _control_score_pair_factory())
    treatment = _run("faithfulness_uq_mocked", _treatment_score_pair_factory())
    summary = {
        "paper": "arXiv:2505.21072",
        "feature_flag": "PRAVIAR_FAITHFULNESS_UQ_ENABLED",
        "control": asdict(control),
        "treatment": asdict(treatment),
        "accuracy_delta": treatment.accuracy - control.accuracy,
        "notes": (
            "Deterministic synthetic smoke fixture; not empirical performance or "
            "release evidence. A separate opt-in real-model experiment lives in "
            "api/tests/test_faithfulness_uq.py."
        ),
    }
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
