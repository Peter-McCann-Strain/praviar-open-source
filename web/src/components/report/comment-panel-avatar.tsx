"use client";

export function CommentPanelAvatar({ userId }: { userId: string }) {
  const initial = userId.charAt(0).toUpperCase();

  return (
    <div className="h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-brand-primary/15 flex text-xs font-bold text-brand-primary">
      {initial}
    </div>
  );
}
