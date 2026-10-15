import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";

export type ConfirmOptions = {
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Destructive actions get the danger button. */
  danger?: boolean;
};

type Pending = ConfirmOptions & { resolve: (ok: boolean) => void };

let listener: ((pending: Pending) => void) | null = null;

const DANGER_VERBS = ["Excluir", "Remover", "Desconectar", "Apagar"];

/** Splits a legacy one-string message into title + detail and infers the verb. */
function normalize(input: string | ConfirmOptions): ConfirmOptions {
  if (typeof input !== "string") return input;
  const text = input.trim();
  const cut = text.search(/[?.]\s/);
  const title = cut === -1 ? text : text.slice(0, cut + 1);
  const message = cut === -1 ? undefined : text.slice(cut + 2).trim() || undefined;
  const verb = text.split(/\s+/)[0] ?? "";
  const danger = DANGER_VERBS.includes(verb);
  return {
    title,
    message,
    danger,
    confirmLabel: danger || /^(Gerar|Aplicar|Registrar)$/.test(verb) ? verb : "Confirmar",
  };
}

/** Promise-based replacement for window.confirm; renders <ConfirmHost />. */
export function confirmAction(input: string | ConfirmOptions): Promise<boolean> {
  const options = normalize(input);
  if (!listener) return Promise.resolve(window.confirm(options.title));
  return new Promise((resolve) => listener?.({ ...options, resolve }));
}

export function ConfirmHost() {
  const [queue, setQueue] = useState<Pending[]>([]);
  useEffect(() => {
    listener = (pending) => setQueue((current) => [...current, pending]);
    return () => {
      listener = null;
    };
  }, []);
  const current = queue[0];
  const close = (ok: boolean) => {
    current?.resolve(ok);
    setQueue((items) => items.slice(1));
  };
  return (
    <Modal onClose={() => close(false)} open={Boolean(current)} title={current?.title ?? ""}>
      {current && (
        <div className="space-y-5">
          {current.message && <p className="text-sm leading-6 text-fg-2">{current.message}</p>}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button onClick={() => close(false)} variant="secondary">
              {current.cancelLabel ?? "Cancelar"}
            </Button>
            <Button onClick={() => close(true)} variant={current.danger ? "danger" : "primary"}>
              {current.confirmLabel ?? "Confirmar"}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
