# Contributing

Praviar is a research preview, not a legal-opinion system. Contributions must
preserve that boundary and must not introduce customer, privileged, personal,
or access-controlled patent data.

## Ground Rules

- Product runtime code belongs in `web/`, `api/`, and `praviar_pipeline/src/praviar_pipeline/`.
- Research code belongs in `research/`; do not add experimental tooling back into runtime paths.
- `APP_ENV` and `NEXT_PUBLIC_DEMO_MODE` are explicit contracts. Do not reintroduce implicit environment fallbacks.
- `packages/shared-types/src/generated.ts` is generated output. Regenerate it instead of hand-editing it.
- Tests that depend on optional extras (e.g. RDKit, PyTorch, OCSR weights) must gate with `pytest.importorskip` rather than being silently skipped or deleted.
- Do not commit model weights, downloaded datasets, saved Terraform plans,
  state, credentials, or generated analysis output.
- New third-party material needs primary-source provenance and an explicit
  redistribution decision in the applicable licence inventory.

## Local Workflow

```bash
# Frontend
(cd web && pnpm dev)
(cd web && pnpm test)

# API
(cd api && APP_ENV=test python -m pytest tests -q)
(cd api && PYTHONPATH=src python -m api.cli export-openapi)

# Pipeline
(cd praviar_pipeline && python -m pytest tests -q)

# Shared contracts
bash scripts/generate-types.sh

```

## Before Opening A PR

1. Run the tests for the surfaces you changed.
2. Regenerate shared types if you changed report models.
3. Update the canonical docs in `docs/` when runtime commands, env contracts, or repo boundaries change.
4. Keep research-only assets out of deploy-gating paths.
5. Treat a new unknown or restricted dependency-licence finding as a review
   item. Document the exact package, terms, distribution posture, and primary
   evidence instead of assuming public availability permits redistribution.

## Licensing contributions

Unless you conspicuously mark a submission otherwise before it is accepted,
intentional contributions are submitted under Apache-2.0 as described in
section 5 of `LICENSE`. By contributing, you confirm that you have the right to
submit the work and its included data or assets under those terms. Third-party
material must retain its own notices and may be rejected when its rights are
unclear.

## Ownership

See [`.github/CODEOWNERS`](.github/CODEOWNERS) for review ownership and [`docs/architecture/adr-001-repo-boundaries.md`](docs/architecture/adr-001-repo-boundaries.md) for the repo boundary policy.
