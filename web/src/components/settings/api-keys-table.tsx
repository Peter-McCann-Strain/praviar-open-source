"use client";

import { AlertTriangle, CalendarClock, Key, Trash2 } from "lucide-react";
import type { APIKeyResponse } from "@/hooks/use-api-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import {
  apiKeyExpiryLabel,
  apiKeyPrefixLabel,
  apiKeyRotationLabel,
  apiKeyScopeLabel,
  apiKeyUsageLabel,
  isAPIKeyExpired,
  isAPIKeyExpiringSoon,
  relativeTime,
} from "@/components/settings/helpers";
import { useHydrationSafeRelativeTime } from "@/hooks/use-hydration-safe-relative-time";

interface ApiKeysTableProps {
  items: APIKeyResponse[];
  confirmRevoke: string | null;
  onStartRevoke: (keyId: string) => void;
  onCancelRevoke: () => void;
  onConfirmRevoke: (keyId: string) => void;
  revokePending: boolean;
  pendingRevokeId?: string | null;
}

export function ApiKeysTable({
  items,
  confirmRevoke,
  onStartRevoke,
  onCancelRevoke,
  onConfirmRevoke,
  revokePending,
  pendingRevokeId = null,
}: ApiKeysTableProps) {
  const formatRelativeTime = useHydrationSafeRelativeTime(relativeTime);
  return (
    <Card className="min-w-0 overflow-hidden">
      <CardHeader className="border-b border-[var(--border-default)]">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <CardTitle className="text-sm" role="heading" aria-level={3}>
              API keys
            </CardTitle>
            <p className="mt-1 text-sm leading-5 text-[var(--text-secondary)]">
              Review automation credentials that can access organization data.
            </p>
          </div>
          <Badge variant="secondary">{items.length} issued</Badge>
        </div>
      </CardHeader>
      {items.length === 0 ? (
        <CardContent className="min-w-0 p-0">
          <EmptyState
            icon={Key}
            title="No API keys"
            description="Use New API Key to integrate Praviar with approved tools, CI jobs, and internal workflow automation."
            surface="embedded"
          />
        </CardContent>
      ) : (
        <CardContent className="p-0">
          <div
            aria-label="API key ledger"
            className="max-w-full overflow-x-auto focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
            role="region"
            tabIndex={0}
          >
            <table className="w-full table-fixed text-sm md:min-w-[980px]">
              <caption className="sr-only">
                API key ledger with credential scope, status, usage, expiry,
                rotation posture, and revocation actions.
              </caption>
              <thead className="hidden md:table-header-group">
                <tr className="border-b border-[var(--border-subtle)]">
                  <th
                    scope="col"
                    className="px-4 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Name
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Scope
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Prefix
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-center type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Status
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Last Used
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Created
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Expires
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Rotation
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="block divide-y divide-[var(--border-subtle)] md:table-row-group">
                {items.map((apiKey) => {
                  const isPendingRevoke = pendingRevokeId === apiKey.id;
                  const canRevoke = !apiKey.revoked && !revokePending;
                  const lastUsedLabel = apiKeyUsageLabel(apiKey.last_used_at);
                  const expired =
                    !apiKey.revoked && isAPIKeyExpired(apiKey.expires_at);
                  const expiringSoon =
                    !apiKey.revoked && isAPIKeyExpiringSoon(apiKey.expires_at);
                  const expiryLabel = apiKeyExpiryLabel(apiKey.expires_at);
                  const rotationLabel = apiKey.revoked
                    ? "Closed"
                    : expired
                      ? "Expired"
                      : expiringSoon
                        ? "Rotate soon"
                        : apiKeyRotationLabel(apiKey.created_at);
                  const statusLabel = apiKey.revoked
                    ? "Revoked"
                    : expired
                      ? "Expired"
                      : expiringSoon
                        ? "Expiring"
                        : "Active";
                  const statusVariant = apiKey.revoked
                    ? "secondary"
                    : expired
                      ? "destructive"
                      : expiringSoon
                        ? "warning"
                        : "success";

                  return (
                    <tr
                      key={apiKey.id}
                      className="block p-4 transition-colors hover:bg-[var(--surface-subtle)] md:table-row md:p-0"
                    >
                      <td className="flex items-start justify-between gap-4 py-2 md:table-cell md:px-4 md:py-3">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          Name
                        </span>
                        <p className="min-w-0 text-right text-sm font-medium text-[var(--text-primary)] [overflow-wrap:anywhere] md:text-left">
                          {apiKey.name}
                        </p>
                      </td>
                      <td className="flex items-start justify-between gap-4 py-2 md:table-cell md:px-4 md:py-3">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          Scope
                        </span>
                        <div className="flex min-w-0 max-w-full flex-wrap justify-end gap-1 md:justify-start">
                          {apiKey.scopes.map((scope) => (
                            <Badge
                              key={scope}
                              variant="secondary"
                              className="max-w-full truncate text-xs font-medium"
                            >
                              {apiKeyScopeLabel(scope)}
                            </Badge>
                          ))}
                        </div>
                      </td>
                      <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-4 md:py-3">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          Prefix
                        </span>
                        <code className="inline-block max-w-full truncate rounded bg-[var(--surface-active)] px-2 py-0.5 font-mono text-xs text-[var(--text-tertiary)]">
                          {apiKeyPrefixLabel(apiKey.key_prefix)}
                        </code>
                      </td>
                      <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-4 md:py-3 md:text-center">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          Status
                        </span>
                        <Badge variant={statusVariant}>{statusLabel}</Badge>
                      </td>
                      <td className="flex items-center justify-between gap-4 py-2 text-xs tabular-nums text-[var(--text-tertiary)] md:table-cell md:px-4 md:py-3 md:text-right">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          Last Used
                        </span>
                        <span
                          className={
                            apiKey.last_used_at
                              ? ""
                              : "font-medium text-warning"
                          }
                        >
                          {lastUsedLabel}
                        </span>
                      </td>
                      <td className="flex items-center justify-between gap-4 py-2 text-xs tabular-nums text-[var(--text-tertiary)] md:table-cell md:px-4 md:py-3 md:text-right">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          Created
                        </span>
                        <span>{formatRelativeTime(apiKey.created_at)}</span>
                      </td>
                      <td className="flex items-center justify-between gap-4 py-2 text-xs tabular-nums text-[var(--text-tertiary)] md:table-cell md:px-4 md:py-3 md:text-right">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          Expires
                        </span>
                        <span
                          className={
                            expired
                              ? "inline-flex items-center gap-1 font-semibold text-error"
                              : expiringSoon
                                ? "inline-flex items-center gap-1 font-semibold text-warning"
                                : ""
                          }
                        >
                          {expiringSoon && !expired ? (
                            <CalendarClock
                              className="h-3.5 w-3.5"
                              aria-hidden="true"
                            />
                          ) : null}
                          {expiryLabel}
                        </span>
                      </td>
                      <td className="flex items-center justify-between gap-4 py-2 text-xs text-[var(--text-tertiary)] md:table-cell md:px-4 md:py-3 md:text-right">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          Rotation
                        </span>
                        <span className="inline-flex items-center justify-end gap-1">
                          {rotationLabel === "Review now" ||
                          rotationLabel === "Rotate soon" ||
                          rotationLabel === "Expired" ? (
                            <AlertTriangle className="h-3.5 w-3.5 text-warning" />
                          ) : null}
                          {rotationLabel}
                        </span>
                      </td>
                      <td className="block py-2 md:table-cell md:px-4 md:py-3 md:text-right">
                        {!apiKey.revoked ? (
                          confirmRevoke === apiKey.id ? (
                            <div className="flex flex-wrap items-center justify-end gap-2 md:gap-1">
                              <Button
                                variant="destructive"
                                size="sm"
                                className="min-h-11"
                                onClick={() => onConfirmRevoke(apiKey.id)}
                                loading={isPendingRevoke}
                                disabled={revokePending && !isPendingRevoke}
                                aria-label={`Confirm revoke for ${apiKey.name}`}
                              >
                                Revoke
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="min-h-11"
                                onClick={onCancelRevoke}
                                disabled={revokePending}
                                aria-label={`Cancel revoke for ${apiKey.name}`}
                              >
                                Cancel
                              </Button>
                            </div>
                          ) : (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="min-h-11 gap-1 text-error hover:text-error"
                              disabled={!canRevoke}
                              onClick={() => onStartRevoke(apiKey.id)}
                              aria-label={`Start revoke for ${apiKey.name}`}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              Revoke
                            </Button>
                          )
                        ) : (
                          <span className="block text-right text-xs text-[var(--text-tertiary)]">
                            Revoked
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      )}
    </Card>
  );
}
