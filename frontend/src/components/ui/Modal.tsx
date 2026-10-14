import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

type ModalProps = {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  /** Prevents closing while an action is running. */
  busy?: boolean;
};

/**
 * Glass dialog. Bottom sheet on phones (thumb reach + safe area), centered
 * card from 640px up. Closes on Escape/backdrop unless `busy`.
 */
export function Modal({ open, title, description, onClose, children, footer, busy }: ModalProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  // Refs keep the effect below from re-running (and re-focusing) on every
  // parent render when callers pass inline callbacks.
  const onCloseRef = useRef(onClose);
  const busyRef = useRef(busy);
  onCloseRef.current = onClose;
  busyRef.current = busy;

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusTimer = window.setTimeout(() => {
      const firstFocusable = panelRef.current?.querySelector<HTMLElement>(
        "button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex='-1'])",
      );
      (firstFocusable ?? panelRef.current)?.focus();
    }, 0);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) onCloseRef.current();
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          "button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex='-1'])",
        ),
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  // Portal: page wrappers use `isolation: isolate`, which would otherwise trap
  // the dialog below the fixed header and bottom navigation.
  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-end justify-center sm:items-center sm:p-6">
      <button
        aria-label="Fechar"
        className="glass-overlay absolute inset-0 cursor-default"
        onClick={() => !busy && onClose()}
        tabIndex={-1}
        type="button"
      />
      <div
        aria-describedby={description ? descriptionId : undefined}
        aria-labelledby={titleId}
        aria-modal="true"
        className="glass-modal modal-enter relative flex max-h-[min(88dvh,720px)] w-full flex-col rounded-b-none pb-[env(safe-area-inset-bottom)] sm:max-w-lg sm:rounded-b-[20px] sm:pb-0"
        ref={panelRef}
        role="dialog"
        tabIndex={-1}
      >
        <div className="mx-auto mt-2.5 h-1 w-10 shrink-0 rounded-full bg-white/15 sm:hidden" />
        <header className="flex items-start justify-between gap-4 px-5 pb-3 pt-4 sm:px-6 sm:pt-6">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold tracking-[-0.02em] text-[#f5f7fb]" id={titleId}>
              {title}
            </h2>
            {description && (
              <p className="mt-1 text-sm leading-6 text-[#94a3b8]" id={descriptionId}>
                {description}
              </p>
            )}
          </div>
          <button
            aria-label="Fechar"
            className="btn-ghost -mr-2 -mt-1 size-10 shrink-0 !px-0"
            disabled={busy}
            onClick={onClose}
            type="button"
          >
            <X size={18} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5 sm:px-6">{children}</div>
        {footer && (
          <footer className="flex flex-wrap justify-end gap-2 border-t border-line-soft px-5 py-4 sm:px-6">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body,
  );
}
