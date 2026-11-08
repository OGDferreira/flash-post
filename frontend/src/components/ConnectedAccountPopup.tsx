import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";

import { Modal } from "@/components/ui/Modal";
import { apiRequest } from "@/services/api";

type Receipt = {
  id: string;
  username: string;
  profile_picture_url: string | null;
  follower_count: number | null;
  connected_at: string;
  connected_by: string | null;
};

/** After the Instagram authorization comes back (`?connected_account=<id>`): a pop-up with the
 *  account's photo, @, the date and time of the connection and who connected it. */
export function ConnectedAccountPopup() {
  // Read while rendering, before the pages' effects clean the URL.
  const [id, setId] = useState<string | null>(() =>
    typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("connected_account"),
  );
  const receipt = useQuery({
    queryKey: ["instagram", "connection", id],
    queryFn: () => apiRequest<Receipt>(`/api/instagram/accounts/${id}/connection`),
    enabled: Boolean(id),
    retry: 1,
  });
  const [broken, setBroken] = useState(false);
  const data = receipt.data;
  if (!id || !data) return null;
  const when = new Date(data.connected_at);
  const date = when.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
  const time = when.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const close = () => setId(null);
  return (
    <Modal open title="Conta conectada com sucesso!" onClose={close}
      footer={<button className="btn-primary w-full" onClick={close} type="button">Continuar</button>}>
      <div className="flex flex-col items-center text-center">
        <div className="relative">
          {data.profile_picture_url && !broken ? (
            <img alt="" onError={() => setBroken(true)} className="size-24 rounded-full border-4 border-success/40 object-cover" referrerPolicy="no-referrer" src={data.profile_picture_url} />
          ) : (
            <div className="grid size-24 place-items-center rounded-full border-4 border-success/40 bg-surface-inset text-3xl font-bold text-fg">
              {data.username.slice(0, 1).toUpperCase()}
            </div>
          )}
          <CheckCircle2 className="absolute -bottom-1 -right-1 rounded-full bg-surface text-success" size={30} />
        </div>
        <p className="mt-3 text-lg font-semibold text-fg">@{data.username}</p>
        {data.follower_count != null && (
          <p className="text-xs text-muted">{data.follower_count.toLocaleString("pt-BR")} seguidores</p>
        )}
        <dl className="mt-4 grid w-full grid-cols-2 gap-2 text-left text-sm">
          <div className="rounded-lg border border-line-soft bg-surface-inset p-3">
            <dt className="text-xs text-muted">Data</dt>
            <dd className="font-semibold text-fg">{date}</dd>
          </div>
          <div className="rounded-lg border border-line-soft bg-surface-inset p-3">
            <dt className="text-xs text-muted">Hora</dt>
            <dd className="font-semibold text-fg">{time}</dd>
          </div>
          <div className="col-span-2 rounded-lg border border-line-soft bg-surface-inset p-3">
            <dt className="text-xs text-muted">Conectada por</dt>
            <dd className="font-semibold text-fg">{data.connected_by ?? "—"}</dd>
          </div>
        </dl>
      </div>
    </Modal>
  );
}
