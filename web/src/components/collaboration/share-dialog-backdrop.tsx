"use client";

export function ShareDialogBackdrop({ onClose }: { onClose: () => void }) {
  return (
    <div
      aria-hidden="true"
      className="praviar-overlay-scrim absolute inset-0"
      onClick={onClose}
    />
  );
}
