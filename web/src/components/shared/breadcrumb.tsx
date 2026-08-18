import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface BreadcrumbProps {
  ariaLabel?: string;
  className?: string;
  items: BreadcrumbItem[];
}

export function Breadcrumb({
  ariaLabel = "Breadcrumb",
  className,
  items,
}: BreadcrumbProps) {
  return (
    <nav
      aria-label={ariaLabel}
      className={cn(
        "mb-4 min-w-0 overflow-x-auto overscroll-x-contain",
        className,
      )}
    >
      <ol className="flex w-full min-w-0 flex-nowrap items-center gap-1 text-sm text-[var(--text-tertiary)]">
        {items.map((item, i) => (
          <li
            key={`${item.href ?? "current"}:${item.label}`}
            className={cn(
              "flex min-w-0 items-center gap-1",
              i === 0 || (items.length > 2 && i === items.length - 1)
                ? "shrink-0"
                : "flex-1",
            )}
          >
            {i > 0 && <ChevronRight className="h-3 w-3 flex-shrink-0" />}
            {item.href ? (
              <Link
                href={item.href}
                className="flex min-h-11 min-w-0 max-w-full items-center overflow-hidden rounded-md px-1.5 transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:max-w-[18rem] sm:px-2"
                title={item.label}
              >
                <span className="block w-full min-w-0 max-w-full overflow-hidden text-ellipsis whitespace-nowrap">
                  {item.label}
                </span>
              </Link>
            ) : (
              <span
                className="flex min-h-11 w-full min-w-0 max-w-full items-center overflow-hidden rounded-md px-1.5 font-medium text-[var(--text-primary)] sm:max-w-[18rem] sm:px-2"
                aria-current="page"
                title={item.label}
              >
                <span className="block w-full min-w-0 max-w-full overflow-hidden text-ellipsis whitespace-nowrap">
                  {item.label}
                </span>
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
