import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

const messages: Record<string, string> = {
  connected: "Conta do Instagram conectada ao workspace.",
  cancelled: "A autorização foi cancelada. Nenhuma conta foi conectada.",
  error: "Não foi possível conectar a conta. Confira as permissões e tente novamente.",
};

/**
 * Shows the OAuth result (`?instagram=connected|cancelled|error`) after the
 * Meta callback redirects back to a dashboard, then cleans the URL.
 */
export function useInstagramCallbackToast() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const outcome = searchParams.get("instagram");

  useEffect(() => {
    if (!outcome) return;
    const message = messages[outcome];
    if (message) {
      window.dispatchEvent(new CustomEvent("flashpost-toast", { detail: message }));
    }
    if (outcome === "connected") {
      void queryClient.invalidateQueries({ queryKey: ["instagram"] });
      void queryClient.invalidateQueries({ queryKey: ["collaborators"] });
      void queryClient.invalidateQueries({ queryKey: ["analytics"] });
    }
    const next = new URLSearchParams(searchParams);
    next.delete("instagram");
    setSearchParams(next, { replace: true });
  }, [outcome, queryClient, searchParams, setSearchParams]);
}
