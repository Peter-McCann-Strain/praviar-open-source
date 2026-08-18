"use client";

import { CreditCard } from "lucide-react";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import { Button } from "@/components/ui/button";

interface BillingHeaderProps {
  actionsDisabled?: boolean;
  hasSubscription: boolean;
  isManagingSubscription: boolean;
  onManageSubscription: () => void;
}

export function BillingHeader({
  actionsDisabled = false,
  hasSubscription,
  isManagingSubscription,
  onManageSubscription,
}: BillingHeaderProps) {
  return (
    <AppSurfaceHeader
      dataTestId="billing-app-surface-header"
      eyebrow="Praviar account control"
      title="Credits & Billing"
      description="Buy Report Credits, manage plan capacity, and review usage"
      actions={
        hasSubscription ? (
          <Button
            variant="outline"
            className="min-h-11 w-full gap-2 sm:w-auto"
            onClick={onManageSubscription}
            disabled={actionsDisabled}
            loading={isManagingSubscription}
          >
            <CreditCard className="h-4 w-4" aria-hidden="true" />
            Manage Subscription
          </Button>
        ) : null
      }
    />
  );
}
