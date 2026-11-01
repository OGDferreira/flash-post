import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { BrandLogo } from "@/components/BrandLogo";
import { appForPath } from "@/lib/brand";
import { CircleAlert, Inbox, RotateCw } from "lucide-react";

export function LoadingState({ label = "Carregando", fullscreen = false }: { label?: string; fullscreen?: boolean }) {
  const content = (
    <div
      aria-busy="true"
      aria-live="polite"
      className={
        fullscreen
          ? "fixed inset-0 z-[200] flex h-[100dvh] w-screen flex-col items-center justify-center gap-4 bg-[var(--nm-bg)] px-4 pb-[env(safe-area-inset-bottom)] pt-[env(safe-area-inset-top)] text-sm text-muted"
          : "flex min-h-48 flex-col items-center justify-center gap-3 text-sm text-muted"
      }
      role="status"
    >
      <BrandLogo animated app={appForPath(window.location.pathname)} className={fullscreen ? "size-[84px]" : "size-12"} />
      {label}
    </div>
  );
  // Full screen: drawn on <body>, so a parent with a transform (page animations) can't pull
  // it up under the top bar; it always sits in the middle of the screen.
  return fullscreen && typeof document !== "undefined" ? createPortal(content, document.body) : content;
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="flex items-start gap-3 rounded-2xl border border-danger/30/80 bg-danger-soft/70 p-4 text-sm text-danger"
      role="alert"
    >
      <CircleAlert className="mt-0.5 shrink-0" size={17} />
      <div className="min-w-0 flex-1">
        <p className="break-words leading-6">{message}</p>
        {onRetry && (
          <button
            className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-danger underline-offset-4 hover:underline"
            onClick={onRetry}
            type="button"
          >
            <RotateCw size={13} />
            Tentar novamente
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({
  message,
  icon,
  action,
}: {
  message: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-line bg-surface-inset/40 px-4 py-10 text-center text-sm text-muted">
      <span className="mx-auto mb-3 grid size-10 place-items-center rounded-xl border border-line-soft text-accent">
        {icon ?? <Inbox size={18} />}
      </span>
      <p className="mx-auto max-w-sm leading-6">{message}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
