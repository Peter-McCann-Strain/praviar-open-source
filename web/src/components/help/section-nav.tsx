import { SECTION_LINKS } from "@/components/help/helpers";

export function HelpSectionNav() {
  return (
    <nav
      aria-label="Help sections"
      className="praviar-glass-strip sticky top-16 z-20 -mx-1 flex flex-wrap gap-1.5 rounded-lg border border-[var(--border-default)] px-3 py-2.5 shadow-[var(--card-shadow)]"
    >
      {SECTION_LINKS.map((link) => (
        <a
          key={link.href}
          href={link.href}
          className="type-label-sm inline-flex min-h-11 items-center rounded-md px-2.5 py-1.5 text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
        >
          {link.label}
        </a>
      ))}
    </nav>
  );
}
