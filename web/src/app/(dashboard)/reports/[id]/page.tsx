import { Suspense } from "react";
import { LegacyReportResolver } from "@/components/report/legacy-report-resolver";

export default async function LegacyReportRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <Suspense fallback={<LegacyReportResolutionPending />}>
      <LegacyReportResolver id={id} />
    </Suspense>
  );
}

function LegacyReportResolutionPending() {
  return (
    <div className="mx-auto flex min-h-[45vh] max-w-xl items-center justify-center px-6 text-center">
      <p className="text-sm text-[var(--text-secondary)]" role="status">
        Resolving this private report link…
      </p>
    </div>
  );
}
