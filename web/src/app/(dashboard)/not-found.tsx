import Link from "next/link";
import { ArrowLeft, Compass } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";

export default function DashboardNotFound() {
  return (
    <div className="py-12 sm:py-16">
      <EmptyState
        icon={Compass}
        title="This workspace page does not exist"
        description="The link may be incorrect, or the workspace page may have moved. Return to the dashboard to continue from the latest governed activity."
        headingLevel={1}
        contextItems={[
          "No private records exposed",
          "Dashboard remains available",
          "Navigation can recover",
        ]}
        className="mx-auto max-w-3xl"
      />
      <div className="mt-5 flex justify-center">
        <Button asChild variant="outline" className="min-h-11 gap-2">
          <Link href="/dashboard">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to Dashboard
          </Link>
        </Button>
      </div>
    </div>
  );
}
