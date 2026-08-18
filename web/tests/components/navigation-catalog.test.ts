import { describe, expect, it } from "vitest";
import {
  buildNavigationSearchValue,
  getVisibleNavItems,
  getVisibleNavSections,
  NAV_ITEMS,
} from "@/components/layout/sidebar-constants";

describe("navigation catalog", () => {
  it("provides one unique destination inventory for sidebar and search", () => {
    const hrefs = NAV_ITEMS.map((item) => item.href);

    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(
      getVisibleNavSections("org:admin", "admin").flatMap(
        (section) => section.items,
      ),
    ).toEqual(getVisibleNavItems("org:admin", "admin"));
    expect(
      getVisibleNavSections("org:member", "scientist").flatMap(
        (section) => section.items,
      ),
    ).toEqual(getVisibleNavItems("org:member", "scientist"));
  });

  it.each([
    [
      "scientist",
      [
        "/dashboard",
        "/analyses",
        "/compounds",
        "/patents",
        "/monitors",
        "/reviews",
        "/batch",
        "/capabilities",
        "/billing",
        "/help",
      ],
    ],
    [
      "attorney",
      [
        "/dashboard",
        "/analyses",
        "/compounds",
        "/patents",
        "/monitors",
        "/reviews",
        "/batch",
        "/config",
        "/capabilities",
        "/billing",
        "/help",
      ],
    ],
    [
      "client",
      [
        "/dashboard",
        "/analyses",
        "/compounds",
        "/capabilities",
        "/billing",
        "/help",
      ],
    ],
  ])(
    "keeps the %s application role inside its permitted navigation",
    (applicationRole, expectedHrefs) => {
      expect(
        getVisibleNavItems("org:member", applicationRole).map(
          (item) => item.href,
        ),
      ).toEqual(expectedHrefs);
    },
  );

  it("keeps billing readable while reserving privileged administration for admins", () => {
    expect(
      getVisibleNavItems("org:member", "admin").map((item) => item.href),
    ).toContain("/billing");
    expect(
      getVisibleNavItems("org:admin", "attorney").map((item) => item.href),
    ).toContain("/billing");
    expect(
      getVisibleNavItems("org:admin", "admin").map((item) => item.href),
    ).toContain("/billing");
    expect(
      getVisibleNavItems("org:member", "admin").map((item) => item.href),
    ).not.toContain("/settings");
  });

  it("fails closed for role-restricted destinations until the application role is known", () => {
    expect(getVisibleNavItems("org:admin").map((item) => item.href)).toEqual([
      "/dashboard",
      "/analyses",
      "/compounds",
      "/capabilities",
      "/help",
    ]);
  });

  it.each([
    ["/compounds", "molecules"],
    ["/patents", "claims"],
    ["/billing", "payments"],
    ["/settings", "sso"],
    ["/admin", "users"],
    ["/admin/analytics", "costs"],
  ])("makes %s discoverable by the %s buyer term", (href, buyerTerm) => {
    const item = NAV_ITEMS.find((candidate) => candidate.href === href);

    expect(item).toBeDefined();
    expect(buildNavigationSearchValue(item!).toLowerCase()).toContain(
      buyerTerm,
    );
  });
});
