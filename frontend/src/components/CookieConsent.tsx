import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import { appForPath, APPS } from "@/lib/brand";
import { CONSENT_EVENT, hasDecided, saveConsent } from "@/lib/cookieConsent";

/** LGPD cookie consent banner (opt-in).
 *
 * Shown on every surface — Flash Post and Flash Bot share one SPA, so the
 * banner reads the current tool from the path and names it. Non-essential
 * cookies stay off until the person taps "Aceitar"; "Apenas essenciais" records
 * the refusal and keeps only the strictly necessary session/security cookies.
 */
export function CookieConsent() {
  const location = useLocation();
  const [open, setOpen] = useState(() => !hasDecided());

  useEffect(() => {
    const sync = () => setOpen(!hasDecided());
    window.addEventListener(CONSENT_EVENT, sync);
    window.addEventListener("storage", sync); // another tab decided
    return () => {
      window.removeEventListener(CONSENT_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  if (!open) return null;

  const app = appForPath(location.pathname);
  const toolName = APPS[app].name;

  const decide = (decision: "all" | "essential") => {
    saveConsent(decision);
    setOpen(false);
  };

  return (
    <div
      aria-label="Aviso de cookies"
      className="fixed inset-x-0 bottom-0 z-[200] px-3 pb-3 sm:px-4 sm:pb-4"
      role="dialog"
    >
      <div className="mx-auto max-w-2xl rounded-2xl border border-line-soft bg-well/95 p-4 shadow-xl backdrop-blur sm:p-5">
        <p className="text-sm font-semibold text-fg">🍪 Cookies no {toolName}</p>
        <p className="mt-1 text-sm leading-6 text-fg-2">
          Usamos cookies essenciais para manter você conectado e proteger sua conta. Com a sua
          autorização, também usamos cookies para lembrar preferências e medir o uso e melhorar o
          serviço. Você decide — pode mudar isso depois na{" "}
          <a className="text-accent underline" href="/cookies" rel="noreferrer" target="_blank">
            Política de Cookies
          </a>
          .
        </p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button className="btn-ghost w-full sm:w-auto" onClick={() => decide("essential")} type="button">
            Apenas essenciais
          </button>
          <button className="btn-primary w-full sm:w-auto" onClick={() => decide("all")} type="button">
            Aceitar
          </button>
        </div>
      </div>
    </div>
  );
}
