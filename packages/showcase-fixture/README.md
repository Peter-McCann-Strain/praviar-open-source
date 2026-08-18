# Praviar showcase fixture

This internal package owns one deterministic, wholly fictional data contract for
future portfolio captures and cross-language fixture work. It contains no real
compound structure, patent record, customer matter, provider response, or legal
conclusion.

The package exposes the same JSON document and payload-digest algorithm to
Python and TypeScript. The public web showcase, development API seed, and
explicit pipeline dry-run project this contract into their own schemas and
record its receipt. Production analysis does not import or fall back to the
fixture.

## Integrity contract

`sha256-canonical-json-payload-v1` hashes UTF-8 JSON with recursively sorted
Unicode code-point keys and no insignificant whitespace. To remain identical in
Python and JavaScript, values are limited to JSON nulls, strings, booleans, safe
integers, arrays, and plain objects. Floating-point values and integers outside
JavaScript's safe range fail closed.

Python's `load_fixture()` verifies the recorded payload digest by default. The
TypeScript surface provides `verifyShowcaseFixtureDigest()` for the same check.
The JSON Schema supplies the structural contract; run the development tests
with the optional `jsonschema` dependency before changing the fixture.

```bash
(cd packages/showcase-fixture && python -m pytest -q)
(cd packages/showcase-fixture && pnpm test && pnpm type-check)
```

This fixture is demonstration data, not legal advice, ground truth, or evidence
of live end-to-end operation.
