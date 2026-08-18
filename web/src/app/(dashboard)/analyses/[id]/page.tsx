"use client";

import { use } from "react";
import { AnalysisDetailContent } from "@/components/analysis-detail/analysis-detail-content";

export default function AnalysisDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return <AnalysisDetailContent id={id} />;
}
