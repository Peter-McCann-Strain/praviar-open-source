import type { CommentPanelComment } from "@/components/report/comment-panel-types";

export function formatRelativeTime(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export function groupCommentsByParent(comments: CommentPanelComment[]) {
  const topLevel = comments.filter((comment) => !comment.parent_id);
  const replies = comments.filter((comment) => comment.parent_id);
  const repliesByParent = new Map<string, CommentPanelComment[]>();

  for (const reply of replies) {
    const parentId = reply.parent_id;
    if (!parentId) continue;

    const list = repliesByParent.get(parentId) ?? [];
    list.push(reply);
    repliesByParent.set(parentId, list);
  }

  return {
    topLevel,
    repliesByParent,
  };
}
