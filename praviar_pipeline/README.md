# Chemical patent-evidence pipeline

The `praviar_pipeline` package is the original internal namespace for a working
chemistry-aware patent-evidence runtime. It resolves a compound, retrieves and ranks candidate material,
structures claim evidence, records uncertainty and provenance, and produces a
report for qualified human review.

> [!CAUTION]
> This package does not provide legal advice, a freedom-to-operate opinion, or
> a guarantee that relevant rights were found. Its outputs require source-level
> review by qualified counsel. No public, independently adjudicated evaluation
> currently establishes legal accuracy or a false-clear rate.

## Runtime shape

The public architecture describes eight user-facing stages:

1. resolve chemical identity and query context;
2. search, normalize, rank, and group candidate patent families;
3. triage candidates for structured review;
4. analyze claims through one adaptive path;
5. screen doctrine-of-equivalents issues for counsel;
6. screen potential invalidity material without reaching a legal conclusion;
7. verify structured output and expose failures; and
8. build a provenance-bearing report and review artefacts.

The implementation uses finer internal checkpoints than this presentation.
Checkpoint numbering is a recovery contract, not an additional claim about
analysis quality. See the repository's [pipeline architecture](../docs/architecture/src/04-evidence-pipeline.md)
and [detailed implementation reference](../docs/PIPELINE.md).

## Design properties

- Pydantic contracts govern configuration, intermediate state, and reports.
- One adaptive execution profile escalates internally when evidence gates or
  uncertainty require it; callers do not select a legal-accuracy mode.
- Retrieval, model output, and structure similarity remain evidence inputs,
  not claim construction.
- Failed sources and incomplete coverage remain visible instead of silently
  becoming a lower-quality success.
- Optional OCSR/model influence fails closed when licence, provenance,
  checksum, size, or runtime prerequisites are unapproved or unavailable.
- Reports retain citations, source spans, limitations, cost records, and
  verification outcomes for reviewer inspection.

## Local setup

```bash
cd praviar_pipeline
python -m venv .venv
source .venv/bin/activate
python -m pip install --editable '.[dev]'

# Configuration-only check; does not establish source coverage or accuracy.
praviar-pipeline validate

# Run the test suite.
python -m pytest tests
```

Live analysis requires an explicit `APP_ENV` and the credentials for every
configured provider. Review `.env.example` as a schema, but do not commit a
populated environment file. Provider calls may incur cost and may send matter
data outside the local machine; do not use confidential inputs without an
approved deployment and data-handling review.

`SOURCE_CONTACT_EMAIL` is an optional deployment-operator identity for
scientific APIs that request one. The research-preview source does not assume
that a Praviar domain or support mailbox exists; leave the field blank for
local evaluation, or configure an address the operator actually controls.

## Command line

```bash
# Live provider-backed execution; review configuration, rights, and cost first.
praviar-pipeline run "aspirin" --format json

# Local configuration check.
praviar-pipeline validate

# Inspect optional model policy. This never downloads a model.
praviar-pipeline models list

# Verify a previously approved and installed model artifact.
praviar-pipeline models verify <model-id>
```

The shipped model registry is deny-by-default. Current entries are upstream
links with activation blocked because their commercial-use or checkpoint
rights have not been approved for this distribution. `models fetch` and
`models register-local` fail closed unless a future registry entry has an
approved licence/use decision, immutable revision, exact size, SHA-256, and
explicit acknowledgement. See [`MODEL_LICENSES.md`](../MODEL_LICENSES.md).

The legacy hosted-vision preflight has a separate ML-BOM attestation contract.
Its private default evidence file is deliberately absent from the public
snapshot, so that path fails closed unless a deployer supplies and verifies an
independently reviewed `PRAVIAR_ML_BOM_PATH`. The acquisition registry is not a
substitute for a hosted-production attestation.

## Evaluation status

The public code snapshot intentionally excludes private validation archives,
downloaded patent documents, third-party corpora, and controlled-pilot source
receipts. The checked-in public result index records:

- a 343-case dry-run invocation that attempted and scored no cases; and
- seven controlled-pilot launch records with zero completed and zero scored
  cases.

Those records demonstrate failure-preserving experiment bookkeeping, not
performance. Do not calculate or advertise an accuracy percentage from them.
Future evaluations need a preregistered, rights-cleared, independently reviewed
protocol and an immutable result format; neither is supplied as completed
accuracy evidence by this archive.

## Test boundaries

The test suite covers software behavior, schemas, deterministic decisioning,
provider adapters, failure handling, and report construction. Optional
dependency tests use explicit skips when their reviewed extras are absent.
The `drawings`, `embeddings`, `export`, and `regulatory` groups remain optional,
lock-inventoried integration surfaces. Their upstream terms require separate
review before installation or redistribution; this archive does not present
them as supported public install profiles.

Passing tests do not establish:

- complete patent retrieval or current legal status;
- correct claim construction or legal conclusions;
- independently measured false-clear performance;
- attorney approval, production reliability, or security certification; or
- rights to use third-party models, datasets, or provider content.

## Source layout

```text
praviar_pipeline/
├── src/praviar_pipeline/
│   ├── agents/       adaptive research and analysis agents
│   ├── clients/      chemistry, patent, literature, and provider adapters
│   ├── models/       Pydantic domain and report contracts
│   ├── pipeline/     staged orchestration, verification, and finalization
│   ├── prompts/      versioned model instructions
│   ├── rendering/    report and evidence renderers
│   ├── cli.py        runtime command dispatch
│   └── run.py        top-level pipeline orchestration
├── tests/            unit, contract, and integration tests
└── playbooks/        analysis playbooks
```

Repository-wide setup, licensing, and contribution rules live in the root
[`README.md`](../README.md) and [`CONTRIBUTING.md`](../CONTRIBUTING.md).
