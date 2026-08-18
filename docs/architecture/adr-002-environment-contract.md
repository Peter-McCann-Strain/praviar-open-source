# ADR-002: Explicit Environment Contract

## Status
Accepted

## Decision

- The API uses `APP_ENV=dev|test|prod`.
- Production-only secret validation and startup behavior happen only in `APP_ENV=prod`.
- Frontend demo behavior is controlled explicitly by `NEXT_PUBLIC_DEMO_MODE=true`.
- Missing `NEXT_PUBLIC_API_URL` is an error unless demo mode is enabled.

## Consequences

- Tests can import `create_app()` without production secrets.
- Local development and CI use explicit modes instead of inferring behavior from `debug=False`.
- Documentation and deployment configuration now share one environment vocabulary.
