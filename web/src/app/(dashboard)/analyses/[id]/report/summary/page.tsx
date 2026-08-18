import { ClientReportSummaryPage } from "@/components/report-page/client-report-summary-page";

export default async function ReportSummaryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return <ClientReportSummaryPage analysisId={id} />;
}
