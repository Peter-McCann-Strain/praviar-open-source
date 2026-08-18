"use client";

export function formatSelectedJurisdictionCount(count: number): string {
  return `${count} jurisdiction${count === 1 ? "" : "s"} selected — the exact scope is recorded with the run`;
}

export function nextSearchJurisdictions(
  current: readonly string[],
  jurisdictionCode: string,
  checked: boolean,
): string[] | null {
  if (checked) {
    return current.includes(jurisdictionCode)
      ? [...current]
      : [...current, jurisdictionCode];
  }

  const next = current.filter((code) => code !== jurisdictionCode);
  return next.length > 0 ? next : null;
}
