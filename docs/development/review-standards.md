# Code Review Guidelines

## Architecture Rules
- All API routes must use `get_current_user` dependency for authentication
- All database queries must be scoped to `org_id` (multi-tenant isolation)
- No hardcoded values — all configuration via Settings/environment variables
- No silent exception swallowing — all errors logged at error level with exc_info
- No fallback behavior — errors must propagate and be visible

## Security (Always Check)
- New API endpoints have proper authentication and authorization
- Database queries use parameterized statements (SQLAlchemy ORM handles this)
- No secrets, API keys, or credentials in code or comments
- Input validation on all user-facing endpoints
- CORS configuration is explicit (no wildcards in production)
- Rate limiting applied to public-facing and resource-intensive endpoints

## Python Backend
- Use `async`/`await` consistently — no blocking calls in async context
- Pydantic models for all request/response schemas
- Structured logging via `structlog` — no f-string log messages
- Type hints on all function signatures
- Use `from __future__ import annotations` for forward references

## TypeScript Frontend
- Use Server Components by default, `"use client"` only when needed
- React Query for all API data fetching (no raw fetch in components)
- Zustand for client-side state that doesn't come from the API
- CSS variables for all colors — no hardcoded Tailwind color classes
- Accessible: proper aria labels, keyboard navigation, focus management

## Testing
- New API routes need at least one happy-path test
- New pipeline steps need unit tests with mocked LLM responses
- Frontend components with logic need Vitest tests
- E2E flows need Playwright coverage

## Style
- Prefer early returns over nested conditionals
- Keep functions focused; extract helpers when a block has a distinct concern or is hard to test
- No commented-out code — delete it (git has history)
- Imports: stdlib → third-party → local, alphabetized within groups

## Skip
- Generated files under `web/.next/`
- Lock files (`pnpm-lock.yaml`, `package-lock.json`)
- Migration files under `api/alembic/versions/`
- Test fixture data files
