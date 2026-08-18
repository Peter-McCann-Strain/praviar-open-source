# Chemical patent-analysis workbench

Next.js 16 frontend for the chemical patent-analysis and FTO evidence research
system. It provides a dashboard for submitting compounds, tracking
multi-phase analyses, reviewing evidence, and preparing structured research
reports for human review.

## Research posture

The workbench implements patent-landscape research and reviewer workflows. It
does not provide legal
advice, replace qualified counsel, or independently establish freedom to
operate. Report conclusions remain subject to source coverage, jurisdiction,
data freshness, pipeline configuration, and human review.

## Tech Stack

- **Framework:** Next.js 16 (App Router) with React 19
- **Styling:** Tailwind CSS v4 with the Praviar premium palette (Forensic Teal + Clinical Copper, plus Soft Mint wash)
- **Charts:** Recharts 3.8 (risk donuts, search funnels, timing waterfalls)
- **State:** Zustand 5 (config, pipeline, UI stores)
- **Data Fetching:** TanStack Query 5
- **Auth:** Clerk
- **Chemistry:** RDKit.js (WASM) for 2D molecule rendering and SMILES validation

## Getting started

```bash
cd ..
corepack enable
pnpm install --frozen-lockfile
pnpm demo       # http://localhost:3000
```

## Demo Mode

The app can run without a backend only when explicit demo mode is enabled.
The versioned fictional matter lives in
[`packages/showcase-fixture/`](../packages/showcase-fixture/); the web adapter in
[`src/lib/demo-data.ts`](./src/lib/demo-data.ts) projects it into local UI
states. Demo fixtures illustrate product states only; they are not benchmark
evidence, patent-status assertions, or legal conclusions.

## Project Structure

```
src/
  app/
    (auth)/           # Clerk sign-in/sign-up routes
    (dashboard)/      # Main app routes
      analyses/       # List, new, wizard, quick-start, detail, report
      config/         # Pipeline configuration
      dashboard/      # Overview dashboard
      help/           # Help & documentation
    share/            # Public shared-report route
  components/
    chemistry/        # MoleculeViewer2D, SmilesInput, FunctionalGroupBadges
    charts/           # RiskDonut, SearchFunnel, TimingWaterfall, UsageChart
    ui/               # Shared UI primitives
  hooks/              # Custom React hooks
  stores/             # Zustand stores (config, pipeline, ui)
  lib/                # Utilities, API client, demo data, constants
  proxy.ts            # Clerk auth proxy
```

## Environment Variables

| Variable                            | Purpose                                                                                                                                        |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk auth. Required outside explicit local demo/dev-auth sessions.                                                                            |
| `CLERK_SECRET_KEY`                  | Clerk server-side auth                                                                                                                         |
| `NEXT_PUBLIC_API_URL`               | Origin-only FastAPI URL. Required unless demo mode is enabled; production requires remote HTTPS with no credentials, path, query, or fragment. |
| `NEXT_PUBLIC_DEMO_MODE`             | Set to `true` to run the UI against built-in demo fixtures instead of the API.                                                                 |
| `NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS` | Set to `true` only for local API sessions that deliberately use the backend `ALLOW_DEV_AUTH_BYPASS=true` path.                                 |

## Part of the Praviar Monorepo

This package lives at `web/` in the Praviar monorepo. See the root README for the full project overview.
