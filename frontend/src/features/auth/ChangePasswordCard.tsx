import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Eye, EyeOff, KeyRound } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ApiError, apiRequest, setCsrfToken } from "@/services/api";

type Fields = { current_password: string; new_password: string; confirm_password: string };
const empty: Fields = { current_password: "", new_password: "", confirm_password: "" };

/** Perfil > Segurança: change your own password (the current one is required). */
export function ChangePasswordCard() {
  const [fields, setFields] = useState<Fields>(empty);
  const [show, setShow] = useState(false);
  const [done, setDone] = useState(false);
  const change = useMutation({
    mutationFn: (body: Fields) =>
      apiRequest<{ message: string; csrf_token: string | null }>("/api/profile/password", { method: "POST", body }),
    onSuccess: (result) => {
      if (result.csrf_token) setCsrfToken(result.csrf_token);
      setFields(empty);
      setDone(true);
    },
  });
  const tooShort = fields.new_password.length > 0 && fields.new_password.length < 8;
  const mismatch = fields.confirm_password.length > 0 && fields.confirm_password !== fields.new_password;
  const valid = fields.current_password && fields.new_password.length >= 8 && !mismatch && fields.confirm_password;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    setDone(false);
    change.mutate(fields);
  };
  const input = (name: keyof Fields, label: string, autoComplete: string, hint?: string | false) => (
    <label className="block">
      <span className="text-xs font-medium text-fg-2">{label}</span>
      <input
        autoComplete={autoComplete}
        className="field mt-1.5 w-full"
        maxLength={256}
        onChange={(event) => setFields((current) => ({ ...current, [name]: event.target.value }))}
        required
        type={show ? "text" : "password"}
        value={fields[name]}
      />
      {hint && <span className="mt-1 block text-[11px] text-danger">{hint}</span>}
    </label>
  );
  return (
    <section aria-labelledby="password-title" className="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-base font-semibold text-fg" id="password-title">
          <KeyRound className="text-accent" size={18} /> Alterar senha
        </h2>
        <button className="btn-ghost btn-sm" onClick={() => setShow((value) => !value)} type="button">
          {show ? <EyeOff size={14} /> : <Eye size={14} />} {show ? "Ocultar" : "Mostrar"}
        </button>
      </div>
      <p className="mt-1 text-xs text-muted">Vale para o Flash e o Flash (é o mesmo login).</p>
      <form className="mt-4 grid gap-3 sm:grid-cols-3" onSubmit={submit}>
        {input("current_password", "Senha atual", "current-password")}
        {input("new_password", "Nova senha", "new-password", tooShort && "Use pelo menos 8 caracteres.")}
        {input("confirm_password", "Confirmar nova senha", "new-password", mismatch && "As senhas não conferem.")}
        <div className="flex flex-wrap items-center gap-3 sm:col-span-3">
          <button className="btn-primary" disabled={!valid || change.isPending} type="submit">
            {change.isPending ? "Salvando…" : "Salvar nova senha"}
          </button>
          {done && (
            <span className="flex items-center gap-1.5 text-sm text-success" role="status">
              <CheckCircle2 size={16} /> Senha alterada.
            </span>
          )}
          {change.error && (
            <span className="text-sm text-danger" role="alert">
              {change.error instanceof ApiError ? change.error.message : "Não foi possível alterar a senha."}
            </span>
          )}
        </div>
      </form>
    </section>
  );
}
