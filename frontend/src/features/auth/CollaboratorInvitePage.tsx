import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CircleCheck, LoaderCircle } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { BrandLogo } from "@/components/BrandLogo";
import { ApiError, apiRequest } from "@/services/api";
import { isValidPublicNickname } from "@/features/auth/nickname";

type InviteInfo = { workspace_name: string; expires_at: string };

/** Public page opened from an owner's invite link: the collaborator self-registers. */
export function CollaboratorInvitePage() {
  const { token = "" } = useParams();
  const info = useQuery({
    queryKey: ["collaborator-invite", token],
    queryFn: () => apiRequest<InviteInfo>(`/api/auth/collaborator-invites/${encodeURIComponent(token)}`),
    retry: false,
  });
  const [values, setValues] = useState({ full_name: "", email: "", nickname: "", password: "", confirm_password: "" });
  const [localError, setLocalError] = useState<string | null>(null);
  const signup = useMutation({
    mutationFn: () =>
      apiRequest<{ message: string }>(`/api/auth/collaborator-invites/${encodeURIComponent(token)}/register`, {
        method: "POST",
        body: values,
      }),
  });
  const set = (key: keyof typeof values) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setValues((current) => ({ ...current, [key]: event.target.value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!isValidPublicNickname(values.nickname)) return setLocalError("Use um apelido entre 2 e 40 caracteres.");
    if (values.password.length < 8) return setLocalError("Use pelo menos 8 caracteres na senha.");
    if (values.password !== values.confirm_password) return setLocalError("As senhas não coincidem.");
    setLocalError(null);
    signup.mutate();
  };
  const serverError =
    signup.error instanceof ApiError ? signup.error.message : signup.error ? "Não foi possível enviar o cadastro." : null;

  return (
    <main className="grid min-h-svh place-items-center px-4 py-8">
      <div className="glass-panel w-full max-w-md p-5 sm:p-7">
        <div className="mb-5 flex items-center gap-3">
          <BrandLogo className="size-10" />
          <span className="text-base font-semibold tracking-[-0.03em] text-fg">FlashPost</span>
        </div>

        {info.isLoading ? (
          <p className="text-sm text-muted">Verificando convite…</p>
        ) : info.error || !info.data ? (
          <>
            <h1 className="text-xl font-semibold text-fg">Convite indisponível</h1>
            <p className="mt-2 text-sm text-muted">
              Este link não é válido, já foi usado ou expirou. Peça um novo link ao chefe.
            </p>
            <Link className="btn-secondary mt-5" to="/login">Ir para o login</Link>
          </>
        ) : signup.isSuccess ? (
          <>
            <CircleCheck className="text-success" size={28} />
            <h1 className="mt-3 text-xl font-semibold text-fg">Cadastro enviado</h1>
            <p className="mt-2 text-sm text-muted">
              Aguarde a aprovação do chefe e do administrador. Quando os dois liberarem, você já pode entrar com seu e-mail e senha.
            </p>
            <Link className="btn-secondary mt-5" to="/login">Ir para o login</Link>
          </>
        ) : (
          <form className="space-y-3" onSubmit={submit}>
            <div>
              <h1 className="text-xl font-semibold text-fg">Criar acesso de colaborador</h1>
              <p className="mt-1 text-sm text-muted">
                Você foi convidado para <strong className="text-fg-2">{info.data.workspace_name}</strong>. O chefe
                libera o acesso depois do cadastro.
              </p>
            </div>
            <input aria-label="Nome completo" autoComplete="name" className="field" onChange={set("full_name")} placeholder="Nome completo" required value={values.full_name} />
            <input aria-label="E-mail" autoComplete="email" className="field" onChange={set("email")} placeholder="E-mail" required type="email" value={values.email} />
            <input aria-label="Apelido" className="field" onChange={set("nickname")} placeholder="Apelido" required value={values.nickname} />
            <input aria-label="Senha" autoComplete="new-password" className="field" onChange={set("password")} placeholder="Senha (mínimo 8 caracteres)" required type="password" value={values.password} />
            <input aria-label="Confirmar senha" autoComplete="new-password" className="field" onChange={set("confirm_password")} placeholder="Confirmar senha" required type="password" value={values.confirm_password} />
            {(localError || serverError) && (
              <p className="rounded-xl border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">
                {localError ?? serverError}
              </p>
            )}
            <button className="btn-primary w-full" disabled={signup.isPending} type="submit">
              {signup.isPending && <LoaderCircle className="animate-spin" size={16} />}
              Enviar cadastro
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
