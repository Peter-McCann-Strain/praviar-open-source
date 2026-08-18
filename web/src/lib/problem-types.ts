const PROBLEM_TYPE_PATH = /^\/[a-z0-9]+(?:-[a-z0-9]+)*$/u;

export const PROBLEM_TYPE_BASE_URI = "https://problems.praviar.invalid/";

const problemType = (slug: string) =>
  `${PROBLEM_TYPE_BASE_URI}${slug}` as const;

export const PROBLEM_TYPES = {
  adminOperationTerminalFailure: problemType(
    "admin-operation-terminal-failure",
  ),
  analysisCapacityExhausted: problemType("analysis-capacity-exhausted"),
  capacityRequestAlreadyResolved: problemType(
    "capacity-request-already-resolved",
  ),
  insufficientCapacity: problemType("insufficient-capacity"),
} as const;

export function canonicalProblemTypeUri(value: unknown): string | undefined {
  if (value === "about:blank") return value;
  if (typeof value !== "string") return undefined;

  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return undefined;
  }
  const base = new URL(PROBLEM_TYPE_BASE_URI);
  if (
    parsed.protocol !== base.protocol ||
    parsed.hostname !== base.hostname ||
    parsed.username ||
    parsed.password ||
    parsed.port ||
    parsed.search ||
    parsed.hash ||
    !PROBLEM_TYPE_PATH.test(parsed.pathname)
  ) {
    return undefined;
  }
  return `${PROBLEM_TYPE_BASE_URI}${parsed.pathname.slice(1)}`;
}
