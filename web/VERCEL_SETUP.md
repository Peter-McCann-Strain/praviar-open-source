# Vercel reference deployment — research preview

This document is an evaluation runbook, not a production-deployment approval.
The public repository does not contain evidence of a linked Vercel project,
successful Vercel deployment, custom domain, or production traffic. Praviar is
published as a research preview; deploying the web application does not turn its
outputs into legal advice or an FTO opinion.

## Current repository contract

The checked-in configuration delegates package installation, framework build,
and output-directory selection to Vercel's monorepo and Next.js detection. A
remote build still has to prove that Vercel found the repository-root lockfile
and the declared package-manager version on the exact revision being evaluated.

| Surface                  | Current, inspectable state                                                                                                                                                                |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Monorepo package manager | [`package.json`](../package.json) declares `pnpm@9.15.4`; [`pnpm-lock.yaml`](../pnpm-lock.yaml) is lockfile version 9 and [`pnpm-workspace.yaml`](../pnpm-workspace.yaml) includes `web`. |
| Validation               | No hosted build is supplied or claimed by this archive. A downstream evaluator must run and record the checks appropriate to its own revision and environment.                            |
| Vercel commands          | [`vercel.json`](./vercel.json) does not override `installCommand`, `buildCommand`, or `outputDirectory`; Vercel must detect the root pnpm workspace and Next.js project defaults.         |
| Next.js output           | [`next.config.ts`](./next.config.ts) sets `output: "standalone"`; no Vercel output override competes with the framework default.                                                          |
| Regions                  | `vercel.json` does not pin regions. No regional-placement claim is made here.                                                                                                             |
| External redirects       | `vercel.json` publishes no external redirect. A deployer must not add one without proving control of the destination.                                                                     |
| Git deployments          | `git.deploymentEnabled` is `false`, disabling Git-connected deployments; `github.autoAlias` is also `false`. Manual preview deployment remains an explicit external action.               |
| Research posture         | The repository contains a working open-source research system; this deployment document remains an unvalidated reference design.                                                          |

