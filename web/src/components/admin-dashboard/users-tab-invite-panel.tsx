"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  ADMIN_BUTTON_TARGET_CLASS,
  ADMIN_FIELD_CLASS,
  INVITE_ROLE_OPTIONS,
} from "@/components/admin-dashboard/helpers";
import { formatRoleLabel } from "@/components/admin-dashboard/users-tab-helpers";

export function UsersTabInvitePanel({
  email,
  emailError,
  role,
  loading,
  onEmailChange,
  onRoleChange,
  onSubmit,
}: {
  email: string;
  emailError: string | null;
  role: string;
  loading: boolean;
  onEmailChange: (value: string) => void;
  onRoleChange: (value: string) => void;
  onSubmit: () => void;
}) {
  const emailErrorId = "invite-user-email-error";

  return (
    <Card>
      <CardContent className="p-5">
        <form
          className="flex flex-col gap-3 sm:flex-row sm:items-end"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (loading) {
              return;
            }
            onSubmit();
          }}
        >
          <div className="flex-1">
            <label
              htmlFor="invite-user-email"
              className="mb-1 block type-label-sm text-[var(--text-secondary)]"
            >
              Email Address
            </label>
            <input
              id="invite-user-email"
              type="email"
              value={email}
              required
              aria-invalid={emailError ? true : undefined}
              aria-describedby={emailError ? emailErrorId : undefined}
              disabled={loading}
              onChange={(e) => onEmailChange(e.target.value)}
              placeholder="user@company.com"
              className={`${ADMIN_FIELD_CLASS} w-full text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] ${
                emailError ? "border-error focus-visible:ring-error/70" : ""
              }`}
            />
            {emailError ? (
              <p
                id={emailErrorId}
                role="alert"
                className="mt-2 text-xs leading-5 text-error"
              >
                {emailError}
              </p>
            ) : null}
          </div>
          <div className="w-full sm:w-32">
            <label
              htmlFor="invite-user-role"
              className="mb-1 block type-label-sm text-[var(--text-secondary)]"
            >
              Role
            </label>
            <select
              id="invite-user-role"
              value={role}
              disabled={loading}
              onChange={(e) => onRoleChange(e.target.value)}
              aria-label="Invite role"
              className={`${ADMIN_FIELD_CLASS} w-full text-[var(--text-secondary)]`}
            >
              {INVITE_ROLE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {formatRoleLabel(option)}
                </option>
              ))}
            </select>
          </div>
          <Button
            type="submit"
            loading={loading}
            size="sm"
            className={`${ADMIN_BUTTON_TARGET_CLASS} w-full sm:w-auto`}
          >
            Send Invite
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
