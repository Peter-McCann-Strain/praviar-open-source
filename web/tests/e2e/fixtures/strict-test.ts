import {
  expect,
  test as base,
  type ConsoleMessage,
  type Page,
  type Request,
} from "@playwright/test";
import { sanitizeDiagnosticText } from "../../../src/lib/diagnostic-redaction";
import {
  isFatalConsoleDiagnostic,
  isProvenBenignNavigationReplacement,
} from "./browser-gate-policy";

type BrowserDiagnostic = {
  kind: "console" | "pageerror" | "requestfailed";
  message: string;
  severity?: string;
  url?: string;
};

const CRITICAL_RESOURCE_TYPES = new Set([
  "document",
  "script",
  "stylesheet",
  "font",
]);

type StrictTestOptions = {
  /** Exact diagnostic prefixes permitted by one intentionally failing test. */
  allowedConsoleErrorPrefixes: string[];
  /** Exact warning prefixes permitted by one intentionally warning test. */
  allowedConsoleWarningPrefixes: string[];
  /** Exact aborted-document URL pairs permitted by one redirecting test. */
  allowedNavigationReplacements: Array<{
    replacementUrl: string;
    requestUrl: string;
  }>;
};

function safeUrl(value: string): string {
  try {
    const url = new URL(value);
    return `${url.origin}${url.pathname}`;
  } catch {
    return value.split("?", 1)[0]?.slice(0, 500) ?? "[invalid URL]";
  }
}

function consoleDiagnostic(message: ConsoleMessage): BrowserDiagnostic {
  return {
    kind: "console",
    message: sanitizeDiagnosticText(
      message.text(),
      "Browser console diagnostic unavailable.",
    ),
    severity: message.type(),
  };
}

function requestDiagnostic(request: Request): BrowserDiagnostic {
  const failure = request.failure();
  return {
    kind: "requestfailed",
    message: `${request.method()} ${request.resourceType()}${
      failure?.errorText ? ` (${failure.errorText})` : ""
    }`,
    url: safeUrl(request.url()),
  };
}

/**
 * Shared browser fixture for baseline observability across every E2E spec.
 *
 * All console errors/warnings and request failures are attached to the test
 * result for inspection. Every unexpected console error or warning, uncaught
 * page error, and required document/script/style/font failure fails the test.
 * An intentional diagnostic must opt into a narrow local prefix; framework
 * warning signatures remain fatal and there is no suite-wide suppression.
 */
export const test = base.extend<StrictTestOptions>({
  allowedConsoleErrorPrefixes: [[], { option: true }],
  allowedConsoleWarningPrefixes: [[], { option: true }],
  allowedNavigationReplacements: [[], { option: true }],
  page: async (
    {
      allowedConsoleErrorPrefixes,
      allowedConsoleWarningPrefixes,
      allowedNavigationReplacements,
      page,
    },
    runPage,
    testInfo,
  ) => {
    const diagnostics: BrowserDiagnostic[] = [];
    const criticalDiagnostics: BrowserDiagnostic[] = [];

    const onConsole = (message: ConsoleMessage) => {
      if (message.type() !== "error" && message.type() !== "warning") return;
      const diagnostic = consoleDiagnostic(message);
      diagnostics.push(diagnostic);
      if (
        isFatalConsoleDiagnostic({
          allowedErrorPrefixes: allowedConsoleErrorPrefixes,
          allowedWarningPrefixes: allowedConsoleWarningPrefixes,
          message: diagnostic.message,
          type: message.type(),
        })
      ) {
        criticalDiagnostics.push(diagnostic);
      }
    };
    const onPageError = (error: Error) => {
      const diagnostic: BrowserDiagnostic = {
        kind: "pageerror",
        message: sanitizeDiagnosticText(
          error.message,
          "Browser page error unavailable.",
        ),
      };
      diagnostics.push(diagnostic);
      criticalDiagnostics.push(diagnostic);
    };
    const onRequestFailed = (request: Request) => {
      const diagnostic = requestDiagnostic(request);
      diagnostics.push(diagnostic);
      const failure = request.failure();
      const expectedReplacement = allowedNavigationReplacements.find(
        (replacement) => replacement.requestUrl === request.url(),
      );
      const isBenignNavigationReplacement = isProvenBenignNavigationReplacement(
        {
          currentUrl: page.url(),
          errorText: failure?.errorText,
          expectedReplacementUrl: expectedReplacement?.replacementUrl,
          isNavigationRequest: request.isNavigationRequest(),
          requestUrl: request.url(),
          resourceType: request.resourceType(),
        },
      );
      if (
        CRITICAL_RESOURCE_TYPES.has(request.resourceType()) &&
        !isBenignNavigationReplacement
      ) {
        criticalDiagnostics.push(diagnostic);
      }
    };

    page.on("console", onConsole);
    page.on("pageerror", onPageError);
    page.on("requestfailed", onRequestFailed);

    await runPage(page);

    page.off("console", onConsole);
    page.off("pageerror", onPageError);
    page.off("requestfailed", onRequestFailed);

    if (diagnostics.length > 0) {
      await testInfo.attach("browser-diagnostics", {
        body: JSON.stringify(diagnostics, null, 2),
        contentType: "application/json",
      });
    }

    expect(
      criticalDiagnostics,
      "Unexpected console error/warning, page error, or required-resource failure",
    ).toEqual([]);
  },
});

export { expect };
export type { Page };
