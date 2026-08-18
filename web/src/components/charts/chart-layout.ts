export function compactChartLabel(value: string, maxChars: number): string {
  if (value.length <= maxChars) {
    return value;
  }

  return `${value.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`;
}

export function estimateAxisWidth(
  labels: string[],
  minWidth: number,
  maxWidth: number,
): number {
  const longestLabel = labels.reduce(
    (longest, label) => Math.max(longest, label.length),
    0,
  );
  return Math.min(maxWidth, Math.max(minWidth, longestLabel * 7 + 22));
}

export function estimateTrailingLabelMargin(
  labels: string[],
  minMargin: number,
  maxMargin: number,
): number {
  const longestLabel = labels.reduce(
    (longest, label) => Math.max(longest, label.length),
    0,
  );
  return Math.min(maxMargin, Math.max(minMargin, longestLabel * 8 + 18));
}

export function minimumReadableChartHeight(
  requestedHeight: number,
  rowCount: number,
  rowHeight: number,
): number {
  if (rowCount === 0) {
    return requestedHeight;
  }

  return Math.max(requestedHeight, rowCount * rowHeight + 56);
}
