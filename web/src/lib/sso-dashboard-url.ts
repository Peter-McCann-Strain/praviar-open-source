const CLERK_DASHBOARD_ORIGIN = "https://dashboard.clerk.com";
const CLERK_ORGANIZATION_SSO_PATH =
  /^\/organizations\/[^/?#]+\/sso-connections\/?$/;

function hasOnlyDemoMarker(url: URL): boolean {
  return (
    url.searchParams.size === 1 && url.searchParams.get("demo_sso") === "clerk"
  );
}

export function validatedClerkDashboardUrl(
  value: string | null | undefined,
  { demoMode, currentOrigin }: { demoMode: boolean; currentOrigin?: string },
): string | null {
  if (!value) return null;

  const candidate = value.trim();
  if (!candidate) return null;

  try {
    if (demoMode) {
      const browserOrigin =
        typeof window === "undefined" ? undefined : window.location.origin;
      const origin = currentOrigin ?? browserOrigin ?? "https://demo.invalid";
      const isRelativePath =
        candidate.startsWith("/") && !candidate.startsWith("//");
      if (!isRelativePath && !currentOrigin && !browserOrigin) return null;
      const url = new URL(candidate, origin);
      if (
        url.origin === origin &&
        url.pathname === "/settings" &&
        !url.username &&
        !url.password &&
        !url.hash &&
        hasOnlyDemoMarker(url)
      ) {
        return `${url.pathname}${url.search}`;
      }
    }

    const url = new URL(candidate);
    if (
      url.origin === CLERK_DASHBOARD_ORIGIN &&
      !url.username &&
      !url.password &&
      !url.search &&
      !url.hash &&
      CLERK_ORGANIZATION_SSO_PATH.test(url.pathname)
    ) {
      return url.toString();
    }
  } catch {
    return null;
  }

  return null;
}
