import { ImagePlus, Trash2, Trophy } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { compact, useAwards } from "@/features/wallet/api";
import { ApiError } from "@/services/api";

/** Super Admin: the photo of each award card shown to every user. */
export function AdminAwardsPage() {
  const { list, upload, remove } = useAwards();
  if (list.isLoading) return <LoadingState label="Carregando premiações" />;
  if (list.error) return <ErrorState message={list.error instanceof ApiError ? list.error.message : "Falha ao carregar."} onRetry={() => void list.refetch()} />;
  const error = upload.error ?? remove.error;
  return (
    <div className="mx-auto max-w-[1100px] space-y-4">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Super Admin</p>
        <h1 className="mt-2 flex items-center gap-2 text-2xl font-semibold text-fg"><Trophy className="text-warning" size={24} /> Premiações</h1>
        <p className="mt-1 text-sm text-muted">A foto de cada meta aparece no painel e na carteira de todos. JPG, PNG ou WEBP até 8 MB, de preferência quadrada.</p>
      </header>
      {error && <p className="text-xs text-danger" role="alert">{error instanceof ApiError ? error.message : "Não foi possível salvar."}</p>}
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        {list.data!.items.map((item) => (
          <li className="glass-panel overflow-hidden" key={item.amount}>
            <div className="flex aspect-square items-center justify-center bg-well">
              {item.image_url ? <img alt={item.prize} className="h-full w-full object-cover" src={item.image_url} /> : <Trophy className="text-warning opacity-40" size={48} />}
            </div>
            <div className="space-y-2 p-3">
              <p className="text-sm font-semibold text-fg">{compact(item.amount)} · {item.prize}</p>
              <div className="flex gap-2">
                <label className="btn-secondary flex-1 cursor-pointer justify-center text-xs">
                  <ImagePlus size={14} /> {upload.isPending && upload.variables?.amount === item.amount ? "Enviando…" : item.image_url ? "Trocar" : "Enviar"}
                  <input
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) upload.mutate({ amount: item.amount, file });
                      event.target.value = "";
                    }}
                    type="file"
                  />
                </label>
                {item.image_url && (
                  <button aria-label="Remover foto" className="btn-secondary text-xs" onClick={() => remove.mutate(item.amount)} type="button"><Trash2 size={14} /></button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
