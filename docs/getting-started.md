# Getting started

This is the shortest path into the working web interface. It starts the bundled
synthetic demonstration: no API, database, account, patent-source subscription,
or model provider is needed.

> [!WARNING]
> Use fictional data only. Do not enter confidential compounds, client matters,
> invention disclosures, personal data, or credentials.

## Requirements

- Git
- Node.js 20 or newer
- Corepack

## Install and run

```bash
git clone https://github.com/Peter-McCann-Strain/chemical-patent-analysis.git
cd chemical-patent-analysis
corepack enable
pnpm install --frozen-lockfile
pnpm demo
```

Open <http://localhost:3000/>. Useful demonstration routes are:

- <http://localhost:3000/sample-reports/example-molecule-alpha>
- <http://localhost:3000/analyses/new>
- <http://localhost:3000/analyses/ana_demo_001/report>
- <http://localhost:3000/reviews>
- <http://localhost:3000/capabilities>

Stop the server with `Ctrl+C`.

## What demo mode does

`pnpm demo` sets `NEXT_PUBLIC_DEMO_MODE=true` and starts the Next.js development
server. The interface reads the versioned fictional fixture in
[`packages/showcase-fixture/`](../packages/showcase-fixture/). It does not run a
patent search, call the FastAPI service, send input to a model provider, or
establish any fact about a real patent or compound.

## Troubleshooting

If `pnpm` is unavailable after enabling Corepack, confirm that `node --version`
reports version 20 or newer, then open a new shell and retry `corepack enable`.

If port 3000 is already in use, stop the other local server or run:

```bash
pnpm demo --port 3001
```

If installation reports a lockfile mismatch, do not use `--no-frozen-lockfile`.
Confirm that the clone is unchanged and retry with the package-manager version
pinned in the root `package.json`.

The provider-backed API and evidence pipeline are separate from this
credential-free interface tour. Read the [compound-to-report pipeline](PIPELINE.md),
[measured evaluation results](evaluation/README.md), and
[known limitations](limitations.md) before configuring live providers.
