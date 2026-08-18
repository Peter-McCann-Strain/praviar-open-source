import type { Request, Response } from "@playwright/test";

type MatrixApiRequest = Pick<Request, "failure" | "method" | "url">;
type MatrixApiResponse = Pick<Response, "ok" | "request" | "status" | "url">;

function httpUrl(request: Pick<Request, "url">): URL | null {
  try {
    const url = new URL(request.url());
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

/**
 * Tracks every application API request for one capture surface. The same
 * tracker remains active before and after state-specific browser actions so a
 * late GET, mutation, or CORS preflight failure cannot escape the screenshot
 * evidence gate.
 */
export class VisualMatrixApiTracker {
  readonly pendingRequests = new Set<MatrixApiRequest>();
  readonly pendingHttpRequests = new Set<MatrixApiRequest>();
  readonly nonApiResponseFailures: string[] = [];
  readonly #failureEvents: Array<{
    identity: string;
    supersededGetKey?: string;
  }> = [];
  readonly #successfulRequestKeys = new Set<string>();
  activityVersion = 0;
  requestCount = 0;

  readonly #applicationApiOrigin: string;

  constructor(applicationApiOrigin: string) {
    const url = new URL(applicationApiOrigin);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      throw new Error(
        `Visual matrix API origin must be HTTP(S), received ${applicationApiOrigin}`,
      );
    }
    this.#applicationApiOrigin = url.origin;
  }

  get failures(): string[] {
    return this.#failureEvents
      .filter(
        ({ supersededGetKey }) =>
          !supersededGetKey ||
          !this.#successfulRequestKeys.has(supersededGetKey),
      )
      .map(({ identity }) => identity);
  }

  #requestKey(request: Pick<Request, "method" | "url">): string {
    const url = new URL(request.url());
    return `${request.method()} ${url.pathname}${url.search}`;
  }

  #isAppApiRequest(request: Pick<Request, "url">): boolean {
    const url = httpUrl(request);
    return (
      url !== null &&
      url.origin === this.#applicationApiOrigin &&
      url.pathname.startsWith("/api/")
    );
  }

  startSurface(): void {
    if (this.pendingHttpRequests.size > 0) {
      throw new Error(
        "Cannot start a visual-matrix surface with pending HTTP requests",
      );
    }
    this.#failureEvents.length = 0;
    this.#successfulRequestKeys.clear();
    this.nonApiResponseFailures.length = 0;
    this.requestCount = 0;
  }

  requestStarted(request: MatrixApiRequest): void {
    if (httpUrl(request)) {
      this.pendingHttpRequests.add(request);
      this.activityVersion += 1;
    }
    if (!this.#isAppApiRequest(request)) return;
    this.requestCount += 1;
    this.pendingRequests.add(request);
  }

  requestFinished(request: MatrixApiRequest): void {
    if (this.pendingHttpRequests.delete(request)) this.activityVersion += 1;
    this.pendingRequests.delete(request);
  }

  requestFailed(request: MatrixApiRequest): void {
    if (this.pendingHttpRequests.delete(request)) this.activityVersion += 1;
    if (!this.#isAppApiRequest(request)) return;
    this.pendingRequests.delete(request);
    const errorText = request.failure()?.errorText ?? "failed";
    this.#failureEvents.push({
      identity: `${request.method()} ${new URL(request.url()).pathname} ${errorText}`,
      supersededGetKey:
        request.method() === "GET" && errorText === "net::ERR_ABORTED"
          ? this.#requestKey(request)
          : undefined,
    });
  }

  responseReceived(response: MatrixApiResponse): void {
    const request = response.request();
    if (httpUrl(request)) this.activityVersion += 1;
    if (response.ok()) {
      if (this.#isAppApiRequest(request)) {
        this.#successfulRequestKeys.add(this.#requestKey(request));
      }
      return;
    }
    if (this.#isAppApiRequest(request)) {
      this.#failureEvents.push({
        identity: `${request.method()} ${new URL(response.url()).pathname} HTTP ${response.status()}`,
      });
      return;
    }
    if (response.status() < 400) return;
    const url = new URL(response.url());
    if (url.protocol === "http:" || url.protocol === "https:") {
      this.nonApiResponseFailures.push(
        `${request.method()} ${url.origin}${url.pathname} HTTP ${response.status()}`,
      );
    }
  }
}
