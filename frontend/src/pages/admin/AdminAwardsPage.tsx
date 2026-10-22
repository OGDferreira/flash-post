import { ImagePlus, RotateCcw, Trophy } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { awardTitle, useAwards } from "@/features/wallet/api";
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
        <p className="mt-1 text-sm text-muted">O banner de cada meta aparece no painel e na carteira de todos. Já vem com a arte padrão da Falcon Bot; envie outra para trocar. JPG, PNG ou WEBP até 8 MB, no formato retrato 4:5 (ex.: 1080×1350).</p>
      </header>
      {error && <p className="text-xs text-danger" role="alert">{error instanceof ApiError ? error.message : "Não foi possível salvar."}</p>}
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        {list.data!.items.map((item) => (
          <li className="glass-panel overflow-hidden" key={item.amount}>
            <div className="relative flex aspect-[4/5] items-center justify-center bg-well">
              {item.image_url ? <img alt={awardTitle(item.amount)} className="h-full w-full object-cover" src={item.image_url} /> : <Trophy className="text-warning opacity-40" size={48} />}
              <span className={`absolute left-2 top-2 rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white ${item.custom ? "bg-accent" : "bg-black/60"}`}>{item.custom ? "Personalizada" : "Padrão"}</span>
            </div>
            <div className="space-y-2 p-3">
              <p className="text-sm font-semibold text-fg">{awardTitle(item.amount)} faturados</p>
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
                {item.custom && (
                  <button aria-label="Voltar para a arte padrão" className="btn-secondary text-xs" onClick={() => remove.mutate(item.amount)} title="Voltar para a arte padrão" type="button"><RotateCcw size={14} /></button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
