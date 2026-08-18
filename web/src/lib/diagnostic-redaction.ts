const DIAGNOSTIC_REDACTIONS: ReadonlyArray<[RegExp, string]> = [
  [/postgres(?:ql)?:\/\/[^\s)]+/gi, "[redacted connection string]"],
  [/\bsk_(?:live|test)_[A-Za-z0-9_=-]+/g, "[redacted API key]"],
  [/\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b/g, "[redacted API key]"],
  [/\bprv_live_[A-Za-z0-9_-]{43}\b/g, "[redacted API key]"],
  [/\bBearer\s+[A-Za-z0-9._=-]+/gi, "Bearer [redacted]"],
  [
    /\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g,
    "[redacted token]",
  ],
  [
    /\b((?:provider|database|service)\s+(?:secret|password|passwd|pwd|token|api[\s_-]?key|access[\s_-]?key|client[\s_-]?secret))\s*[:=]\s*(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\r\n;,]*)/gi,
    "$1: [redacted]",
  ],
  [
    /\b(password|passwd|pwd)\s*[:=]\s*(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s&;]+)/gi,
    "$1=[redacted]",
  ],
  [
    /\b(secret|token|api[\s_-]?key|access[\s_-]?key|client[\s_-]?secret)\s*[:=]\s*(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s&;]+)/gi,
    "$1: [redacted]",
  ],
  [
    /\b[A-Z0-9.!#$%&'*+/=?^_{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+\b/gi,
    "[redacted email]",
  ],
  [/\bSELECT\b[\s\S]*?\bFROM\b[^\n;.]+/gi, "[redacted query]"],
  [
    /\b(?:INSERT\s+INTO|UPDATE\s+[A-Za-z_][A-Za-z0-9_$]*(?:\.[A-Za-z_][A-Za-z0-9_$]*)*\s+SET|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE)\b[^\n;.]+/gi,
    "[redacted query]",
  ],
  [/Traceback[\s\S]*$/i, "Diagnostic details are available to support."],
  [
    /\bat\s+[A-Za-z0-9_.$<>/-]+(?:\s+\([^)]+\)|[^\n]*)/g,
    "[redacted stack frame]",
  ],
  [/(?:\/Users|\/var|\/tmp)\/[^\s)]+/g, "[redacted path]"],
  [/[A-Z]:\\[^\s)]+/g, "[redacted path]"],
];

const MAX_DIAGNOSTIC_LENGTH = 240;
const MAX_METADATA_DEPTH = 5;
const SENSITIVE_METADATA_KEY =
  /(?:^|_)(?:api_?key|authorization|body|compound(?:_input)?|detail|email|error(?:_detail|_message)?|message|password|payload|prompt|query|response_(?:body|data|payload|text)|secret|smiles|stack(?:_trace)?|token)(?:_|$)/i;

function isSensitiveMetadataKey(key: string): boolean {
  const normalized = key.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
  return SENSITIVE_METADATA_KEY.test(normalized);
}

export function sanitizeDiagnosticText(
  value: string | null | undefined,
  fallback: string,
): string {
  const source = value?.trim();
  if (!source) {
    return fallback;
  }

  const redacted = DIAGNOSTIC_REDACTIONS.reduce(
    (next, [pattern, replacement]) => next.replace(pattern, replacement),
    source,
  )
    .replace(/\s+/g, " ")
    .trim();

  if (!redacted) {
    return fallback;
  }

  return redacted.length > MAX_DIAGNOSTIC_LENGTH
    ? `${redacted.slice(0, MAX_DIAGNOSTIC_LENGTH - 3).trim()}...`
    : redacted;
}

export function sanitizeDiagnosticMetadata(value: unknown): unknown {
  return sanitizeMetadataValue(value, 0, new WeakSet<object>());
}

function sanitizeMetadataValue(
  value: unknown,
  depth: number,
  seen: WeakSet<object>,
): unknown {
  if (typeof value === "string") {
    return sanitizeDiagnosticText(value, "");
  }

  if (
    value == null ||
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  ) {
    return value;
  }

  if (value instanceof Error) {
    if (value.name === "APIError") {
      const status = (value as Error & { status?: unknown }).status;
      return {
        name: "APIError",
        ...(typeof status === "number" &&
        Number.isInteger(status) &&
        status >= 100 &&
        status <= 599
          ? { status }
          : {}),
      };
    }
    return {
      name: value.name,
      message: sanitizeDiagnosticText(
        value.message,
        "Error details available.",
      ),
    };
  }

  if (typeof value !== "object") {
    return String(value);
  }

  if (seen.has(value)) {
    return "[circular]";
  }

  if (depth >= MAX_METADATA_DEPTH) {
    return "[nested metadata]";
  }

  seen.add(value);

  if (Array.isArray(value)) {
    return value.map((item) => sanitizeMetadataValue(item, depth + 1, seen));
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      isSensitiveMetadataKey(key)
        ? "[redacted metadata]"
        : sanitizeMetadataValue(item, depth + 1, seen),
    ]),
  );
}
