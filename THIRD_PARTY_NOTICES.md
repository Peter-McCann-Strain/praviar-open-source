# Third-party notices

Apache-2.0 applies only to Praviar-authored work. It does not relicense package
dependencies, model weights, datasets, generated media, vendored software,
patent documents, provider responses, or trademarks.

## Dependency inventories

Third-party dependencies retain the licences and notices published by their
authors. The checked-in lockfiles identify the versions selected by this
archive:

- `pnpm-lock.yaml` for JavaScript packages;
- `api/uv.lock` and `praviar_pipeline/uv.lock` for Python packages;
- `api/requirements/decimer.lock` and its adjacent checksum record for the
  isolated DECIMER environment;
- environment `.terraform.lock.hcl` files for Terraform providers.

The archive does not include a generated SBOM or a legal opinion on dependency
licences. Before redistribution or deployment, inspect the exact dependency
closure you intend to install, read the authoritative upstream terms, retain
required notices, and resolve unknown or restricted classifications. Lockfiles
and scanner output establish neither permission nor fitness for a particular
use.

Optional pipeline groups such as `drawings`, `embeddings`, `export`, and
`regulatory` can add dependencies with separate terms. Their presence in a
lockfile does not make them an approved or supported installation profile.

## Separately governed material

- The vendored RDKit.js browser runtime is BSD-3-Clause; its version, licence,
  source, and checksums are under `web/public/rdkit/`.
- Optional machine-learning artefacts are documented in `MODEL_LICENSES.md`.
- Visual and binary assets are documented in `ASSET_LICENSES.md`.
- Research inputs and outputs are not licensed merely because tooling that
  processes them is present.
- Praviar names and marks are governed by `TRADEMARKS.md`.

Report a missing or inaccurate attribution through the process in `SUPPORT.md`.
