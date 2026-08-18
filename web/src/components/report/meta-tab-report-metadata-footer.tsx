"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";

export function ReportMetadataFooter({
  reportId,
  praviarPipelineVersion,
  generatedAt,
}: {
  reportId: string;
  praviarPipelineVersion: string;
  generatedAt: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-6 flex-wrap">
          <div>
            <p className="text-xs text-[var(--text-tertiary)] mb-0.5">
              Report ID
            </p>
            <p className="text-xs font-mono text-[var(--text-secondary)]">
              {reportId}
            </p>
          </div>
          <div>
            <p className="text-xs text-[var(--text-tertiary)] mb-0.5">
              Version
            </p>
            <Badge variant="secondary" className="text-xs">
              {praviarPipelineVersion}
            </Badge>
          </div>
          <div>
            <p className="text-xs text-[var(--text-tertiary)] mb-0.5">
              Generated
            </p>
            <p className="text-xs text-[var(--text-secondary)]">
              {formatDate(generatedAt)}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