Vercel detects a package manager from the repository lockfile and can use the
root `packageManager` field through Corepack. See Vercel's
[package-manager documentation](https://vercel.com/docs/package-managers) and
[monorepo documentation](https://vercel.com/docs/monorepos).

## Local verification

Run the supported build path from the repository root:

```bash
corepack enable
pnpm install --frozen-lockfile
pnpm lint
pnpm type-check
pnpm test
pnpm --filter web build
```

The production build requires a non-local `NEXT_PUBLIC_APP_URL`, a valid Clerk
publishable key, and the remaining environment contract described below. Use
owner-controlled test credentials in a local secret store; do not put
credentials in shell history or commit an environment file. Use only
non-secret `.example` origins for isolated build evaluation.

This local sequence can reveal source-build errors. It does not prove Vercel
account configuration, DNS, runtime secrets, backend reachability, security, or
a remote deployment.

## Preconditions for a Vercel evaluation

Before creating even a preview deployment:

1. Prove from the preview build log that automatic detection used the
   repository-root `pnpm-lock.yaml` without mutation and selected the declared
   `pnpm@9.15.4` toolchain. Do not add an install-command override as a substitute
   for that evidence.
2. Configure the Vercel project as a monorepo project whose Root Directory is
   `web`, while retaining access to the repository-root workspace and lockfile.
3. Use a protected Preview environment first. Do not attach a production domain
   and do not run `vercel --prod` during evaluation.
   Keep Git-connected automatic deployment disabled; the checked-in
   `git.deploymentEnabled: false` and `github.autoAlias: false` contracts must
   remain unchanged during evaluation.
4. Configure environment variables in Vercel, scoped separately to Preview and
   Production. Environment changes apply only to later deployments; see
   [Vercel environment variables](https://vercel.com/docs/environment-variables).
5. Configure the FastAPI backend with the exact preview origin when live API mode
   is tested. Do not use a wildcard `*.vercel.app` CORS claim: the backend uses an
   explicit-origin allowlist with credentials.

## Environment contract

All `NEXT_PUBLIC_*` values are embedded into browser-delivered code and are not
secrets.

| Variable                                       | Preview requirement                                                                                                                                                   |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_APP_URL`                          | Required for a production-mode Next.js build. Set it to the stable, non-local HTTPS origin being evaluated; it controls canonical metadata, robots, and sitemap URLs. |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`            | Required and format-validated in production mode. Use an owner-controlled Clerk test instance for a protected preview.                                                |
| `CLERK_SECRET_KEY`                             | Required by the production runtime for protected routes. Store only as a Vercel secret.                                                                               |
| `NEXT_PUBLIC_DEMO_MODE`                        | Set to `true` only for the fictional research-preview fixture experience. Demo mode does not bypass production Clerk requirements.                                    |
| `NEXT_PUBLIC_API_URL`                          | Required when demo mode is not `true`. Must be the approved remote HTTPS FastAPI origin only, with no credentials, path, query, or fragment.                          |
| `NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS`            | Leave unset or `false`. The bypass is local-development-only and is rejected as a production strategy.                                                                |
| `NEXT_PUBLIC_ENABLE_AUTH_BOUNDARY_TEST_BRIDGE` | Leave unset or `false`; this is a test-only boundary.                                                                                                                 |
| `NEXT_PUBLIC_SENTRY_DSN`                       | Optional browser telemetry. Configure only after privacy, retention, and environment tagging are approved.                                                            |
| `NEXT_PUBLIC_CLERK_DOMAIN`                     | Optional Clerk custom-domain input. If set, it must be a non-local DNS hostname only—no scheme, credentials, port, path, query, fragment, or wildcard.                |

Never place API secrets, model credentials, database URLs, signing keys, or Clerk
secret keys in a `NEXT_PUBLIC_*` variable.

## Preview-only evaluation sequence

Only after the package-manager precondition is resolved, link and build from the
monorepo root using a current Vercel CLI:

```bash
vercel link --repo
vercel pull --yes --environment=preview
vercel build
vercel deploy --prebuilt
```

These commands create external state and can expose a deployment. Run them only
in the intended Vercel account. Do not add `--prod` until the preview evidence
below has been reviewed and an owner explicitly approves promotion. Vercel's
[deployment overview](https://vercel.com/docs/deployments/overview) describes
preview and production deployments.

## Required preview evidence

Record the source revision, deployment ID, immutable preview URL, build log, and
the reviewer who accepted each result. At minimum, verify:

- the deployed revision is the intended reviewed archive revision;
- the install log uses the repository pnpm lockfile without mutation;
- the home page and sample report visibly say research preview, use only the
  canonical fictional `Example Molecule Alpha` data, and retain the no-legal-advice
  boundary;
- authenticated and unauthenticated route behavior matches the Clerk policy;
- `NEXT_PUBLIC_DEMO_MODE=true` never contacts the production API;
- live API mode reaches only the configured API origin and CORS accepts only the
  exact web origin;
- CSP, HSTS, `X-Content-Type-Options`, frame denial, referrer policy, and
  permissions policy are present on representative responses;
- `/robots.txt`, `/sitemap.xml`, Open Graph metadata, and canonical URLs use the
  evaluated origin;
- no route redirects to an unverified external hostname;
- no credential, private evidence, real customer data, model weight, or
  attorney-client material appears in HTML, JavaScript, source maps, logs, or
  network responses; and
- the verified deployment can be rolled back without rebuilding.

Apply [Deployment Protection](https://vercel.com/docs/deployment-protection) to
preview URLs. Protection behavior and plan availability change over time, so the
operator must review the current Vercel terms rather than relying on a price or
plan claim in this repository.

## Promotion gate

A Vercel production deployment remains blocked until all of the following are
true:

- the automatically detected pnpm install and remote build are reproducible;
- the evaluator's documented local and remote checks pass for the exact revision;
- preview runtime and browser evidence is archived and independently reviewed;
- the owner approves the environment, domain, DNS, protection, monitoring,
  privacy, CORS, rollback, and incident-response configuration;
- all public content remains within the research-preview and fictional-data
  boundary; and
- no documentation describes the deployment as legal clearance, production
  validation, or commercial readiness without separate evidence.

No production deployment command is endorsed by the current repository state.
