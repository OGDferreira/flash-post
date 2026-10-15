import {
  Clipboard,
} from "lucide-react";

import { ApiError } from "@/services/api";

export type EmailStatus = "available" | "in_use" | "completed" | "error" | "returned";
export type EmailAccount = {
  id: string;
  supplier: string;
  email: string;
  password: string;
  responsible: string | null;
  status: EmailStatus;
  observation: string | null;
  two_factor_code: string;
  two_factor_password: string;
  attachment_url: string | null;
  created_at: string;
  updated_at: string;
  import_batch_id: string | null;
};
export type EmailForm = Pick<
  EmailAccount,
  "supplier" | "email" | "password" | "two_factor_code" | "two_factor_password"
>;
export type EmailsResponse = {
  can_manage: boolean;
  accounts: EmailAccount[];
  counts: {
    total: number;
    available: number;
    in_use: number;
    completed: number;
    error: number;
    returned: number;
  };
};

export const emptyForm: EmailForm = {
  supplier: "",
  email: "",
  password: "",
  two_factor_code: "",
  two_factor_password: "",
};
export const statuses: { id: EmailStatus; label: string }[] = [
  { id: "available", label: "Disponível" },
  { id: "in_use", label: "Em Uso" },
  { id: "completed", label: "Concluído" },
  { id: "error", label: "Erro" },
  { id: "returned", label: "Retornado" },
];
export const nextStatus: Record<EmailStatus, EmailStatus> = {
  available: "in_use",
  in_use: "completed",
  completed: "error",
  error: "returned",
  returned: "available",
};
export const statusStyles: Record<EmailStatus, string> = {
  available: "border-success/30 bg-success-soft text-success",
  in_use: "border-line bg-brand-soft text-accent",
  completed: "border-line bg-well text-accent",
  error: "border-danger/30 bg-danger-soft text-danger",
  returned: "border-warning/30 bg-warning-soft text-warning",
};

export function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : error ? fallback : null;
}

export function notify(message: string) {
  window.dispatchEvent(new CustomEvent("flashpost-toast", { detail: message }));
}

export function StatusLabel({ status }: { status: EmailStatus }) {
  return statuses.find((item) => item.id === status)?.label ?? status;
}

export function SummaryCard({
  label,
  count,
  status,
}: {
  label: string;
  count: number;
  status?: EmailStatus;
}) {
  return (
    <article className="dashboard-card rounded-xl p-4">
      <p className="text-xs text-muted">{label}</p>
      <p
        className={`mt-2 text-2xl font-semibold ${
          status ? statusStyles[status].split(" ").at(-1) : "text-fg"
        }`}
      >
        {count}
      </p>
    </article>
  );
}

export function CopyValue({ value, label }: { value: string; label: string }) {
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      notify(`${label} copiado`);
    } catch {
      notify(`Não foi possível copiar ${label.toLowerCase()}.`);
    }
  }

  return (
    <button
      className="inline-flex max-w-full items-center gap-1.5 break-all text-left text-fg hover:text-accent"
      onClick={() => void copy()}
      title={`Copiar ${label}`}
      type="button"
    >
      <span>{value || "—"}</span>
      <Clipboard className="shrink-0 text-muted" size={12} />
    </button>
  );
}
