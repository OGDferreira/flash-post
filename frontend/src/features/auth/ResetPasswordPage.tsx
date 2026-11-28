import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Eye, EyeOff, LoaderCircle } from "lucide-react";
import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { AuthShell } from "@/features/auth/AuthShell";
import { ApiError, apiRequest } from "@/services/api";

const schema = z
  .object({
    new_password: z.string().min(8, "Use pelo menos 8 caracteres.").max(256),
    confirm_password: z.string().min(1, "Confirme a senha."),
  })
  .refine((v) => v.new_password === v.confirm_password, {
    message: "As senhas não coincidem.",
    path: ["confirm_password"],
  });
type Values = z.infer<typeof schema>;

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [done, setDone] = useState(false);
  const [visibleNew, setVisibleNew] = useState(false);
  const [visibleConfirm, setVisibleConfirm] = useState(false);

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { new_password: "", confirm_password: "" },
  });
  const mutation = useMutation({
    mutationFn: (values: Values) =>
      apiRequest<{ message: string }>("/api/auth/reset-password", {
        method: "POST",
        body: { ...values, token },
      }),
    onSuccess: () => setDone(true),
  });

  const apiError = mutation.error instanceof ApiError ? mutation.error.message : null;

  if (!token) {
    return (
      <AuthShell mode="login">
        <section className="flex items-center border-t border-line-soft p-4 sm:p-8 md:border-l md:border-t-0 md:p-10">
          <div className="w-full max-w-md md:mx-auto">
            <p className="text-sm text-danger">Link inválido. Solicite um novo link de redefinição.</p>
            <p className="mt-4 text-sm text-muted">
              <Link to="/esqueci-senha" className="font-medium text-accent hover:text-white">
                Solicitar novo link
              </Link>
            </p>
          </div>
        </section>
      </AuthShell>
    );
  }

  return (
    <AuthShell mode="login">
      <section className="flex items-center border-t border-line-soft p-4 sm:p-8 md:border-l md:border-t-0 md:p-10">
        <div className="w-full max-w-md md:mx-auto">
          <div className="mb-4 sm:mb-7">
            <h2 className="text-xl font-semibold tracking-[-0.035em] text-fg">
              Redefinir senha
            </h2>
            <p className="mt-2 text-sm text-muted">
              Escolha uma nova senha para a sua conta.
            </p>
          </div>

          {done ? (
            <div className="space-y-4">
              <div className="rounded-lg border border-line bg-brand-soft px-3.5 py-4 text-sm text-[#c8c8ff]" role="status">
                Senha redefinida com sucesso.
              </div>
              <Link
                to="/login"
                className="flex h-10 w-full items-center sm:h-11 justify-center rounded-lg bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand"
              >
                Entrar
              </Link>
            </div>
          ) : (
            <form
              className="space-y-3 sm:space-y-4"
              onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
              noValidate
            >
              <div>
                <label htmlFor="rp-new" className="mb-1.5 block text-sm font-medium text-fg-2 sm:mb-2">
                  Nova senha
                </label>
                <div className="relative">
                  <input
                    id="rp-new"
                    type={visibleNew ? "text" : "password"}
                    autoComplete="new-password"
                    {...form.register("new_password")}
                    aria-invalid={Boolean(form.formState.errors.new_password)}
                    className="h-10 w-full sm:h-11 rounded-lg border border-line bg-surface-inset px-3.5 pr-12 text-sm text-fg outline-none transition placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
                  />
                  <button
                    type="button"
                    onClick={() => setVisibleNew((v) => !v)}
                    aria-label={visibleNew ? "Ocultar senha" : "Mostrar senha"}
                    className="absolute inset-y-0 right-0 grid w-11 place-items-center text-muted hover:text-fg-2"
                  >
                    {visibleNew ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
                {form.formState.errors.new_password && (
                  <p className="mt-1.5 text-xs text-danger">{form.formState.errors.new_password.message}</p>
                )}
              </div>

              <div>
                <label htmlFor="rp-confirm" className="mb-1.5 block text-sm font-medium text-fg-2 sm:mb-2">
                  Confirmar nova senha
                </label>
                <div className="relative">
                  <input
                    id="rp-confirm"
                    type={visibleConfirm ? "text" : "password"}
                    autoComplete="new-password"
                    {...form.register("confirm_password")}
                    aria-invalid={Boolean(form.formState.errors.confirm_password)}
                    className="h-10 w-full sm:h-11 rounded-lg border border-line bg-surface-inset px-3.5 pr-12 text-sm text-fg outline-none transition placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
                  />
                  <button
                    type="button"
                    onClick={() => setVisibleConfirm((v) => !v)}
                    aria-label={visibleConfirm ? "Ocultar senha" : "Mostrar senha"}
                    className="absolute inset-y-0 right-0 grid w-11 place-items-center text-muted hover:text-fg-2"
                  >
                    {visibleConfirm ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
                {form.formState.errors.confirm_password && (
                  <p className="mt-1.5 text-xs text-danger">{form.formState.errors.confirm_password.message}</p>
                )}
              </div>

              {apiError && (
                <div className="rounded-lg border border-danger/30 bg-danger-soft px-3.5 py-3 text-sm text-danger" role="alert">
                  {apiError}
                  {apiError.includes("inválido") && (
                    <span>
                      {" "}
                      <Link to="/esqueci-senha" className="underline">
                        Solicitar novo link.
                      </Link>
                    </span>
                  )}
                </div>
              )}

              <button
                type="submit"
                disabled={mutation.isPending}
                className="flex h-10 w-full items-center sm:h-11 justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand focus:outline-none focus:ring-2 focus:ring-brand focus:ring-offset-2 focus:ring-offset-[#0d1015] disabled:cursor-wait disabled:opacity-70"
              >
                {mutation.isPending && <LoaderCircle size={16} className="animate-spin" />}
                {mutation.isPending ? "Salvando..." : "Redefinir senha"}
              </button>
            </form>
          )}
        </div>
      </section>
    </AuthShell>
  );
}
