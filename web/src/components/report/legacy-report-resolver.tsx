"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FileQuestion, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuthToken } from "@/hooks/use-auth-token";
import { APIError, apiClient } from "@/lib/api-client";
import { resolveLegacyReportAnalysisId } from "@/lib/legacy-report-redirect";
import { authScopeKey } from "@/lib/query-keys";

interface ReportIdentityResolution {
  analysis_id: string;
  report_id: string;
  matched_by: "analysis_id" | "report_id";
}

export function LegacyReportResolver({ id }: { id: string }) {
  const searchParams = useSearchParams();
  const token = useAuthToken();
  const queryString = searchParams.toString();
  const legacyAnalysisId = useMemo(
    () => resolveLegacyReportAnalysisId(id),
    [id],
  );

  return (
    <LegacyReportResolutionRequest
      key={`${id}:${queryString}:${authScopeKey(token)}`}
      id={id}
      legacyAnalysisId={legacyAnalysisId}
      queryString={queryString}
      token={token}
    />
  );
}

function LegacyReportResolutionRequest({
  id,
  legacyAnalysisId,
  queryString,
  token,
}: {
  id: string;
  legacyAnalysisId: string;
  queryString: string;
  token: string | null;
}) {
  const router = useRouter();
  const [error, setError] = useState<"missing" | "unavailable" | null>(null);

  useEffect(() => {
    const navigate = (analysisId: string) => {
      router.replace(
        `/analyses/${encodeURIComponent(analysisId)}/report${
          queryString ? `?${queryString}` : ""
        }`,
      );
    };

    if (legacyAnalysisId !== id) {
      navigate(legacyAnalysisId);
      return;
    }
    if (!token) return;

    const controller = new AbortController();
    void apiClient<ReportIdentityResolution>(
      `/reports/resolve/${encodeURIComponent(id)}`,
      { token, signal: controller.signal },
    )
      .then((resolution) => navigate(resolution.analysis_id))
      .catch((caught: unknown) => {
        if (caught instanceof Error && caught.name === "AbortError") return;
        setError(
          caught instanceof APIError && caught.status === 404
            ? "missing"
            : "unavailable",
        );
      });

    return () => controller.abort();
  }, [id, legacyAnalysisId, queryString, router, token]);

  if (error) {
    const missing = error === "missing";
    return (
      <div className="mx-auto flex min-h-[45vh] max-w-xl items-center justify-center px-6">
        <section className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-card)] p-6 text-center shadow-sm">
          <FileQuestion
            className="mx-auto h-8 w-8 text-[var(--text-tertiary)]"
            aria-hidden="true"
          />
          <h1 className="mt-4 text-xl font-semibold text-[var(--text-primary)]">
            {missing ? "Report link not found" : "Report link unavailable"}
          </h1>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            {missing
              ? "This report reference does not exist in your organization or is no longer available."
              : "The report reference could not be resolved. Check your connection and try again."}
          </p>
          <Button asChild variant="outline" className="mt-5 min-h-11">
            <Link href="/analyses">Back to analyses</Link>
          </Button>
        </section>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-[45vh] max-w-xl items-center justify-center px-6 text-center">
      <div
        role="status"
        className="space-y-3 text-sm text-[var(--text-secondary)]"
      >
        <Loader2
          className="mx-auto h-5 w-5 animate-spin motion-reduce:animate-none"
          aria-hidden="true"
        />
        <p>Resolving this private report link…</p>
      </div>
    </div>
  );
}
