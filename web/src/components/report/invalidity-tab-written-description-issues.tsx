"use client";

interface InvalidityTabWrittenDescriptionIssuesProps {
  issues: string[];
}

export function InvalidityTabWrittenDescriptionIssues({
  issues,
}: InvalidityTabWrittenDescriptionIssuesProps) {
  if (issues.length === 0) {
    return null;
  }

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">
        Written Description Issues
      </p>
      <ul className="space-y-1">
        {issues.map((issue, i) => (
          <li
            key={i}
            className="text-sm text-[var(--text-primary)] flex items-start gap-2"
          >
            <span className="text-warning mt-0.5">*</span>
            {issue}
          </li>
        ))}
      </ul>
    </div>
  );
}
