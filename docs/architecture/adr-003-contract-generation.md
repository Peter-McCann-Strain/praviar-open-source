# ADR-003: Backend-Owned Contract Generation

## Status
Accepted

## Decision

- Backend and runtime Python models remain the source of truth for shared contracts.
- `packages/shared-types/src/generated.ts` is generated output.
- `packages/shared-types/src/index.ts` is only a stable barrel export.
- Contract regeneration is invoked through backend-owned CLI and root wrapper:
  - `cd api && PYTHONPATH=src python -m api.cli generate-shared-types`
  - `bash scripts/generate-types.sh`

## Consequences

- Contract drift becomes visible and reviewable.
- The repo no longer treats hand-edited shared report types as canonical.
- Future CI can block on generated-type drift without changing consumer imports.
