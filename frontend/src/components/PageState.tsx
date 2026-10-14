import type { ReactNode } from "react";
import { CircleAlert, Inbox, LoaderCircle, RotateCw } from "lucide-react";

export function LoadingState({ label = "Carregando" }: { label?: string }) {
  return (
    <div
      aria-busy="true"
      aria-live="polite"
      className="flex min-h-48 flex-col items-center justify-center gap-3 text-sm text-[#94a3b8]"
      role="status"
    >
      <span className="grid size-11 place-items-center rounded-2xl border border-line bg-surface shadow-[0_0_24px_rgba(83,109,254,0.18)]">
        <LoaderCircle className="animate-spin text-[#8295ff]" size={18} />
      </span>
      {label}
    </div>
  );
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
      className="flex items-start gap-3 rounded-2xl border border-[#5a3037]/80 bg-[#1a1013]/70 p-4 text-sm text-[#f1a3ad]"
      role="alert"
    >
      <CircleAlert className="mt-0.5 shrink-0" size={17} />
      <div className="min-w-0 flex-1">
        <p className="break-words leading-6">{message}</p>
        {onRetry && (
          <button
            className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-[#f8c4cb] underline-offset-4 hover:underline"
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
    <div className="rounded-2xl border border-dashed border-line bg-surface-inset/40 px-4 py-10 text-center text-sm text-[#94a3b8]">
      <span className="mx-auto mb-3 grid size-10 place-items-center rounded-xl border border-line-soft text-[#7186ff]">
        {icon ?? <Inbox size={18} />}
      </span>
      <p className="mx-auto max-w-sm leading-6">{message}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
