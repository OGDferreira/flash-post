import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle } from "lucide-react";

import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/features/auth/AuthProvider";
import { isValidCpf, maskCpf } from "@/features/auth/cpf";
import { ApiError, apiRequest, type User } from "@/services/api";

/** Blocking pop-up for accounts created before the CPF became required. They can't
 *  use the app until they complete it, so the dialog has no way out (no backdrop/X
 *  close). A Super Admin viewing the account via "Entrar" is never prompted. */
export function CompleteProfileGate() {
  const { user } = useAuth();
  const cache = useQueryClient();
  const [cpf, setCpf] = useState("");
  const submit = useMutation({
    mutationFn: () =>
      apiRequest<User>("/api/profile/complete", { method: "POST", body: { cpf } }),
    onSuccess: (updated) => {
      cache.setQueryData(["auth", "me"], updated);
      cache.setQueryData(["profile"], updated);
    },
  });

  if (!user || user.impersonator_name || user.profile_complete !== false) return null;

  const valid = isValidCpf(cpf);
  const apiError = submit.error instanceof ApiError ? submit.error.message : null;

  return (
    <Modal
      open
      title="Complete seu cadastro"
      description="Para continuar usando a plataforma, informe seu CPF. Ele é usado apenas para verificação da sua conta."
      onClose={() => {}}
      busy={submit.isPending}
      footer={
        <button
          type="submit"
          form="complete-profile-form"
          disabled={!valid || submit.isPending}
          className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand focus:outline-none focus:ring-2 focus:ring-brand disabled:cursor-not-allowed disabled:opacity-70"
        >
          {submit.isPending && <LoaderCircle size={16} className="animate-spin" />}
          {submit.isPending ? "Salvando..." : "Salvar e continuar"}
        </button>
      }
    >
      <form
        id="complete-profile-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (valid) submit.mutate();
        }}
      >
        <label htmlFor="complete-cpf" className="mb-1.5 block text-sm font-medium text-fg-2">
          CPF
        </label>
        <input
          id="complete-cpf"
          inputMode="numeric"
          autoComplete="off"
          maxLength={14}
          placeholder="000.000.000-00"
          value={cpf}
          onChange={(event) => setCpf(maskCpf(event.target.value))}
          aria-invalid={cpf.length > 0 && !valid}
          className="h-11 w-full rounded-lg border border-line bg-surface-inset px-3.5 text-sm text-fg outline-none transition placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
        {cpf.length > 0 && !valid && (
          <p className="mt-1.5 text-xs text-danger">Informe um CPF válido.</p>
        )}
        {apiError && (
          <p className="mt-2 rounded-lg border border-danger/30 bg-danger-soft px-3.5 py-2.5 text-sm text-danger" role="alert">
            {apiError}
          </p>
        )}
      </form>
    </Modal>
  );
}
