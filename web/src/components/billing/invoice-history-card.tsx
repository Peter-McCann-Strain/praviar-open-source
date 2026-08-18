"use client";

import {
  AlertTriangle,
  ExternalLink,
  FileText,
  Loader2,
  Receipt,
  RotateCcw,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  formatCurrency,
  formatDate,
  safeBillingDocumentHref,
} from "@/components/billing/helpers";
import type { InvoiceListResponse } from "@/hooks/use-billing";
import { isAuthBoundaryError } from "@/lib/api-client";

interface InvoiceHistoryCardProps {
  invoiceData?: InvoiceListResponse;
  error?: unknown;
  isLoading: boolean;
  onRetry?: () => void;
}

export function InvoiceHistoryCard({
  invoiceData,
  error,
  isLoading,
  onRetry,
}: InvoiceHistoryCardProps) {
  const accessRestricted = isAuthBoundaryError(error);
  const invoices = accessRestricted ? [] : (invoiceData?.invoices ?? []);
  const hasInvoices = invoices.length > 0;
  const showErrorOnly = Boolean(error && (!invoiceData || accessRestricted));
  const showStaleWarning = Boolean(error && invoiceData && !accessRestricted);

  return (
    <Card className="praviar-account-control-card overflow-hidden">
      <CardHeader className="praviar-account-control-header border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-2">
          <Receipt className="h-4 w-4 text-[var(--text-tertiary)]" />
          <CardTitle className="text-sm">Invoice History</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <div
            role="status"
            aria-live="polite"
            aria-busy="true"
            className="flex flex-col items-center justify-center px-6 py-8 text-center"
          >
            <Loader2
              className="h-5 w-5 animate-spin motion-reduce:animate-none text-[var(--text-tertiary)]"
              aria-hidden="true"
            />
            <p className="mt-3 text-sm font-medium text-[var(--text-primary)]">
              Loading invoice history
            </p>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">
              Retrieving Stripe-hosted invoice records for this organization.
            </p>
          </div>
        ) : showErrorOnly ? (
          <InvoiceHistoryError
            accessRestricted={accessRestricted}
            onRetry={onRetry}
          />
        ) : !hasInvoices ? (
          <div className="flex flex-col items-center justify-center px-6 py-10">
            <FileText className="mb-2 h-8 w-8 text-[var(--text-tertiary)]" />
            <p className="text-sm text-[var(--text-secondary)]">
              No invoices yet
            </p>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">
              Invoices will appear here after your first payment
            </p>
          </div>
        ) : (
          <div>
            {showStaleWarning ? (
              <div className="border-b border-warning/20 bg-warning/10 px-6 py-3">
                <div className="flex items-start gap-2">
                  <AlertTriangle
                    className="mt-0.5 h-4 w-4 shrink-0 text-warning"
                    aria-hidden="true"
                  />
                  <p className="text-xs leading-5 text-[var(--text-secondary)]">
                    Invoice refresh failed. Existing invoice history is still
                    shown, and no billing changes were made.
                  </p>
                </div>
              </div>
            ) : null}
            {invoiceData?.has_more ? (
              <div className="border-b border-info/20 bg-info/10 px-6 py-3">
                <p className="text-xs leading-5 text-[var(--text-secondary)]">
                  Showing the latest invoices returned by billing. Additional
                  invoice history is available in the Stripe billing portal.
                </p>
              </div>
            ) : null}
            <table className="w-full">
              <caption className="sr-only">
                Invoice history with invoice identifier, date, status, amount,
                and document actions.
              </caption>
              <thead className="hidden lg:table-header-group">
                <tr className="border-b border-[var(--border-subtle)]">
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-[var(--text-tertiary)]"
                  >
                    Invoice
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-[var(--text-tertiary)]"
                  >
                    Date
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-[var(--text-tertiary)]"
                  >
                    Status
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-right text-xs font-medium text-[var(--text-tertiary)]"
                  >
                    Amount
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-right text-xs font-medium text-[var(--text-tertiary)]"
                  >
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="block divide-y divide-[var(--border-subtle)] lg:table-row-group">
                {invoices.map((invoice) => {
                  const invoiceLabel =
                    invoice.number || invoice.id.slice(0, 12);
                  const hostedInvoiceHref = safeBillingDocumentHref(
                    invoice.hosted_invoice_url,
                  );
                  const pdfHref = safeBillingDocumentHref(invoice.pdf_url);
                  const amountCents =
                    invoice.amount_paid_cents || invoice.amount_due_cents;

                  return (
                    <tr
                      key={invoice.id}
                      className="block p-4 transition-colors hover:bg-[var(--surface-subtle)] lg:table-row lg:p-0"
                    >
                      <td className="flex items-start justify-between gap-4 py-2 lg:table-cell lg:px-6 lg:py-3">
                        <span className="text-xs font-medium text-[var(--text-tertiary)] lg:hidden">
                          Invoice
                        </span>
                        <span className="min-w-0 break-all text-right text-sm font-medium text-[var(--text-primary)] lg:text-left">
                          {invoiceLabel}
                        </span>
                      </td>
                      <td className="flex items-center justify-between gap-4 py-2 lg:table-cell lg:px-6 lg:py-3">
                        <span className="text-xs font-medium text-[var(--text-tertiary)] lg:hidden">
                          Date
                        </span>
                        <span className="text-sm tabular-nums text-[var(--text-secondary)]">
                          {formatDate(invoice.created_at)}
                        </span>
                      </td>
                      <td className="flex items-center justify-between gap-4 py-2 lg:table-cell lg:px-6 lg:py-3">
                        <span className="text-xs font-medium text-[var(--text-tertiary)] lg:hidden">
                          Status
                        </span>
                        <Badge
                          variant={
                            invoice.status === "paid"
                              ? "success"
                              : invoice.status === "open"
                                ? "warning"
                                : "secondary"
                          }
                        >
                          {invoice.status}
                        </Badge>
                      </td>
                      <td className="flex items-center justify-between gap-4 py-2 lg:table-cell lg:px-6 lg:py-3 lg:text-right">
                        <span className="text-xs font-medium text-[var(--text-tertiary)] lg:hidden">
                          Amount
                        </span>
                        <span className="text-sm font-medium tabular-nums text-[var(--text-primary)]">
                          {formatCurrency(amountCents, invoice.currency)}
                        </span>
                      </td>
                      <td className="block py-2 lg:table-cell lg:px-6 lg:py-3 lg:text-right">
                        <div className="flex flex-wrap items-center justify-end gap-3">
                          {hostedInvoiceHref ? (
                            <a
                              href={hostedInvoiceHref}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md border border-brand-primary/20 bg-brand-primary/10 px-3 text-xs font-semibold text-brand-primary transition-colors hover:bg-brand-primary/15 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
                              aria-label={`View invoice ${invoiceLabel}`}
                            >
                              View
                              <ExternalLink
                                className="h-3 w-3"
                                aria-hidden="true"
                              />
                            </a>
                          ) : null}
                          {pdfHref ? (
                            <a
                              href={pdfHref}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-3 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
                              aria-label={`Download invoice ${invoiceLabel} PDF`}
                            >
                              PDF
                              <ExternalLink
                                className="h-3 w-3"
                                aria-hidden="true"
                              />
                            </a>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function InvoiceHistoryError({
  accessRestricted = false,
  onRetry,
}: {
  accessRestricted?: boolean;
  onRetry?: () => void;
}) {
  const title = accessRestricted
    ? "Invoice history access restricted"
    : "Invoice history temporarily unavailable";
  const body = accessRestricted
    ? "Your current session is not authorized to view invoice history. Cached invoice rows and document links are hidden until access is restored."
    : "Praviar could not load invoice history. This does not indicate an empty billing record, and no payment or plan changes were made.";

  return (
    <div role="alert" className="px-6 py-8">
      <div className="rounded-lg border border-error/20 bg-error/10 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle
            className="mt-0.5 h-5 w-5 shrink-0 text-error"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="font-semibold text-[var(--text-primary)]">{title}</p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {body}
            </p>
            {onRetry ? (
              <Button
                type="button"
                variant="outline"
                className="mt-4 min-h-11 w-full gap-2 sm:w-auto"
                onClick={onRetry}
              >
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Retry invoice load
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
