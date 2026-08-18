export function relativeTime(date: string): string {
  const timestamp = new Date(date).getTime();
  if (Number.isNaN(timestamp)) {
    return "Unknown";
  }

  const diff = Math.max(0, Date.now() - timestamp);
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function ageInDays(date: string): number | null {
  const timestamp = new Date(date).getTime();
  if (Number.isNaN(timestamp)) {
    return null;
  }
  return Math.max(0, Math.floor((Date.now() - timestamp) / 86_400_000));
}

export function apiKeyRotationLabel(createdAt: string): string {
  const days = ageInDays(createdAt);
  if (days === null) {
    return "Review";
  }
  if (days >= 90) {
    return "Review now";
  }
  if (days <= 7) {
    return "Recently created";
  }
  return `${90 - days}d to review`;
}

export function apiKeyUsageLabel(lastUsedAt: string | null): string {
  if (!lastUsedAt) {
    return "Never used";
  }
  return relativeTime(lastUsedAt);
}

export function daysUntil(date: string): number | null {
  const timestamp = new Date(date).getTime();
  if (Number.isNaN(timestamp)) {
    return null;
  }
  return Math.ceil((timestamp - Date.now()) / 86_400_000);
}

export function isAPIKeyExpired(expiresAt: string): boolean {
  const days = daysUntil(expiresAt);
  return days !== null && days <= 0;
}

export function isAPIKeyExpiringSoon(expiresAt: string): boolean {
  const days = daysUntil(expiresAt);
  return days !== null && days > 0 && days <= 14;
}

export function apiKeyExpiryLabel(expiresAt: string): string {
  const days = daysUntil(expiresAt);
  if (days === null) {
    return "Unknown";
  }
  if (days <= 0) {
    return "Expired";
  }
  if (days === 1) {
    return "1d left";
  }
  if (days <= 14) {
    return `${days}d left`;
  }
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(expiresAt));
}

export function apiKeyScopeLabel(scope: string): string {
  switch (scope) {
    case "analyses:read":
      return "Read analyses";
    case "analyses:write":
      return "Create analyses";
    case "reports:read":
      return "Read reports";
    case "reports:export":
      return "Export reports";
    case "monitors:manage":
      return "Manage monitors";
    default:
      return scope;
  }
}

export function apiKeyPrefixLabel(prefix: string): string {
  return prefix.endsWith("...") ? prefix : `${prefix}...`;
}
