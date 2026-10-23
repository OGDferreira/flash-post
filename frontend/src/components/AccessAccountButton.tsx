import { useMutation } from "@tanstack/react-query";
import { LogIn } from "lucide-react";

import { confirmAction } from "@/lib/confirm";
import { ApiError, apiRequest } from "@/services/api";

/** Super Admin: enter this user's account (audited); the banner on top brings you back. */
export function AccessAccountButton({ userId, name, className = "" }: { userId: string; name: string; className?: string }) {
  const enter = useMutation({
    mutationFn: () => apiRequest<{ message: string }>(`/api/admin/users/${userId}/impersonate`, { method: "POST" }),
    // full reload so the app starts fresh as the chosen user
    onSuccess: () => window.location.assign("/"),
  });
  return (
    <span className={`inline-flex flex-col ${className}`}>
      <button
        aria-label={`Acessar a conta de ${name}`}
        className="inline-flex min-h-8 items-center gap-1.5 rounded-lg bg-brand px-3 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
        disabled={enter.isPending}
        onClick={async () => {
          if (
            await confirmAction(
              `Acessar a conta de ${name}? Você vai ver e poder alterar tudo como se fosse ele. Ele não é avisado e você volta pela faixa "Voltar para minha conta".`,
            )
          ) {
            enter.mutate();
          }
        }}
        type="button"
      >
        <LogIn size={13} />
        {enter.isPending ? "Entrando…" : "Acessar conta"}
      </button>
      {enter.error && (
        <span className="mt-1 text-[11px] text-danger">
          {enter.error instanceof ApiError ? enter.error.message : "Não foi possível acessar."}
        </span>
      )}
    </span>
  );
}
