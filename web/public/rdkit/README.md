# RDKit.js browser runtime

These two distribution files are vendored from the official
[`@rdkit/rdkit`](https://www.npmjs.com/package/@rdkit/rdkit/v/2025.3.4-1.0.0)
package, version `2025.3.4-1.0.0`:

- `dist/RDKit_minimal.js`
- `dist/RDKit_minimal.wasm`

The embedded runtime reports RDKit `2025.03.4`. The upstream package and RDKit
source are BSD-3-Clause; the required notice is in `LICENSE`. These files are
not covered by Praviar's Apache-2.0 licence.

`checksums.sha256` records the exact bytes reviewed for this repository. The
source-archive boundary pins the WebAssembly file and fails if it changes. To
verify the repository copy from the repository root, run
`shasum -a 256 -c web/public/rdkit/checksums.sha256`. To independently
reproduce the check, download the immutable package version with scripts
disabled, compare its `dist/` files, and review its bundled `LICENSE`:

```bash
audit_dir="$(mktemp -d)"
npm pack --ignore-scripts --pack-destination "$audit_dir" \
  @rdkit/rdkit@2025.3.4-1.0.0
tar -xzf "$audit_dir"/*.tgz -C "$audit_dir"
shasum -a 256 \
  "$audit_dir/package/dist/RDKit_minimal.js" \
  "$audit_dir/package/dist/RDKit_minimal.wasm"
```

Do not replace either file from an unversioned CDN URL. Update the version,
licence evidence, checksums, loader comment, and archive manifest together.
