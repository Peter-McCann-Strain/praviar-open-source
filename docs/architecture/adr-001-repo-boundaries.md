# ADR-001: Runtime vs Research Repo Boundaries

## Status

Accepted

## Decision

- `web/`, `api/`, and `praviar_pipeline/src/praviar_pipeline/` are the product runtime surface.
- `research/` holds benchmarks, validation assets, experiments, and research tooling.
- `infra/terraform/` holds an unvalidated hosted-infrastructure reference.
- Stale historical material is removed from the active repo surface once it has a pushed git checkpoint; it does not stay adjacent to runtime code paths.

## Consequences

- Deploy-gating tests target runtime code, not research-only assets.
- Experimental scripts no longer share directories with production pipeline modules.
- Repo ownership and onboarding are clearer because directories now communicate intent directly.
