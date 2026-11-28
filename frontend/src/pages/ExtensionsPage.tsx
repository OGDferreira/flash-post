import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Chrome, Download, Eye, EyeOff, KeyRound, Pencil, Plus, Puzzle, Trash2, Upload } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/features/auth/AuthProvider";
import { ApiError, apiRequest } from "@/services/api";
import { confirmAction } from "@/lib/confirm";

type Extension = {
  id: string;
  name: string;
  description: string | null;
  instructions: string | null;
  visible_to_collaborators: boolean;
  file_name: string | null;
  file_size: number | null;
  has_file: boolean;
  updated_at: string;
};

const MAX_BYTES = 25 * 1024 * 1024;
const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");
const sizeLabel = (bytes: number | null) =>
  bytes === null ? "—" : bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

function EditorModal({ item, open, onClose }: { item: Extension | null; open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(item?.name ?? "");
  const [description, setDescription] = useState(item?.description ?? "");
  const [instructions, setInstructions] = useState(item?.instructions ?? "");
  const [visible, setVisible] = useState(item?.visible_to_collaborators ?? true);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name: name.trim(),
        description: description.trim() || null,
        instructions: instructions.trim() || null,
        visible_to_collaborators: visible,
      };
      const saved = item
        ? await apiRequest<Extension>(`/api/extensions/${item.id}`, { method: "PATCH", body })
        : await apiRequest<Extension>("/api/extensions", { method: "POST", body });
      if (file) {
        await apiRequest<Extension>(`/api/extensions/${saved.id}/file`, {
          method: "PUT",
          headers: { "Content-Type": "application/zip", "X-File-Name": file.name },
          body: file,
        });
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["extensions"] });
      onClose();
    },
    onError: (e) => setError(errorText(e)),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (name.trim().length < 2) return setError("Informe um nome com pelo menos 2 caracteres.");
    if (!item && !file) return setError("Selecione o arquivo ZIP.");
    save.mutate();
  };

  const pick = (selected: File | null) => {
    if (!selected) return;
    if (!/\.zip$/i.test(selected.name)) return setError("Selecione um arquivo .zip.");
    if (selected.size > MAX_BYTES) return setError("O ZIP deve ter até 25 MB.");
    setError(null);
    setFile(selected);
  };

  return (
    <Modal
      busy={save.isPending}
      description="Somente arquivos ZIP, até 25 MB."
      onClose={onClose}
      open={open}
      title={item ? "Editar extensão" : "Nova extensão"}
      footer={
        <>
          <button className="btn-ghost" disabled={save.isPending} onClick={onClose} type="button">Cancelar</button>
          <button className="btn-primary" disabled={save.isPending} form="extension-form" type="submit">
            {save.isPending ? "Salvando…" : "Salvar"}
          </button>
        </>
      }
    >
      <form className="space-y-3" id="extension-form" onSubmit={submit}>
        <label className="block text-sm">
          <span className="mb-1 block text-fg-2">Nome</span>
          <input className="field" maxLength={120} onChange={(e) => setName(e.target.value)} value={name} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-fg-2">Descrição</span>
          <input className="field" maxLength={1000} onChange={(e) => setDescription(e.target.value)} value={description} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-fg-2">Instruções de instalação/uso</span>
          <textarea className="field min-h-24 py-2" maxLength={8000} onChange={(e) => setInstructions(e.target.value)} value={instructions} />
        </label>
        <label className="flex items-center gap-2 text-sm text-fg-2">
          <input checked={visible} onChange={(e) => setVisible(e.target.checked)} type="checkbox" />
          Colaboradores podem baixar
        </label>
        <div>
          <input accept=".zip,application/zip" className="hidden" onChange={(e) => { pick(e.target.files?.[0] ?? null); e.target.value = ""; }} ref={fileInput} type="file" />
          <button className="btn-secondary" onClick={() => fileInput.current?.click()} type="button">
            <Upload size={15} /> {item ? "Trocar ZIP" : "Escolher ZIP"}
          </button>
          <span className="ml-2 text-xs text-muted">{file ? `${file.name} (${sizeLabel(file.size)})` : item?.file_name ?? ""}</span>
        </div>
        {error && <p className="text-xs text-danger" role="alert">{error}</p>}
      </form>
    </Modal>
  );
}

// ─── IgExtension types ─────────────────────────────────────────────────────────

type IgExtensionConfig = {
  full_name: string | null;
  username: string | null;
  bio: string | null;
  profile_photo_url: string | null;
  story_photo_url: string | null;
  link_url: string | null;
  sticker_text: string | null;
  highlight_title: string | null;
  sticker_size: number | null;
  sticker_x: number | null;
  sticker_y: number | null;
  sticker_rotation: number | null;
  has_password: boolean;
  updated_at: string;
};

// ─── IgExtension tab ───────────────────────────────────────────────────────────

