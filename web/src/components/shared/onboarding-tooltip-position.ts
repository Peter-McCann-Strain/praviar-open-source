export type TooltipPlacement = "top" | "bottom" | "left" | "right";

export interface TooltipPosition {
  top: number;
  left: number;
  placement: TooltipPlacement;
}

export function calculateTooltipPosition(
  targetRect: DOMRect,
  tooltipWidth: number,
  tooltipHeight: number,
  viewportWidth: number,
  viewportHeight: number,
): TooltipPosition {
  const gap = 16;

  const spaceBelow = viewportHeight - targetRect.bottom;
  const spaceAbove = targetRect.top;
  const spaceRight = viewportWidth - targetRect.right;
  const spaceLeft = targetRect.left;

  let placement: TooltipPlacement = "bottom";
  let top = 0;
  let left = 0;

  if (spaceBelow >= tooltipHeight + gap) {
    placement = "bottom";
    top = targetRect.bottom + gap;
    left = targetRect.left + targetRect.width / 2 - tooltipWidth / 2;
  } else if (spaceAbove >= tooltipHeight + gap) {
    placement = "top";
    top = targetRect.top - tooltipHeight - gap;
    left = targetRect.left + targetRect.width / 2 - tooltipWidth / 2;
  } else if (spaceRight >= tooltipWidth + gap) {
    placement = "right";
    top = targetRect.top + targetRect.height / 2 - tooltipHeight / 2;
    left = targetRect.right + gap;
  } else if (spaceLeft >= tooltipWidth + gap) {
    placement = "left";
    top = targetRect.top + targetRect.height / 2 - tooltipHeight / 2;
    left = targetRect.left - tooltipWidth - gap;
  } else {
    placement = "bottom";
    top = targetRect.bottom + gap;
    left = targetRect.left + targetRect.width / 2 - tooltipWidth / 2;
  }

  left = Math.max(12, Math.min(left, viewportWidth - tooltipWidth - 12));
  top = Math.max(12, Math.min(top, viewportHeight - tooltipHeight - 12));

  return { top, left, placement };
}
