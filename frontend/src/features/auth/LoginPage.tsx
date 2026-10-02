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
            ? "/admin"
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
        to={user.role === "SUPER_ADMIN" ? "/admin" : "/dashboard"}
        replace
      />
    );
  }

  const apiError =
    mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <main className="relative grid min-h-screen overflow-hidden bg-[#070809] px-5 py-8 lg:grid-cols-[1.05fr_0.95fr] lg:px-12">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_20%_48%,rgba(83,109,254,0.08),transparent_45%)]" />
      <section className="relative mx-auto flex w-full max-w-xl flex-col justify-between lg:mx-0">
        <Link to="/" className="flex w-fit items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl border border-[#33447c] bg-[#11182d] text-sm font-bold text-[#9baaff]">
            F
          </span>
          <span className="text-base font-semibold tracking-[-0.03em] text-[#f5f7fb]">
            flashpost<span className="text-[#7186ff]">.</span>
          </span>
        </Link>
        <div className="my-16 max-w-lg lg:my-0">
          <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-[#27334a] bg-[#0d1015] px-3 py-1.5 text-xs text-[#aeb9ce]">
            <ShieldCheck size={14} className="text-[#8295ff]" />
            Acesso seguro à sua operação
          </p>
          <h1 className="text-4xl font-semibold leading-tight tracking-[-0.06em] text-[#f5f7fb] sm:text-5xl">
            Bom ter você
            <br />
            <span className="text-[#7186ff]">de volta.</span>
          </h1>
          <p className="mt-5 max-w-md text-base leading-7 text-[#94a3b8]">
            Entre no FlashPost para continuar acompanhando seu espaço de trabalho.
          </p>
        </div>
        <p className="hidden text-xs text-[#64748b] lg:block">
          FlashPost · Acesso protegido
        </p>
      </section>

      <section className="relative mx-auto flex w-full max-w-md items-center lg:mx-0 lg:ml-auto">
        <div className="w-full rounded-2xl border border-[#202838] bg-[#0d1015] p-6 shadow-[0_24px_80px_rgba(0,0,0,0.28)] sm:p-8">
          <div className="mb-7">
            <h2 className="text-xl font-semibold tracking-[-0.035em] text-[#f5f7fb]">
              Entrar
            </h2>
            <p className="mt-2 text-sm text-[#94a3b8]">
              Use o e-mail e a senha da sua conta.
            </p>
          </div>
          <form
            className="space-y-5"
            onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
            noValidate
          >
            <div>
              <label htmlFor="email" className="mb-2 block text-sm font-medium text-[#c7cfdd]">
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
                className="h-11 w-full rounded-lg border border-[#27334a] bg-[#090b0e] px-3.5 text-sm text-[#f5f7fb] outline-none transition placeholder:text-[#536176] focus:border-[#536dfe] focus:ring-2 focus:ring-[#536dfe]/20"
                placeholder="voce@empresa.com"
              />
              {form.formState.errors.email && (
                <p id="email-error" className="mt-1.5 text-xs text-[#f1a3ad]">
                  {form.formState.errors.email.message}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="password" className="mb-2 block text-sm font-medium text-[#c7cfdd]">
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
                  className="h-11 w-full rounded-lg border border-[#27334a] bg-[#090b0e] px-3.5 pr-12 text-sm text-[#f5f7fb] outline-none transition placeholder:text-[#536176] focus:border-[#536dfe] focus:ring-2 focus:ring-[#536dfe]/20"
                  placeholder="Sua senha"
                />
                <button
                  type="button"
                  onClick={() => setPasswordVisible((visible) => !visible)}
                  aria-label={passwordVisible ? "Ocultar senha" : "Mostrar senha"}
                  className="absolute inset-y-0 right-0 grid w-11 place-items-center text-[#64748b] hover:text-[#c7cfdd]"
                >
                  {passwordVisible ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
              {form.formState.errors.password && (
                <p id="password-error" className="mt-1.5 text-xs text-[#f1a3ad]">
                  {form.formState.errors.password.message}
                </p>
              )}
            </div>

            {apiError && (
              <div
                className="rounded-lg border border-[#47252d] bg-[#1a1013] px-3.5 py-3 text-sm text-[#f1a3ad]"
                role="alert"
              >
                {apiError}
              </div>
            )}

            <button
              type="submit"
              disabled={mutation.isPending}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#536dfe] px-4 text-sm font-semibold text-white transition hover:bg-[#667eea] focus:outline-none focus:ring-2 focus:ring-[#8da0ff] focus:ring-offset-2 focus:ring-offset-[#0d1015] disabled:cursor-wait disabled:opacity-70"
            >
              {mutation.isPending && <LoaderCircle size={16} className="animate-spin" />}
              {mutation.isPending ? "Entrando..." : "Entrar"}
            </button>
          </form>
          <p className="mt-6 border-t border-[#202838] pt-5 text-xs leading-5 text-[#64748b]">
            Ainda não tem uma conta?{" "}
            <Link to="/register" className="font-medium text-[#aab7ff] hover:text-white">
              Criar conta
            </Link>
          </p>
        </div>
      </section>
    </main>
  );
}

function LoginLoading() {
  return (
    <main className="grid min-h-screen place-items-center bg-[#070809] text-sm text-[#94a3b8]">
      Verificando sessão segura...
    </main>
  );
}
