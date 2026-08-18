# OCSR Ensemble: Research-Preview Architecture

This note describes the drawing-recognition path implemented in the current
source tree. It is an architecture reference, not a model card, benchmark
report, production-readiness attestation, or claim of state-of-the-art
performance.

## Release posture

Drawing-derived structure evidence remains governed research-preview
functionality. It can affect a run only when all of the following are true:

- the rollout state is explicitly `beta` or `production`;
- the reviewed drawing-evidence gate has passed;
- at least one jurisdiction is explicitly allowed; and
- the calibration artefact and runtime bindings verify successfully.

Internal and shadow modes may collect diagnostic evidence, but that evidence
does not influence triage, claim analysis, or risk output. A live rollout
fails closed when its acquisition, segmentation, OCSR, calibration, or
governance prerequisites fail. These controls are implemented in
`src/praviar_pipeline/pipeline/drawing_rollout.py`,
`src/praviar_pipeline/ocsr/calibration_contract.py`, and the drawing
orchestration modules.

No benchmark result is asserted by this document. Historical experiment
outputs, partial runs, and manually assembled comparisons are not release
evidence. They must not be used to infer accuracy, latency, generalisation,
legal correctness, or production coverage.

## Processing path

The runtime separates evidence acquisition from decision influence:

1. Patent documents and page images are acquired through configured sources.
2. Page-level segmentation proposes regions that may contain chemical
   drawings.
3. Drawing classification routes supported regions to one or more configured
   OCSR workers.
4. Each worker returns a structured prediction with validity and confidence
   availability recorded explicitly.
5. Candidate structures are normalised and checked for parseability before
   they participate in fusion.
6. The ensemble applies the configured fusion strategy, optionally using
   formula, text, label, or beam-candidate context.
7. The fused structure passes shared confidence and heavy-atom resolution
   gates. A missing confidence, malformed SMILES, low confidence, or excessive
   atom count produces an unresolved result rather than a guessed structure.
8. Specialist and aggregate drawing evidence may be retained with provenance.
9. The rollout governor either admits that evidence to decisioning or keeps it
   shadow-only.

The complete phase relationship, including text and metadata fusion, is shown
in the [vision evidence-fusion diagram](../../docs/architecture/src/10-vision-evidence-fusion.md).

## Fusion contract

`src/praviar_pipeline/ocsr/ensemble.py` exposes four configured strategies:

- `confidence_cascade` attempts a governed high-confidence resolution and
  falls through to voting when it cannot resolve safely;
- `majority_vote` groups canonical connectivity and accounts for agreement;
- `weighted_majority` uses configured model weights; and
- `best_single` selects the strongest admissible candidate.

The runtime roster is configuration-bound. This document deliberately does
not promise a fixed number of models or imply that every worker is installed,
licensed, calibrated, or enabled in every deployment. Isolated worker entry
points live under `src/praviar_pipeline/ocsr/workers/`; their presence in
source is not evidence that a deployment is authorised to execute the
corresponding model.

After fusion, `apply_resolution_gates()` applies the same safety policy to
ensemble, shortcut, and specialist paths. Live calibration is loaded through
the verified calibration contract rather than accepting unbound confidence
parameters. The result records whether confidence is available, so a numeric
transport sentinel cannot be mistaken for calibrated evidence.

## Evidence required for a performance claim

A publishable OCSR result needs a separately reviewed, immutable benchmark
record that binds at least:

- dataset name, licence, revision, sample identifiers, and split definition;
- model identities, weight digests, runtime roster, and dependency
  environment;
- preprocessing, segmentation, normalisation, fusion, and threshold settings;
- the metric definition, denominator, abstention policy, and failure handling;
- per-sample outputs sufficient to reproduce the aggregate result;
- hardware and timing methodology for latency claims; and
- the source revision and verification commands.

Comparisons with external work additionally require compatible datasets,
splits, metrics, and evaluation policies plus direct citations. Without those
bindings, the appropriate language is exploratory rather than comparative.

## Verification surfaces

The implementation is covered by focused tests for fusion, calibration,
resolution gates, rollout governance, orchestration, and production-evidence
binding. Relevant test modules include:

- `tests/test_ensemble_gates.py`
- `tests/test_drawing_cascade.py`
- `tests/test_drawing_rollout.py`
- `tests/test_drawing_orchestration.py`
- `tests/test_vision_execution_contract.py`
- `tests/test_vision_production.py`

Run these tests from `praviar_pipeline/` with the repository's documented test
environment. Passing implementation tests establish contract behaviour; they
do not establish model accuracy or legal suitability.
