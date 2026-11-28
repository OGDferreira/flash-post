import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, Megaphone, Plus, RotateCcw, Save, Send, Trash2 } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { ApiError, apiRequest } from "@/services/api";

type Template = { title: string; body: string };
type Messages = Record<string, Record<string, Template[]>>;
type MessagesResponse = {
  kinds: { kind: string; label: string; thresholds: number[] }[];
  placeholders: Record<string, string>;
  messages: Messages;
  defaults: Messages;
  customized: boolean;
};
type TestResponse = {
  title: string;
  body: string;
  value: number;
  source: string;
  devices: number;
  delivered: number;
};

const fmt = (value: number) => value.toLocaleString("pt-BR");

type Audience = { users: number; push_users: number };
type BroadcastResult = { users: number; delivered: number; devices: number };

const COMUNICADO_PADRAO = {
  title: "A FlashPost agora é flashpost.tech",
  body: "Mudamos de domínio. Suas contas, bots e dados continuam salvos. Toque para ver o que mudou e como reinstalar o app.",
  url: "/novidades",
};

/** Dispara um aviso único para TODOS os usuários (in-app + push). Ação irreversível. */
function BroadcastCard() {
  const [title, setTitle] = useState(COMUNICADO_PADRAO.title);
  const [body, setBody] = useState(COMUNICADO_PADRAO.body);
  const [url, setUrl] = useState(COMUNICADO_PADRAO.url);
  const [armed, setArmed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const audience = useQuery({
    queryKey: ["admin", "notifications", "audience"],
    queryFn: () => apiRequest<Audience>("/api/admin/notifications/broadcast/audience"),
  });

  const send = useMutation({
    mutationFn: () =>
      apiRequest<BroadcastResult>("/api/admin/notifications/broadcast", {
        method: "POST",
        body: { title: title.trim(), body: body.trim(), url: url.trim() || null },
      }),
    onSuccess: (r) => {
      setArmed(false);
      setNotice(`Comunicado enviado para ${fmt(r.users)} usuário(s). Push entregue a ${fmt(r.delivered)} de ${fmt(r.devices)} dispositivo(s).`);
    },
    onError: (error) => {
      setArmed(false);
      setNotice(error instanceof ApiError ? error.message : "Não foi possível enviar o comunicado.");
    },
  });

  const valid = title.trim().length > 0 && body.trim().length > 0;
  const total = audience.data?.users ?? 0;

  return (
    <section className="dashboard-card space-y-3 rounded-2xl border border-brand/40 p-4">
      <div className="flex items-center gap-2">
        <Megaphone className="text-accent" size={18} />
        <h3 className="text-sm font-semibold text-fg">Comunicado para todos</h3>
      </div>
      <p className="text-xs leading-5 text-muted">
        Envia um aviso único para <strong className="text-fg-2">{audience.isLoading ? "…" : fmt(total)}</strong> usuário(s)
        — na central de Avisos e por push. É irreversível e vai para todo mundo de uma vez.
      </p>
      <input
        aria-label="Título do comunicado"
        className="h-10 w-full rounded-lg border border-line bg-surface-inset px-3 text-sm text-fg"
        maxLength={120}
        onChange={(e) => { setTitle(e.target.value); setArmed(false); }}
        value={title}
      />
      <textarea
        aria-label="Texto do comunicado"
        className="min-h-[72px] w-full rounded-lg border border-line bg-surface-inset px-3 py-2 text-sm text-fg"
        maxLength={500}
        onChange={(e) => { setBody(e.target.value); setArmed(false); }}
        value={body}
      />
      <input
        aria-label="Link ao tocar (interno, ex: /novidades)"
        className="h-10 w-full rounded-lg border border-line bg-surface-inset px-3 text-sm text-fg"
        maxLength={255}
        onChange={(e) => { setUrl(e.target.value); setArmed(false); }}
        placeholder="/novidades"
        value={url}
      />
      <div className="flex flex-wrap items-center gap-2">
        {!armed ? (
          <button
            className="btn-primary text-xs"
            disabled={!valid || send.isPending}
            onClick={() => setArmed(true)}
            type="button"
          >
            <Megaphone size={14} /> Disparar comunicado
          </button>
        ) : (
          <>
            <button className="btn-secondary btn-danger text-xs" disabled={send.isPending} onClick={() => send.mutate()} type="button">
              <Send size={14} /> Confirmar envio para {fmt(total)} usuário(s)
            </button>
            <button className="btn-secondary text-xs" disabled={send.isPending} onClick={() => setArmed(false)} type="button">
              Cancelar
            </button>
          </>
        )}
      </div>
      {notice && <p className="text-xs text-fg-2" role="status">{notice}</p>}
    </section>
  );
}

function preview(text: string, value: number) {
  return text.replaceAll("{valor}", fmt(value)).replaceAll("{conta}", "@suaconta").replaceAll("{nome}", "Gui").replaceAll("{posts}", "230");
}

export function AdminNotificationsPage() {
  const queryClient = useQueryClient();
  const data = useQuery({
    queryKey: ["admin", "notifications", "messages"],
    queryFn: () => apiRequest<MessagesResponse>("/api/admin/notifications/messages"),
  });
  const [kind, setKind] = useState("views");
  const [threshold, setThreshold] = useState<number | null>(null);
  const [draft, setDraft] = useState<Messages | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastTest, setLastTest] = useState<TestResponse | null>(null);

  useEffect(() => {
    if (data.data && !draft) setDraft(structuredClone(data.data.messages));
  }, [data.data, draft]);

  const kindInfo = data.data?.kinds.find((item) => item.kind === kind);
  const activeThreshold = threshold ?? kindInfo?.thresholds[0] ?? 0;
  const variants = useMemo(
    () => draft?.[kind]?.[String(activeThreshold)] ?? [],
    [draft, kind, activeThreshold],
  );
  const dirty = JSON.stringify(draft) !== JSON.stringify(data.data?.messages);

  const setVariants = (next: Template[]) =>
    setDraft((current) => ({
      ...(current ?? {}),
      [kind]: { ...(current?.[kind] ?? {}), [String(activeThreshold)]: next },
    }));

  const onSaved = (response: MessagesResponse) => {
    queryClient.setQueryData(["admin", "notifications", "messages"], response);
    setDraft(structuredClone(response.messages));
  };
  const save = useMutation({
    mutationFn: () =>
      apiRequest<MessagesResponse>("/api/admin/notifications/messages", { method: "PUT", body: { messages: draft } }),
    onSuccess: (response) => {
      onSaved(response);
      setNotice("Textos salvos. Os próximos pushes já usam a versão nova.");
    },
    onError: (error) => setNotice(error instanceof ApiError ? error.message : "Não foi possível salvar."),
  });
  const reset = useMutation({
    mutationFn: () => apiRequest<MessagesResponse>("/api/admin/notifications/messages", { method: "DELETE" }),
    onSuccess: (response) => {
      onSaved(response);
      setNotice("Textos voltaram ao padrão.");
    },
  });
  const test = useMutation({
    mutationFn: (variant: number) =>
      apiRequest<TestResponse>("/api/admin/notifications/test", {
        method: "POST",
        body: { kind, threshold: activeThreshold, variant },
      }),
    onSuccess: (response) => {
      setLastTest(response);
      setNotice(
        response.devices === 0
          ? "Nenhum dispositivo seu com push ativo. Ative em Perfil → Notificações neste dispositivo."
          : `Enviado para ${response.delivered} de ${response.devices} dispositivo(s).`,
      );
    },
    onError: (error) => setNotice(error instanceof ApiError ? error.message : "Falha ao enviar o teste."),
  });

  if (data.isLoading || !draft) return <LoadingState label="Carregando notificações" />;
  if (data.error || !data.data) return <ErrorState message="Não foi possível carregar as notificações." />;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">Notificações</h2>
        <p className="mt-2 text-sm text-muted">
          Textos dos pushes de conquista. Variáveis: {Object.entries(data.data.placeholders)
            .map(([key, label]) => `${key} = ${label}`)
            .join(" · ")}
          . Uma frase é sorteada a cada envio.
        </p>
      </div>

      <BroadcastCard />

      <div className="flex flex-wrap gap-2">
        {data.data.kinds.map((item) => (
          <button
            className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
              item.kind === kind ? "border-brand bg-brand-soft text-accent" : "border-line-soft text-muted"
            }`}
            key={item.kind}
            onClick={() => {
              setKind(item.kind);
              setThreshold(null);
            }}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {kindInfo?.thresholds.map((value) => (
          <button
            className={`rounded-lg border px-2.5 py-1 text-xs ${
              value === activeThreshold ? "border-brand text-accent" : "border-line-soft text-muted"
            }`}
            key={value}
            onClick={() => setThreshold(value)}
            type="button"
          >
            {fmt(value)}
          </button>
        ))}
      </div>

      <section className="dashboard-card space-y-3 rounded-2xl p-4">
        {variants.map((variant, index) => (
          <div className="grid gap-2 rounded-xl border border-line-soft p-3" key={index}>
            <input
              aria-label={`Título da frase ${index + 1}`}
              className="h-10 rounded-lg border border-line bg-surface-inset px-3 text-sm text-fg"
              maxLength={120}
              onChange={(event) =>
                setVariants(variants.map((v, i) => (i === index ? { ...v, title: event.target.value } : v)))
              }
              value={variant.title}
            />
            <input
              aria-label={`Texto da frase ${index + 1}`}
              className="h-10 rounded-lg border border-line bg-surface-inset px-3 text-sm text-fg"
              maxLength={240}
              onChange={(event) =>
                setVariants(variants.map((v, i) => (i === index ? { ...v, body: event.target.value } : v)))
              }
              value={variant.body}
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="min-w-0 text-xs text-muted">
                <BellRing className="mr-1 inline text-accent" size={12} />
                <strong className="text-fg-2">{preview(variant.title, activeThreshold)}</strong> —{" "}
                {preview(variant.body, activeThreshold)}
              </p>
              <div className="flex gap-2">
                <button
                  className="btn-secondary !px-2.5 !py-1 text-xs"
                  disabled={test.isPending || dirty}
                  onClick={() => test.mutate(index)}
                  title={dirty ? "Salve antes de testar" : "Enviar este texto para os seus dispositivos"}
                  type="button"
                >
                  <Send size={13} /> Testar
                </button>
                <button
                  aria-label="Remover frase"
                  className="btn-secondary !px-2.5 !py-1 text-xs"
                  disabled={variants.length <= 1}
                  onClick={() => setVariants(variants.filter((_, i) => i !== index))}
                  type="button"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          </div>
        ))}
        <div className="flex flex-wrap gap-2">
          <button
            className="btn-secondary text-xs"
            disabled={variants.length >= 10}
            onClick={() => setVariants([...variants, { title: "🔥 {valor} ...", body: "Sua frase aqui 😎" }])}
            type="button"
          >
            <Plus size={14} /> Nova frase
          </button>
          <button className="btn-primary text-xs" disabled={!dirty || save.isPending} onClick={() => save.mutate()} type="button">
            <Save size={14} /> Salvar textos
          </button>
          <button
            className="btn-secondary text-xs"
            disabled={!data.data.customized || reset.isPending}
            onClick={() => reset.mutate()}
            type="button"
          >
            <RotateCcw size={14} /> Voltar ao padrão
          </button>
        </div>
        {notice && <p className="text-xs text-fg-2" role="status">{notice}</p>}
        {lastTest && (
          <p className="text-xs text-muted">
            Último teste: <strong className="text-fg-2">{lastTest.title}</strong> — {lastTest.body} ({lastTest.source})
          </p>
        )}
      </section>
    </div>
  );
}
