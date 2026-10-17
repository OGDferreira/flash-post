import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ApiError, apiRequest } from "@/services/api";

/** Saves a funnel export (JSON with media embedded) as a file. */
export async function downloadFlow(path: string, name: string) {
  const data = await apiRequest<unknown>(path);
  const blob = new Blob([JSON.stringify(data)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${name.replace(/[^\w -]+/g, "").trim().replace(/\s+/g, "-") || "funil"}.flashpost.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function ImportFlowModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const [mode, setMode] = useState<"file" | "code">("file");
  const [file, setFile] = useState<File | null>(null);
  const [code, setCode] = useState("");
  const run = useMutation({
    mutationFn: async () =>
      mode === "file"
        ? apiRequest("/api/bots/flows/import", { method: "POST", body: await file!.text() })
        : apiRequest("/api/bots/flows/import-code", { method: "POST", body: { code: code.trim() } }),
    onSuccess: () => {
      setFile(null);
      setCode("");
      onDone();
      onClose();
    },
  });
  const ready = mode === "file" ? Boolean(file) : code.trim().length >= 10;
  return (
    <Modal
      busy={run.isPending}
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button disabled={!ready || run.isPending} onClick={() => run.mutate()} variant="primary">
            {run.isPending ? "Importando…" : "Importar"}
          </Button>
        </>
      }
      onClose={onClose}
      open={open}
      title="Importar funil"
    >
      <div className="space-y-4">
        <div className="inline-flex gap-1 rounded-full bg-well p-1">
          {(["file", "code"] as const).map((value) => (
            <button
              className={`min-h-9 rounded-full px-4 text-sm ${mode === value ? "bg-brand text-white" : "text-muted"}`}
              key={value}
              onClick={() => setMode(value)}
              type="button"
            >
              {value === "file" ? "Arquivo" : "Código"}
            </button>
          ))}
        </div>
        {mode === "file" ? (
          <label className="grid gap-1.5 text-sm text-fg-2">
            Arquivo .flashpost.json exportado
            <input accept=".json,application/json" className="field" onChange={(event) => setFile(event.target.files?.[0] ?? null)} type="file" />
          </label>
        ) : (
          <label className="grid gap-1.5 text-sm text-fg-2">
            Código de importação
            <textarea className="field min-h-24 font-mono text-xs" onChange={(event) => setCode(event.target.value)} value={code} />
          </label>
        )}
        <p className="text-xs text-muted">
          O funil volta completo: textos, botões, mídias, planos, upsells e downsells. Se a entrega for em grupo, escolha o seu grupo no editor.
        </p>
        {run.error && <p className="text-xs text-danger">{run.error instanceof ApiError ? run.error.message : "Não foi possível importar."}</p>}
      </div>
    </Modal>
  );
}
