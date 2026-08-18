export function formatRelativeTime(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const isFuture = diff < 0;
  const minutes = Math.floor(Math.abs(diff) / 60_000);

  if (minutes < 1) return isFuture ? "soon" : "just now";
  if (minutes < 60) return isFuture ? `in ${minutes}m` : `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return isFuture ? `in ${hours}h` : `${hours}h ago`;

  const days = Math.floor(hours / 24);
  if (days < 30) return isFuture ? `in ${days}d` : `${days}d ago`;

  return new Date(isoDate).toLocaleDateString();
}

export async function copyTextToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    try {
      textarea.select();
      if (!document.execCommand("copy")) {
        throw new Error("Clipboard copy was not accepted");
      }
    } finally {
      textarea.remove();
    }
  }
}
