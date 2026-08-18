"use client";

import { Globe } from "lucide-react";
import type { PatentHit } from "@praviar/shared-types";
import { PatentFamilyTree } from "@/components/report/patent-family-tree";
import { PatentDetailDrawerSection } from "@/components/report/patent-detail-drawer-section";

export function PatentDetailDrawerFamilySection({
  family,
  currentPatentId,
}: {
  family: NonNullable<PatentHit["family"]>;
  currentPatentId: string;
}) {
  return (
    <PatentDetailDrawerSection
      title="Patent Family"
      icon={Globe}
      defaultOpen={false}
    >
      <PatentFamilyTree family={family} currentPatentId={currentPatentId} />
    </PatentDetailDrawerSection>
  );
}
