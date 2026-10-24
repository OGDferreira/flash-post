import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Handshake } from "lucide-react";

import { ApiError, apiRequest } from "@/services/api";

type MyChief = {
  has_chief: boolean;
  chief_name: string | null;
  chief_nickname: string | null;
  participation_percent: string | null;
  since: string | null;
};

export const myChiefKey = ["affiliates", "me"] as const;

/** Profile card: shows who the user is affiliated with, or lets them use an invite code. */
export function AffiliateLinkCard() {
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const me = useQuery({ queryKey: myChiefKey, queryFn: () => apiRequest<MyChief>("/api/affiliates/me"), staleTime: 60_000 });
  const join = useMutation({
    mutationFn: () => apiRequest<MyChief>("/api/affiliates/join", { method: "POST", body: { code: code.trim() } }),
    onSuccess: (result) => {
      setCode("");
      queryClient.setQueryData(myChiefKey, result);
    },
  });
  const error = join.error instanceof ApiError ? join.error.message : join.error ? "Não foi possível usar o código." : null;

  return (
    <section className="glass-panel p-4 sm:p-5" aria-labelledby="affiliate-link-title">
      <h3 id="affiliate-link-title" className="flex items-center gap-2 text-base font-semibold text-fg">
        <Handshake size={17} className="text-accent" />
        Filiação
      </h3>
      {me.data?.has_chief ? (
        <div className="mt-3 space-y-2 text-sm text-fg-2">
          <p>
            Você é filiado de <strong className="text-fg">{me.data.chief_name}</strong>
            {me.data.chief_nickname ? ` (${me.data.chief_nickname})` : ""}.
          </p>
          <p>
            Participação combinada:{" "}
            <strong className="text-fg">
              {Number(me.data.participation_percent ?? 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%
            </strong>{" "}
            da receita aprovada da sua operação.
          </p>
          <p className="text-xs leading-5 text-muted">
            Seu chefe vê as métricas das suas contas e do SharkBot. Ele não acessa suas contas, tokens ou senha. O
            percentual é definido por ele; o Flash não faz repasses.
          </p>
        </div>
      ) : (
        <form
          className="mt-3 space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (code.trim()) join.mutate();
          }}
        >
          <p className="text-xs leading-5 text-muted">
            Recebeu um código de convite? Informe-o para se tornar filiado de quem convidou. Você só pode ter um chefe.
          </p>
          <div className="flex gap-2">
            <input
              aria-label="Código de convite"
              autoCapitalize="characters"
              className="field min-w-0 flex-1 uppercase tracking-widest"
              maxLength={40}
              onChange={(event) => setCode(event.target.value)}
              placeholder="CÓDIGO"
              value={code}
            />
            <button className="btn-primary shrink-0" disabled={join.isPending || !code.trim()} type="submit">
              {join.isPending ? "Vinculando..." : "Usar código"}
            </button>
          </div>
          {error && <p className="text-xs text-danger" role="alert">{error}</p>}
        </form>
      )}
    </section>
  );
}
