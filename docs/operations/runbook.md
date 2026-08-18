# Praviar Runbook

> [!WARNING]
> Unvalidated reference design. This is not a supported operating procedure,
> production approval, or evidence of a deployed service.

## Local Setup

1. Install frontend dependencies with `pnpm install`.
2. Install API and pipeline packages in editable mode inside their local environments.
3. Start the frontend with `cd web && pnpm dev`.
4. Start the API with `cd api && APP_ENV=dev uvicorn api.main:app --reload`.
5. Run `cd api && PYTHONPATH=src python -m api.cli seed-dev-db` after applying migrations for a local dev org.

## Change checks

- Run the smallest relevant local checks for changed code.
- Web changes should pass formatting, lint, type checks, and focused tests.
- API changes should pass import/startup checks, focused tests under
  `APP_ENV=test`, and contract generation when schemas change.
- Pipeline changes must keep runtime code separate from research-only tooling
  and exercise the affected failure or abstention path.
- A local check proves only what it executed; it is not operational, legal, or
  deployment evidence.

## Schema-change reference

1. Export OpenAPI and regenerate shared types when contract surfaces change.
2. Review Alembic migrations independently before applying them anywhere.
3. Test compatibility, backup, restore, and rollback in an isolated environment.
4. Do not infer deployment safety from repository tests.

## Incident Debugging

1. Reproduce under the correct environment contract: `APP_ENV=dev|test|prod`.
2. Confirm whether the issue is runtime (`web/`, `api/`, `praviar_pipeline/src/praviar_pipeline/`) or research-only.
3. Check router importability and app startup before deeper endpoint debugging.
4. Verify worker cancellation and terminal-state handling before retrying failed analyses.
