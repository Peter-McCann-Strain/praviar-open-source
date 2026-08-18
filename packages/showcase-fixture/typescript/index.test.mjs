import assert from "node:assert/strict";
import test from "node:test";

import {
  canonicalPayloadJson,
  payloadDigest,
  showcaseFixture,
  verifyShowcaseFixtureDigest,
} from "../.test-dist/typescript/index.js";

test("the TypeScript surface verifies the packaged fixture", async () => {
  assert.equal(await verifyShowcaseFixtureDigest(), true);
  assert.equal(
    await payloadDigest(showcaseFixture.payload),
    showcaseFixture.fixture_digest,
  );
});

test("canonical JSON follows Python Unicode code-point key ordering", () => {
  assert.equal(
    canonicalPayloadJson({ "\u{10000}": 1, "\ue000": 2 }),
    '{"":2,"𐀀":1}',
  );
  assert.equal(
    canonicalPayloadJson({ "2": 2, "10": 10 }),
    '{"10":10,"2":2}',
  );
});

test("canonical JSON rejects values that JSON cannot represent", () => {
  assert.throws(
    () => canonicalPayloadJson({ notJson: Number.NaN }),
    /requires safe integers/,
  );
  assert.throws(() => canonicalPayloadJson({ lossy: 2 ** 53 }), /requires safe integers/);
  assert.throws(() => canonicalPayloadJson({ ambiguous: 1.5 }), /requires safe integers/);
  assert.throws(
    () => canonicalPayloadJson({ malformed: "\ud800" }),
    /unpaired Unicode surrogates/,
  );
});
