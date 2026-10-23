import { useEffect, useRef, useState } from "react";
import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

/** Floating button: refetch every query on screen (new accounts, metrics, rankings). */
export function RefreshFab() {
  const queryClient = useQueryClient();
  const fetching = useIsFetching() > 0;
  const [spinning, setSpinning] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const refresh = () => {
    setSpinning(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setSpinning(false), 900);
    void queryClient.invalidateQueries();
  };
  const busy = spinning || fetching;

  return (
    <button
      aria-label="Atualizar página e métricas"
      className="glass-bar fixed bottom-[calc(env(safe-area-inset-bottom)+92px)] left-4 z-30 grid size-12 place-items-center rounded-full text-accent shadow-lg transition-transform hover:-translate-y-0.5 active:scale-95 lg:bottom-6 lg:left-auto lg:right-6 [body[data-flow-editor]_&]:hidden [body[data-bottom-tabs]_&]:max-lg:hidden"
      disabled={busy}
      onClick={refresh}
      title="Atualizar página e métricas"
      type="button"
    >
      <RefreshCw className={busy ? "animate-spin" : ""} size={19} />
    </button>
  );
}
