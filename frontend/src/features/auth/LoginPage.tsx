import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, LoaderCircle, ShieldCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { useAuth } from "@/features/auth/AuthProvider";
import { ApiError, apiRequest, type User } from "@/services/api";

const loginSchema = z.object({
  email: z.string().trim().email("Informe um e-mail válido."),
  password: z.string().min(1, "Informe sua senha.").max(256),
});
type LoginValues = z.infer<typeof loginSchema>;
type LoginResponse = { user: User; csrf_token: string };

export function LoginPage() {
  const { user, isLoading } = useAuth();
  const [passwordVisible, setPasswordVisible] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const registrationPending =
    (location.state as { registrationPending?: boolean } | null)?.registrationPending === true;
  const queryClient = useQueryClient();
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const mutation = useMutation({
    mutationFn: (values: LoginValues) =>
      apiRequest<LoginResponse>("/api/auth/login", {
        method: "POST",
        body: values,
      }),
    onSuccess: ({ user: signedInUser }) => {
      queryClient.setQueryData(["auth", "me"], signedInUser);
      const requestedPath = (location.state as { from?: string } | null)?.from;
      const destination =
        requestedPath?.startsWith("/") && !requestedPath.startsWith("//")
          ? requestedPath
          : signedInUser.role === "SUPER_ADMIN"
            ? signedInUser.workspace_role === "OWNER"
              ? "/dashboard"
              : signedInUser.workspace_role === "COLLABORATOR"
                ? "/feature/accounts"
                : "/admin"
            : "/dashboard";
      navigate(destination, { replace: true });
    },
  });

  if (isLoading) {
    return <LoginLoading />;
  }
  if (user) {
    return (
      <Navigate
        to={
          user.role === "SUPER_ADMIN"
            ? user.workspace_role === "OWNER"
              ? "/dashboard"
              : user.workspace_role === "COLLABORATOR"
                ? "/feature/accounts"
                : "/admin"
            : "/dashboard"
        }
        replace
      />
    );
  }

  const apiError =
    mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <main className="relative grid min-h-svh place-items-center overflow-x-hidden bg-transparent px-4 py-4 sm:px-5 sm:py-10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_20%_48%,rgba(83,109,254,0.08),transparent_45%)]" />
      <div className="relative grid w-full max-w-[960px] overflow-hidden rounded-2xl border border-line-soft bg-surface shadow-[0_24px_80px_rgba(0,0,0,0.28)] md:grid-cols-[0.95fr_1.05fr]">
        <section className="flex flex-col justify-between gap-10 p-4 sm:p-6 md:min-h-[540px] md:p-9">
          <Link to="/" className="flex w-fit items-center gap-3">
            <img
              src="/flashpost-logo.png"
              alt="FlashPost"
              width="40"
              height="40"
              className="size-10 shrink-0 object-contain"
            />
            <span className="text-base font-semibold tracking-[-0.03em] text-fg">
              FlashPost<span className="text-accent">.</span>
            </span>
          </Link>
          <div className="max-w-sm md:my-auto">
            <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-xs text-fg-2">
              <ShieldCheck size={14} className="text-accent" />
              Acesso seguro à sua operação
            </p>
            <h1 className="text-4xl font-semibold leading-tight tracking-[-0.06em] text-fg sm:text-5xl">
              Bom ter você
              <br />
              <span className="text-accent">de volta.</span>
            </h1>
            <p className="mt-5 max-w-md text-base leading-7 text-muted">
              Entre no FlashPost para continuar acompanhando seu espaço de trabalho.
            </p>
          </div>
          <p className="hidden text-xs text-muted md:block">
            FlashPost · Acesso protegido
          </p>
        </section>

        <section className="flex items-center border-t border-line-soft p-4 sm:p-6 md:border-l md:border-t-0 md:p-9">
          <div className="w-full max-w-md md:mx-auto">
          <div className="mb-7">
            <h2 className="text-xl font-semibold tracking-[-0.035em] text-fg">
              Entrar
            </h2>
            <p className="mt-2 text-sm text-muted">
              Use o e-mail e a senha da sua conta.
            </p>
            {registrationPending && (
              <p
                className="mt-4 rounded-lg border border-line bg-brand-soft px-3.5 py-3 text-sm text-[#c8c8ff]"
                role="status"
              >
                Cadastro recebido. Seu acesso será liberado após aprovação do administrador.
              </p>
            )}
          </div>
          <form
            className="space-y-4"
            onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
            noValidate
          >
            <div>
              <label htmlFor="email" className="mb-2 block text-sm font-medium text-fg-2">
                E-mail
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                inputMode="email"
                autoCapitalize="none"
                spellCheck={false}
                {...form.register("email")}
                aria-invalid={Boolean(form.formState.errors.email)}
                aria-describedby={form.formState.errors.email ? "email-error" : undefined}
                className="h-11 w-full rounded-lg border border-line bg-surface-inset px-3.5 text-sm text-fg outline-none transition placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
                placeholder="voce@empresa.com"
              />
              {form.formState.errors.email && (
                <p id="email-error" className="mt-1.5 text-xs text-danger">
                  {form.formState.errors.email.message}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="password" className="mb-2 block text-sm font-medium text-fg-2">
                Senha
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={passwordVisible ? "text" : "password"}
                  autoComplete="current-password"
                  {...form.register("password")}
                  aria-invalid={Boolean(form.formState.errors.password)}
                  aria-describedby={form.formState.errors.password ? "password-error" : undefined}
                  className="h-11 w-full rounded-lg border border-line bg-surface-inset px-3.5 pr-12 text-sm text-fg outline-none transition placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
                  placeholder="Sua senha"
                />
                <button
                  type="button"
                  onClick={() => setPasswordVisible((visible) => !visible)}
                  aria-label={passwordVisible ? "Ocultar senha" : "Mostrar senha"}
                  className="absolute inset-y-0 right-0 grid w-11 place-items-center text-muted hover:text-fg-2"
                >
                  {passwordVisible ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
              {form.formState.errors.password && (
                <p id="password-error" className="mt-1.5 text-xs text-danger">
                  {form.formState.errors.password.message}
                </p>
              )}
            </div>

            {apiError && (
              <div
                className="rounded-lg border border-danger/30 bg-danger-soft px-3.5 py-3 text-sm text-danger"
                role="alert"
              >
                {apiError}
              </div>
            )}

            <button
              type="submit"
              disabled={mutation.isPending}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand focus:outline-none focus:ring-2 focus:ring-brand focus:ring-offset-2 focus:ring-offset-[#0d1015] disabled:cursor-wait disabled:opacity-70"
            >
              {mutation.isPending && <LoaderCircle size={16} className="animate-spin" />}
              {mutation.isPending ? "Entrando..." : "Entrar"}
            </button>
          </form>
          <p className="mt-6 border-t border-line-soft pt-5 text-xs leading-5 text-muted">
            Ainda não tem uma conta?{" "}
            <Link to="/register" className="font-medium text-accent hover:text-white">
              Criar conta
            </Link>
          </p>
          </div>
        </section>
      </div>
    </main>
  );
}

function LoginLoading() {
  return (
    <main className="grid min-h-screen place-items-center bg-transparent text-sm text-muted">
      Verificando sessão segura...
    </main>
  );
}
