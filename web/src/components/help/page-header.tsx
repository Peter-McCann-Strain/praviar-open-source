import Link from "next/link";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import { Button } from "@/components/ui/button";
import type { PrincipalCapabilities } from "@/hooks/use-principal-capabilities";

export function HelpPageHeader({
  capabilities,
}: {
  capabilities?: PrincipalCapabilities;
}) {
  return (
    <AppSurfaceHeader
      className="max-[359px]:[&_[data-praviar-mark-frame]]:hidden"
      dataTestId="help-app-surface-header"
      eyebrow="Praviar support"
      markSize="sm"
      mobileDensity="compact"
      title="Help & Documentation"
      description="Learn how to use Praviar for Freedom-to-Operate analysis."
      metrics={[
        { label: "Start", value: "Guided workflow" },
        { label: "Evidence", value: "Pipeline steps" },
        { label: "Support", value: "Human handoff" },
      ]}
      actions={
        <div className="flex w-full flex-col gap-2 sm:flex-row lg:w-auto">
          {capabilities?.can_create_analysis === true ? (
            <Button asChild className="min-h-11 w-full sm:w-auto">
              <Link href="/analyses/new">Start analysis</Link>
            </Button>
          ) : null}
          <Button
            asChild
            variant="outline"
            className="min-h-11 w-full sm:w-auto"
          >
            <Link href="#pipeline-steps">Open report guide</Link>
          </Button>
        </div>
      }
    />
  );
}
