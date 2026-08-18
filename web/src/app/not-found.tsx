import Link from "next/link";
import { ArrowLeft, Compass, FileText } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";

export default function RootNotFound() {
  return (
    <main
      id="main-content"
      className="praviar-app-field flex min-h-screen items-center justify-center px-4 py-12 text-[var(--text-primary)]"
    >
      <div className="w-full max-w-3xl">
        <EmptyState
          icon={Compass}
          title="This Praviar page does not exist"
          description="The link may be incorrect, expired, or moved. You can return to the public site, review sample reports, or open your workspace if you are signed in."
          headingLevel={1}
          contextItems={[
            "Public routes remain available",
            "No workspace data exposed",
            "Navigation can recover",
          ]}
        />
        <div className="mt-5 flex flex-col justify-center gap-3 sm:flex-row">
          <Button asChild className="min-h-11 gap-2">
            <Link href="/">
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              Back to Praviar
            </Link>
          </Button>
          <Button asChild variant="outline" className="min-h-11 gap-2">
            <Link href="/sample-reports">
              <FileText className="h-4 w-4" aria-hidden="true" />
              View sample reports
            </Link>
          </Button>
        </div>
      </div>
    </main>
  );
}
