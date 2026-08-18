"use client";

import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  ClipboardCheck,
  Compass,
  CreditCard,
  FileSearch,
  HelpCircle,
  Key,
  Layers,
  LayoutDashboard,
  LibraryBig,
  Radar,
  ScrollText,
  Shield,
  SlidersHorizontal,
} from "lucide-react";
import type { ApplicationRole } from "@/hooks/use-principal-capabilities";
import { hasValidClerkPublishableKey } from "@/lib/production-env";

export const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
export const hasClerk = hasValidClerkPublishableKey(clerkKey);

export interface NavigationItem {
  href: string;
  label: string;
  description: string;
  keywords: readonly string[];
  icon: LucideIcon;
  adminOnly?: boolean;
  allowedRoles?: readonly ApplicationRole[];
}

export interface NavigationSection {
  id: string;
  label: string;
  items: readonly NavigationItem[];
}

export const NAV_SECTIONS: readonly NavigationSection[] = [
  {
    id: "workspace",
    label: "Workspace",
    items: [
      {
        href: "/dashboard",
        label: "Dashboard",
        description: "Workspace overview and setup readiness",
        keywords: ["home", "overview", "readiness"],
        icon: LayoutDashboard,
      },
      {
        href: "/analyses",
        label: "Analyses",
        description: "Launch and review FTO analyses",
        keywords: ["reports", "matters", "freedom to operate", "fto"],
        icon: FileSearch,
      },
      {
        href: "/compounds",
        label: "Compounds",
        description: "Browse compounds and product contexts",
        keywords: ["molecules", "structures", "smiles", "products"],
        icon: LibraryBig,
      },
      {
        href: "/patents",
        label: "Patents",
        description: "Inspect patent records and evidence",
        keywords: ["claims", "families", "documents", "prior art"],
        icon: ScrollText,
        allowedRoles: ["admin", "attorney", "scientist"],
      },
    ],
  },
  {
    id: "decisions",
    label: "Decisions",
    items: [
      {
        href: "/monitors",
        label: "Monitors",
        description: "Track portfolio and legal-status changes",
        keywords: ["alerts", "watch", "legal status", "portfolio"],
        icon: Radar,
        allowedRoles: ["admin", "attorney", "scientist"],
      },
      {
        href: "/reviews",
        label: "Review Queue",
        description: "Resolve attorney and reviewer decisions",
        keywords: ["approvals", "decisions", "counsel", "review"],
        icon: ClipboardCheck,
        allowedRoles: ["admin", "attorney", "scientist"],
      },
    ],
  },
  {
    id: "operations",
    label: "Operations",
    items: [
      {
        href: "/batch",
        label: "Batch",
        description: "Run governed analyses across a portfolio",
        keywords: ["bulk", "portfolio", "multiple compounds"],
        icon: Layers,
        allowedRoles: ["admin", "attorney", "scientist"],
      },
      {
        href: "/config",
        label: "Configuration",
        description: "Review organization-controlled analysis policy",
        keywords: ["policy", "settings", "jurisdictions", "parameters"],
        icon: SlidersHorizontal,
        allowedRoles: ["admin", "attorney"],
      },
      {
        href: "/capabilities",
        label: "Workflow Atlas",
        description: "Understand pipeline stages and evidence controls",
        keywords: ["capabilities", "pipeline", "methods", "controls"],
        icon: Compass,
      },
    ],
  },
  {
    id: "administration",
    label: "Administration",
    items: [
      {
        href: "/billing",
        label: "Credits & Billing",
        description: "Review usage, credits, plan, and billing authority",
        keywords: ["plan", "subscription", "payments", "usage"],
        icon: CreditCard,
        allowedRoles: ["admin", "attorney", "scientist", "client"],
      },
      {
        href: "/settings",
        label: "Settings",
        description: "Manage access, SSO, API keys, and organization settings",
        keywords: ["security", "members", "authentication", "organization"],
        icon: Key,
        adminOnly: true,
      },
      {
        href: "/admin",
        label: "Platform Admin",
        description: "Manage users, organizations, health, and task operations",
        keywords: ["admin", "users", "organizations", "tasks", "health"],
        icon: Shield,
        adminOnly: true,
      },
      {
        href: "/admin/analytics",
        label: "Cost & Usage",
        description:
          "Inspect spend, model usage, pipeline volume, and audit events",
        keywords: ["analytics", "costs", "models", "tokens", "audit"],
        icon: BarChart3,
        adminOnly: true,
      },
    ],
  },
  {
    id: "support",
    label: "Support",
    items: [
      {
        href: "/help",
        label: "Help",
        description: "Find guidance, workflows, and support",
        keywords: ["docs", "documentation", "support", "faq"],
        icon: HelpCircle,
      },
    ],
  },
];

export const NAV_ITEMS: readonly NavigationItem[] = NAV_SECTIONS.flatMap(
  (section) => section.items,
);

export function isAdminOrgRole(orgRole: string | null | undefined): boolean {
  return orgRole === "org:admin" || orgRole === "admin";
}

export function getVisibleNavSections(
  orgRole: string | null | undefined,
  applicationRole?: string | null,
): NavigationSection[] {
  const normalizedRole = normalizeApplicationRole(applicationRole);
  const isAdmin = isAdminOrgRole(orgRole) && normalizedRole === "admin";

  return NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => {
      if (item.adminOnly) return isAdmin;
      if (!item.allowedRoles) return true;
      return normalizedRole
        ? item.allowedRoles.includes(normalizedRole)
        : false;
    }),
  })).filter((section) => section.items.length > 0);
}

export function getVisibleNavItems(
  orgRole: string | null | undefined,
  applicationRole?: string | null,
): NavigationItem[] {
  return getVisibleNavSections(orgRole, applicationRole).flatMap(
    (section) => section.items,
  );
}

function normalizeApplicationRole(
  role: string | null | undefined,
): ApplicationRole | null {
  const normalized = role?.trim().toLowerCase().replace(/^org:/u, "");
  return normalized === "admin" ||
    normalized === "attorney" ||
    normalized === "scientist" ||
    normalized === "client"
    ? normalized
    : null;
}

export function buildNavigationSearchValue(item: NavigationItem): string {
  return [item.label, item.description, ...item.keywords].join(" ");
}