function IgExtensionTab() {
  const queryClient = useQueryClient();
  const [password, setPassword] = useState("");
  const [pwdError, setPwdError] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [configSuccess, setConfigSuccess] = useState(false);

  const cfg = useQuery({
    queryKey: ["ig-extension"],
    queryFn: () => apiRequest<IgExtensionConfig>("/api/ig-extension"),
  });
  const data = cfg.data;

  const [form, setForm] = useState<Partial<IgExtensionConfig>>({});
  const field = <K extends keyof IgExtensionConfig>(k: K) => ({
    value: (k in form ? form[k] : data?.[k]) as string ?? "",
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm((prev) => ({ ...prev, [k]: e.target.value || null })),
  });
  const numField = (k: "sticker_size" | "sticker_x" | "sticker_y" | "sticker_rotation") => ({
    value: (k in form ? form[k] : data?.[k]) as number ?? "",
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((prev) => ({ ...prev, [k]: e.target.value === "" ? null : parseFloat(e.target.value) })),
  });

  const saveConfig = useMutation({
    mutationFn: () => apiRequest<IgExtensionConfig>("/api/ig-extension", { method: "PUT", body: { ...(data ?? {}), ...form } }),
    onSuccess: (d) => {
      void queryClient.invalidateQueries({ queryKey: ["ig-extension"] });
      setForm({});
      setConfigSuccess(true);
      setConfigError(null);
      setTimeout(() => setConfigSuccess(false), 3000);
    },
    onError: (e) => setConfigError(errorText(e)),
  });

  const savePassword = useMutation({
    mutationFn: () => apiRequest<IgExtensionConfig>("/api/ig-extension/password", { method: "POST", body: { pin: password } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ig-extension"] });
      setPassword("");
      setPwdError(null);
    },
    onError: (e) => setPwdError(errorText(e)),
  });

  const submitPwd = (e: FormEvent) => {
    e.preventDefault();
    if (!/^\d{4}$/.test(password)) return setPwdError("O PIN deve ter exatamente 4 dígitos numéricos.");
    setPwdError(null);
    savePassword.mutate();
  };

  const submitConfig = (e: FormEvent) => {
    e.preventDefault();
    setConfigError(null);
    setConfigSuccess(false);
    saveConfig.mutate();
  };

  if (cfg.isLoading) return <LoadingState label="Carregando configuração" />;
  if (cfg.error) return <ErrorState message={errorText(cfg.error)} onRetry={() => void cfg.refetch()} />;

  const sx = (k: "sticker_x" | "sticker_y") => ((k in form ? form[k] : data?.[k]) as number | null) ?? 0.5;
  const ss = ((("sticker_size" in form ? form.sticker_size : data?.sticker_size) as number | null) ?? 0.4);

  return (
    <div className="space-y-6">
      {/* PIN section */}
      <section className="glass-panel space-y-3 p-4">
        <h3 className="flex items-center gap-2 font-medium text-fg">
          <KeyRound size={16} className="text-accent" />
          {data?.has_password ? "Alterar PIN da extensão" : "Criar PIN da extensão"}
        </h3>
        <p className="text-sm text-muted">
          {data?.has_password
            ? "Digite um novo PIN de 4 dígitos para substituir o atual."
            : "Crie um PIN de 4 dígitos para liberar o uso da extensão FlashPost no navegador."}
        </p>
        <form className="flex flex-wrap items-end gap-3" onSubmit={submitPwd}>
          <label className="block text-sm">
            <span className="mb-1 block text-fg-2">PIN (4 dígitos)</span>
            <input
              className="field w-32 text-center tracking-widest text-lg"
              inputMode="numeric"
              maxLength={4}
              minLength={4}
              onChange={(e) => setPassword(e.target.value.replace(/\D/g, "").slice(0, 4))}
              pattern="\d{4}"
              placeholder="••••"
              type="password"
              value={password}
            />
          </label>
          <button className="btn-primary" disabled={savePassword.isPending} type="submit">
            {savePassword.isPending ? "Salvando…" : data?.has_password ? "Alterar PIN" : "Criar PIN"}
          </button>
        </form>
        {pwdError && <p className="text-xs text-danger" role="alert">{pwdError}</p>}
        {savePassword.isSuccess && <p className="text-xs text-green-400">PIN atualizado. Um novo token foi gerado para a extensão.</p>}
      </section>

      {/* Download section */}
      <section className="glass-panel p-4 space-y-3">
        <h3 className="font-medium text-fg">Baixar extensão</h3>
        <p className="text-sm text-muted">
          Instale no Chrome: baixe o ZIP, descompacte e carregue em <strong>chrome://extensions</strong> com o modo desenvolvedor ativado.
        </p>
        <div className="flex flex-col gap-2">
          <a className="btn-primary inline-flex items-center gap-2 justify-center" download href="/api/ig-extension/download-with-token">
            <Download size={15} /> Baixar com credencial <span className="text-xs opacity-70">(sem PIN)</span>
          </a>
          <a className="btn-secondary inline-flex items-center gap-2 justify-center text-sm" download href="/api/ig-extension/download">
            <Download size={14} /> Baixar sem credencial <span className="text-xs opacity-60">(pede PIN ao abrir)</span>
          </a>
        </div>
        <p className="text-xs text-muted">
          <strong>Com credencial</strong>: abre direto, sem PIN. Ideal para uso pessoal.
          &nbsp;·&nbsp;<strong>Sem credencial</strong>: genérico, pede o PIN de 4 dígitos na primeira abertura.
        </p>
      </section>

      {/* Config section */}
      <section className="glass-panel p-4 space-y-4">
        <h3 className="font-medium text-fg">Perfil e configurações da extensão</h3>
        <form className="space-y-4" onSubmit={submitConfig}>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="mb-1 block text-fg-2">Nome completo</span>
              <input className="field" maxLength={200} placeholder="Nome que aparece no perfil" {...field("full_name")} />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-fg-2">Nome de usuário</span>
              <input className="field" maxLength={100} placeholder="@usuario" {...field("username")} />
            </label>
          </div>
          <label className="block text-sm">
            <span className="mb-1 block text-fg-2">Bio</span>
            <textarea className="field min-h-20 py-2" maxLength={500} placeholder="Bio do perfil" {...field("bio")} />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="mb-1 block text-fg-2">URL da foto de perfil</span>
              <input className="field" maxLength={2048} placeholder="https://…" type="url" {...field("profile_photo_url")} />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-fg-2">URL da foto do stories</span>
              <input className="field" maxLength={2048} placeholder="https://…" type="url" {...field("story_photo_url")} />
            </label>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="mb-1 block text-fg-2">Link (URL do sticker)</span>
              <input className="field" maxLength={2048} placeholder="https://…" type="url" {...field("link_url")} />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-fg-2">Texto da figurinha</span>
              <input className="field" maxLength={200} placeholder="Texto do sticker" {...field("sticker_text")} />
            </label>
          </div>
          <label className="block text-sm">
            <span className="mb-1 block text-fg-2">Título do highlight</span>
            <input className="field" maxLength={100} placeholder="Nome do destaque" {...field("highlight_title")} />
          </label>
          <fieldset className="space-y-3 rounded-lg border border-white/10 p-3">
            <legend className="px-1 text-sm font-medium text-fg-2">Figurinha — posição e tamanho</legend>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="block text-sm">
                <span className="mb-1 block text-fg-2">Tamanho (0.1–1.0)</span>
                <input className="field" max={1.0} min={0.1} step={0.05} type="number" {...numField("sticker_size")} />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block text-fg-2">Posição X (0–1)</span>
                <input className="field" max={1.0} min={0.0} step={0.05} type="number" {...numField("sticker_x")} />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block text-fg-2">Posição Y (0–1)</span>
                <input className="field" max={1.0} min={0.0} step={0.05} type="number" {...numField("sticker_y")} />
              </label>
              <label className="block text-sm">
                <span className="mb-1 block text-fg-2">Rotação (rad, -π a π)</span>
                <input className="field" max={3.15} min={-3.15} step={0.1} type="number" {...numField("sticker_rotation")} />
              </label>
            </div>
            {/* Sticker preview */}
            <div className="relative mx-auto w-[100px] overflow-hidden rounded-lg bg-black/40" style={{ aspectRatio: "9/16" }}>
              {data?.story_photo_url && (
                <img alt="Story preview" className="absolute inset-0 h-full w-full object-cover" src={data.story_photo_url} />
              )}
              <div
                className="absolute flex items-center justify-center rounded-lg bg-white/90 px-2 text-[8px] font-bold text-black"
                style={{
                  width: `${ss * 100}%`,
                  height: "8%",
                  left: `${(sx("sticker_x") - ss / 2) * 100}%`,
                  top: `${(sx("sticker_y") - 0.04) * 100}%`,
                  transform: `rotate(${((("sticker_rotation" in form ? form.sticker_rotation : data?.sticker_rotation) as number | null) ?? 0)}rad)`,
                  transition: "all 0.2s",
                }}
              >
                {(("sticker_text" in form ? form.sticker_text : data?.sticker_text) as string | null) ?? "Link"}
              </div>
            </div>
          </fieldset>

          <div className="flex items-center gap-3">
            <button className="btn-primary" disabled={saveConfig.isPending} type="submit">
              {saveConfig.isPending ? "Salvando…" : "Salvar configuração"}
            </button>
            {configSuccess && <span className="text-sm text-green-400">Configuração salva!</span>}
          </div>
          {configError && <p className="text-xs text-danger" role="alert">{configError}</p>}
        </form>
      </section>
    </div>
  );
}

// ─── Main page ─────────────────────────────────────────────────────────────────

type PageTab = "zip" | "ig";

export function ExtensionsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isOwner = user?.role === "OWNER" || (user?.role === "SUPER_ADMIN" && user.workspace_role === "OWNER");
  const [tab, setTab] = useState<PageTab>("ig");
  const [editing, setEditing] = useState<Extension | null | undefined>(undefined);
  const [actionError, setActionError] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ["extensions"],
    queryFn: () => apiRequest<Extension[]>("/api/extensions"),
    enabled: tab === "zip",
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/api/extensions/${id}`, { method: "DELETE" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["extensions"] }),
    onError: (e) => setActionError(errorText(e)),
  });

  const tabs: { value: PageTab; label: string; icon: React.ReactNode }[] = [
    { value: "ig", label: "Extensão IG FlashPost", icon: <Chrome size={15} /> },
    { value: "zip", label: "Outras extensões", icon: <Puzzle size={15} /> },
  ];

  return (
    <div className="tab-host mx-auto max-w-[1100px] space-y-4">
      <header className="space-y-3">
        <h2 className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-[-0.045em] text-fg">
          <Puzzle className="text-accent" size={24} /> Extensões
        </h2>
        <nav aria-label="Abas de extensões" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
          {tabs.map((item) => (
            <button
              aria-current={tab === item.value ? "page" : undefined}
              className={`flex shrink-0 items-center gap-1.5 rounded-full px-4 py-2 text-sm transition ${
                tab === item.value
                  ? "bg-brand/20 font-medium text-accent shadow-[inset_0_0_0_1px_rgba(130,149,255,0.45)]"
                  : "text-muted hover:bg-white/5 hover:text-fg"
              }`}
              key={item.value}
              onClick={() => setTab(item.value)}
              type="button"
            >
              {item.icon} {item.label}
            </button>
          ))}
        </nav>
      </header>

      {tab === "ig" && <IgExtensionTab />}

      {tab === "zip" && (
        <>
          <div className="flex justify-end">
            {isOwner && (
              <button className="btn-primary" onClick={() => setEditing(null)} type="button">
                <Plus size={16} /> Nova extensão
              </button>
            )}
          </div>

          {list.isLoading && <LoadingState label="Carregando extensões" />}
          {list.error && <ErrorState message={errorText(list.error)} onRetry={() => void list.refetch()} />}
          {actionError && <ErrorState message={actionError} />}
          {list.data && list.data.length === 0 && (
            <EmptyState message={isOwner ? "Nenhuma extensão enviada ainda." : "Nenhuma extensão liberada para você."} icon={<Puzzle size={18} />} />
          )}

          <div className="grid gap-3 md:grid-cols-2">
            {list.data?.map((item) => (
              <article className="glass-panel space-y-2 p-4" key={item.id}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="truncate font-medium text-fg">{item.name}</h3>
                    {item.description && <p className="mt-0.5 text-sm text-muted">{item.description}</p>}
                  </div>
                  {isOwner && (
                    <span className="flex shrink-0 items-center gap-1 text-xs text-muted" title={item.visible_to_collaborators ? "Visível para colaboradores" : "Oculta para colaboradores"}>
                      {item.visible_to_collaborators ? <Eye size={14} /> : <EyeOff size={14} />}
                    </span>
                  )}
                </div>
                {item.instructions && (
                  <p className="whitespace-pre-wrap rounded-lg bg-black/25 p-2.5 text-xs leading-5 text-fg-2">{item.instructions}</p>
                )}
                <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                  <span className="text-xs text-muted">
                    {item.has_file ? `${item.file_name} · ${sizeLabel(item.file_size)}` : "Sem arquivo"}
                  </span>
                  <span className="flex gap-1.5">
                    {item.has_file && (
                      <a className="btn-secondary" download href={`/api/extensions/${item.id}/download`}>
                        <Download size={15} /> Baixar
                      </a>
                    )}
                    {isOwner && (
                      <>
                        <button aria-label="Editar" className="btn-ghost" onClick={() => setEditing(item)} type="button"><Pencil size={15} /></button>
                        <button
                          aria-label="Excluir"
                          className="btn-ghost"
                          disabled={remove.isPending}
                          onClick={async () => { if (await confirmAction(`Excluir "${item.name}"?`)) { setActionError(null); remove.mutate(item.id); } }}
                          type="button"
                        >
                          <Trash2 size={15} />
                        </button>
                      </>
                    )}
                  </span>
                </div>
              </article>
            ))}
          </div>

          {editing !== undefined && (
            <EditorModal item={editing} key={editing?.id ?? "new"} onClose={() => setEditing(undefined)} open />
          )}
        </>
      )}
    </div>
  );
}
