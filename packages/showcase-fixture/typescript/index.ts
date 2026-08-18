import fixtureDocument from "../src/praviar_showcase_fixture/showcase.v1.json" with {
  type: "json",
};

export type EvidencePosture =
  | "no_blocker_identified_in_searched_record"
  | "review_required"
  | "potential_blocking_claim_identified";

export type ShowcasePayload = typeof fixtureDocument.payload;

export interface ShowcaseFixture {
  schema_version: "praviar.showcase.v1";
  fixture_id: "praviar-fictional-showcase";
  fixture_version: string;
  fixture_digest_algorithm: "sha256-canonical-json-payload-v1";
  fixture_digest: string;
  fictional: true;
  payload: ShowcasePayload;
}

function compareUnicodeCodePoints(left: string, right: string): number {
  const leftPoints = Array.from(left, (character) => character.codePointAt(0)!);
  const rightPoints = Array.from(right, (character) => character.codePointAt(0)!);
  const sharedLength = Math.min(leftPoints.length, rightPoints.length);
  for (let index = 0; index < sharedLength; index += 1) {
    if (leftPoints[index] !== rightPoints[index]) {
      return leftPoints[index]! - rightPoints[index]!;
    }
  }
  return leftPoints.length - rightPoints.length;
}

function assertWellFormedUnicode(value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const low = value.charCodeAt(index + 1);
      if (!(low >= 0xdc00 && low <= 0xdfff)) {
        throw new TypeError(
          "Canonical fixture JSON rejects unpaired Unicode surrogates",
        );
      }
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      throw new TypeError(
        "Canonical fixture JSON rejects unpaired Unicode surrogates",
      );
    }
  }
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) {
      throw new TypeError("Canonical fixture JSON requires safe integers");
    }
    return JSON.stringify(value);
  }
  if (value !== null && typeof value === "object") {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new TypeError("Canonical fixture JSON requires plain objects");
    }
    const entries = Object.entries(value as Record<string, unknown>);
    if (Reflect.ownKeys(value).length !== entries.length) {
      throw new TypeError(
        "Canonical fixture JSON requires enumerable string object keys",
      );
    }
    entries.sort(([left], [right]) => compareUnicodeCodePoints(left, right));
    return `{${entries
      .map(([key, nested]) => {
        assertWellFormedUnicode(key);
        return `${JSON.stringify(key)}:${canonicalJson(nested)}`;
      })
      .join(",")}}`;
  }
  if (value === null) {
    return "null";
  }
  if (typeof value === "string") {
    assertWellFormedUnicode(value);
    return JSON.stringify(value);
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  throw new TypeError(
    "Canonical fixture JSON permits only null, strings, booleans, " +
      "safe integers, arrays, and objects",
  );
}

export function canonicalPayloadJson(payload: unknown): string {
  return canonicalJson(payload);
}

export async function payloadDigest(payload: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalPayloadJson(payload));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

export async function verifyShowcaseFixtureDigest(
  fixture: ShowcaseFixture = showcaseFixture,
): Promise<boolean> {
  return (await payloadDigest(fixture.payload)) === fixture.fixture_digest;
}

export const showcaseFixture = fixtureDocument as ShowcaseFixture;

if (showcaseFixture.fictional !== true) {
  throw new Error("The Praviar showcase fixture must be explicitly fictional");
}
