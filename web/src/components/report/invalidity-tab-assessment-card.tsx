"use client";

import { Card, CardContent } from "@/components/ui/card";
import { InvalidityTabAssessmentHeader } from "@/components/report/invalidity-tab-assessment-header";
import { InvalidityTabPtabAlert } from "@/components/report/invalidity-tab-ptab-alert";
import { InvalidityTabPtabProceedingsTable } from "@/components/report/invalidity-tab-ptab-proceedings-table";
import { InvalidityTabPriorArtTable } from "@/components/report/invalidity-tab-prior-art-table";
import { InvalidityTabClaimChartsSection } from "@/components/report/invalidity-tab-claim-charts-section";
import { InvalidityTabEnablementScreeningCard } from "@/components/report/invalidity-tab-enablement-screening-card";
import { InvalidityTabWrittenDescriptionIssues } from "@/components/report/invalidity-tab-written-description-issues";
import { InvalidityTabScreeningDisclaimer } from "@/components/report/invalidity-tab-screening-disclaimer";
import { GrahamFactorsSection } from "@/components/report/invalidity-tab-graham-factors";
import type { InvalidityAssessment } from "@/components/report/invalidity-tab-helpers";

interface InvalidityTabAssessmentCardProps {
  assessment: InvalidityAssessment;
  reportContext?: {
    generatedAt?: string | null;
    pipelineVersion?: string | null;
    reportId?: string | null;
  };
}

export function InvalidityTabAssessmentCard({
  assessment,
  reportContext,
}: InvalidityTabAssessmentCardProps) {
  return (
    <Card>
      <InvalidityTabAssessmentHeader assessment={assessment} />
      <CardContent className="space-y-5">
        <InvalidityTabPtabAlert ptab={assessment.ptab} />
        <p className="text-sm text-[var(--text-primary)]">
          {assessment.reasoning}
        </p>
        <InvalidityTabEnablementScreeningCard
          enablementScreening={assessment.enablement_screening}
        />
        <InvalidityTabPtabProceedingsTable
          proceedings={assessment.ptab.proceedings}
        />
        <InvalidityTabPriorArtTable
          patentId={assessment.patent_id}
          priorArt={assessment.prior_art}
        />
        {assessment.claim_charts.length > 0 && (
          <InvalidityTabClaimChartsSection
            claimCharts={assessment.claim_charts}
            priorArt={assessment.prior_art}
            reportContext={reportContext}
          />
        )}
        {assessment.graham_factors && (
          <GrahamFactorsSection factors={assessment.graham_factors} />
        )}
        <InvalidityTabWrittenDescriptionIssues
          issues={assessment.written_description_issues}
        />
        {assessment.screening_disclaimer && (
          <InvalidityTabScreeningDisclaimer
            screeningDisclaimer={assessment.screening_disclaimer}
          />
        )}
      </CardContent>
    </Card>
  );
}
