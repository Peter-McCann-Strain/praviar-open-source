import type { ConsoleMessage, JSHandle } from "@playwright/test";

export type ConsoleDiagnosticType = "error" | "warning";

export type ConsoleDiagnosticSetDiff = {
  missing: string[];
  unexpected: string[];
};

function diagnosticArgument(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  ) {
    return String(value);
  }
  if (value === null) return "null";
  return null;
}

/**
 * Produces one stable, exact app-owned diagnostic identity. Console metadata is
 * deliberately excluded after the first two arguments: logError emits source,
 * message, and then redacted structured context. The source and message are the
 * diagnostic contract; query keys and other context are provenance, not identity.
 */
export function exactConsoleDiagnosticIdentity({
  args,
  fallbackText,
  type,
}: {
  args: readonly unknown[];
  fallbackText: string;
  type: ConsoleDiagnosticType;
}): string {
  const identityArguments = args
    .slice(0, 2)
    .map(diagnosticArgument)
    .filter((value): value is string => value !== null);
  const message =
    identityArguments.length > 0
      ? identityArguments.join(" ")
      : fallbackText.trim();
  return `${type}: ${message}`;
}

async function jsonValue(handle: JSHandle): Promise<unknown> {
  try {
    return await handle.jsonValue();
  } catch {
    return undefined;
  }
}

export async function captureConsoleDiagnosticIdentity(
  message: ConsoleMessage,
): Promise<string> {
  const type = message.type();
  if (type !== "error" && type !== "warning") {
    throw new Error(`Unsupported visual-matrix console diagnostic: ${type}`);
  }
  const args = await Promise.all(message.args().slice(0, 2).map(jsonValue));
  return exactConsoleDiagnosticIdentity({
    args,
    fallbackText: message.text(),
    type,
  });
}

export function consoleDiagnosticSetDiff(
  actual: readonly string[],
  expected: readonly string[],
): ConsoleDiagnosticSetDiff {
  const counts = (identities: readonly string[]) => {
    const result = new Map<string, number>();
    for (const identity of identities) {
      result.set(identity, (result.get(identity) ?? 0) + 1);
    }
    return result;
  };
  const actualCounts = counts(actual);
  const expectedCounts = counts(expected);
  const identities = new Set([
    ...actualCounts.keys(),
    ...expectedCounts.keys(),
  ]);
  const missing: string[] = [];
  const unexpected: string[] = [];
  for (const identity of identities) {
    const difference =
      (actualCounts.get(identity) ?? 0) - (expectedCounts.get(identity) ?? 0);
    if (difference > 0) unexpected.push(...Array(difference).fill(identity));
    if (difference < 0) missing.push(...Array(-difference).fill(identity));
  }
  return {
    missing: missing.sort(),
    unexpected: unexpected.sort(),
  };
}

export function strictConsoleAllowance(identity: string): string {
  return identity.replace(/^(?:error|warning):\s*/u, "");
}
