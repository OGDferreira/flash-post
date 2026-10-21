import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Share2 } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import type { Flow } from "@/features/bots/types";
import type { InstagramLoop } from "@/pages/loops/loopShared";
import { ApiError, apiRequest } from "@/services/api";

type Item = { id: string; name: string; shared?: boolean; shared_with?: string[] | null };

const sharedWith = (item: Item, userId: string) =>
  Boolean(item.shared) && (!item.shared_with || item.shared_with.includes(userId));

/** The chief's own funnels and loops (not copies received from someone else). */
function useOwnItems() {
  const flows = useQuery({
    queryKey: ["bots", "flows"],
    queryFn: () => apiRequest<{ flows: Flow[] }>("/api/bots/flows/list"),
    staleTime: 30_000,
  });
  const loops = useQuery({
    queryKey: ["loops"],
    queryFn: () => apiRequest<{ loops: InstagramLoop[] }>("/api/loops?include_accounts=false"),
    staleTime: 30_000,
  });
  return {
    loading: flows.isLoading || loops.isLoading,
    flows: (flows.data?.flows ?? []).filter((flow) => !flow.from_template) as Item[],
    loops: (loops.data?.loops ?? []).filter((loop) => !loop.linked && !loop.from_template) as Item[],
  };
}

/** Partner row: how many funnels and loops this partner receives; opens the list to add or remove. */
export function PartnerSharesCell({ affiliationId, userId, name }: { affiliationId: string; userId: string; name: string }) {
  const own = useOwnItems();
  const [open, setOpen] = useState(false);
  const flows = own.flows.filter((item) => sharedWith(item, userId)).length;
  const loops = own.loops.filter((item) => sharedWith(item, userId)).length;
  return (
    <>
      <button
        className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-left text-[11px] text-fg hover:bg-surface-raised"
        onClick={() => setOpen(true)}
        title={`Ver e compartilhar funis e loops com ${name}`}
        type="button"
      >
        <Share2 className="shrink-0 text-accent" size={13} />
        <span>
          {own.loading ? "…" : `${flows} funil(is) · ${loops} loop(s)`}
          <span className="block text-[10px] text-muted">ver / adicionar</span>
        </span>
      </button>
      {open && <PartnerSharesModal affiliationId={affiliationId} name={name} onClose={() => setOpen(false)} userId={userId} />}
    </>
  );
}

function PartnerSharesModal({ affiliationId, userId, name, onClose }: {
  affiliationId: string;
  userId: string;
  name: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const own = useOwnItems();
  const toggle = useMutation({
    mutationFn: (body: { kind: "flow" | "loop"; id: string; shared: boolean }) =>
      apiRequest(`/api/partners/${affiliationId}/shares`, { method: "POST", body }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bots", "flows"] });
      void queryClient.invalidateQueries({ queryKey: ["loops"] });
    },
  });
  const first = name.split(/\s+/)[0];
  const section = (title: string, kind: "flow" | "loop", items: Item[], empty: string) => (
    <div className="space-y-1.5">
      <h4 className="text-sm font-medium text-fg">{title}</h4>
      {items.length === 0 ? (
        <p className="text-xs text-muted">{empty}</p>
      ) : (
        items.map((item) => {
          const on = sharedWith(item, userId);
          return (
            <label className="flex items-center justify-between gap-2 rounded-lg border border-line-soft bg-surface-inset px-3 py-2 text-sm" key={item.id}>
              <span className="min-w-0">
                <span className="block truncate text-fg">{item.name}</span>
                <span className="text-[11px] text-muted">
                  {!item.shared ? "Só seu" : !item.shared_with ? "Com todos os sócios" : `Com ${item.shared_with.length} sócio(s)`}
                </span>
              </span>
              <input
                aria-label={`${on ? "Parar de compartilhar" : "Compartilhar"} ${item.name} com ${first}`}
                checked={on}
                disabled={toggle.isPending}
                onChange={() => toggle.mutate({ kind, id: item.id, shared: !on })}
                type="checkbox"
              />
            </label>
          );
        })
      )}
    </div>
  );
  return (
    <Modal
      description={`Marque o que ${first} recebe. Loops chegam prontos para ${first}, sem contas: começam a postar quando ele conectar as dele. Desmarcar tira só ${first}; os outros sócios continuam recebendo.`}
      onClose={onClose}
      open
      title={`Compartilhado com ${name}`}
    >
      <div className="space-y-4">
        {own.loading ? (
          <LoadingState label="Carregando funis e loops" />
        ) : (
          <>
            {section("Funis", "flow", own.flows, "Crie um funil no FlashBot para poder compartilhar.")}
            {section("Loops", "loop", own.loops, "Crie um loop para poder compartilhar.")}
          </>
        )}
        {toggle.error && <ErrorState message={toggle.error instanceof ApiError ? toggle.error.message : "Não foi possível salvar."} />}
      </div>
    </Modal>
  );
}
