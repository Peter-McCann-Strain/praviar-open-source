import { Keyboard } from "lucide-react";
import {
  HELP_SECTION_SEARCH_TERMS,
  SHORTCUTS,
  matchesHelpQuery,
} from "@/components/help/helpers";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface KeyboardShortcutsCardProps {
  query?: string;
}

export function KeyboardShortcutsCard({
  query = "",
}: KeyboardShortcutsCardProps) {
  const normalizedQuery = query.trim().toLowerCase();
  const shortcuts = SHORTCUTS.filter((shortcut) =>
    matchesHelpQuery(
      normalizedQuery,
      ...HELP_SECTION_SEARCH_TERMS.shortcuts,
      shortcut.keys,
      shortcut.action,
    ),
  );

  return (
    <Card id="shortcuts" className="scroll-mt-36">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Keyboard className="h-4 w-4 text-brand-primary" />
          Keyboard Shortcuts
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {shortcuts.map((shortcut) => (
            <div
              key={shortcut.keys}
              className="flex items-center justify-between"
            >
              <span className="type-body-md text-[var(--text-secondary)]">
                {shortcut.action}
              </span>
              <kbd className="type-label-sm inline-flex items-center gap-1 rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-hover)] px-2.5 py-1 font-mono text-[var(--text-secondary)]">
                {shortcut.keys}
              </kbd>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
