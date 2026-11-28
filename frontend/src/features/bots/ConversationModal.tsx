import { useEffect } from "react";
import { createPortal } from "react-dom";

import { Conversation } from "./ConversationsPanel";

/** Opens a lead's conversation in a pop-up over the current screen (sales list,
 *  dashboard log). `leadId` null = closed. */
export function ConversationModal({ leadId, onClose }: { leadId: string | null; onClose: () => void }) {
  useEffect(() => {
    if (!leadId) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [leadId, onClose]);

  if (!leadId) return null;
  return createPortal(
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-3 sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="h-[85dvh] max-h-[620px] w-full max-w-[460px]">
        <Conversation key={leadId} leadId={leadId} onBack={onClose} inModal />
      </div>
    </div>,
    document.body,
  );
}
