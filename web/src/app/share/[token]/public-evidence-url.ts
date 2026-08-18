const PUBLIC_EVIDENCE_HOSTS = new Set([
  "patents.google.com",
  "worldwide.espacenet.com",
  "register.epo.org",
  "patentscope.wipo.int",
  "patentcenter.uspto.gov",
  "ppubs.uspto.gov",
]);

export function sanitizePublicEvidenceUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }

  try {
    const url = new URL(value.trim());
    const hostname = url.hostname.toLowerCase().replace(/\.$/, "");
    if (
      url.protocol !== "https:" ||
      url.username.length > 0 ||
      url.password.length > 0 ||
      (url.port.length > 0 && url.port !== "443") ||
      !PUBLIC_EVIDENCE_HOSTS.has(hostname)
    ) {
      return null;
    }

    url.protocol = "https:";
    url.hostname = hostname;
    url.port = "";
    url.hash = "";
    return url.toString();
  } catch {
    return null;
  }
}
