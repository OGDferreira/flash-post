import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { LoaderCircle } from "lucide-react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import { AuthShell } from "@/features/auth/AuthShell";
import { ApiError, apiRequest } from "@/services/api";

const schema = z.object({
  email: z.string().trim().email("Informe um e-mail válido."),
});
type Values = z.infer<typeof schema>;

export function ForgotPasswordPage() {
  const [sent, setSent] = useState(false);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "" },
  });
  const mutation = useMutation({
    mutationFn: (values: Values) =>
      apiRequest<{ message: string }>("/api/auth/forgot-password", {
        method: "POST",
        body: values,
      }),
    onSuccess: () => setSent(true),
  });

  const apiError = mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <AuthShell mode="login">
      <section className="flex items-center border-t border-line-soft p-4 sm:p-8 md:border-l md:border-t-0 md:p-10">
        <div className="w-full max-w-md md:mx-auto">
          <div className="mb-4 sm:mb-7">
            <h2 className="text-xl font-semibold tracking-[-0.035em] text-fg">
              Esqueci minha senha
            </h2>
            <p className="mt-2 text-sm text-muted">
              Informe o e-mail da sua conta e enviaremos um link para redefinir a senha.
            </p>
          </div>

          {sent ? (
            <div className="rounded-lg border border-line bg-brand-soft px-3.5 py-4 text-sm text-[#c8c8ff]" role="status">
              Se o e-mail estiver cadastrado, você receberá o link de redefinição em breve.
              Verifique também a caixa de spam.
            </div>
          ) : (
            <form
              className="space-y-3 sm:space-y-4"
              onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
              noValidate
            >
              <div>
                <label htmlFor="fp-email" className="mb-1.5 block text-sm font-medium text-fg-2 sm:mb-2">
                  E-mail
                </label>
                <input
                  id="fp-email"
                  type="email"
                  autoComplete="email"
                  inputMode="email"
                  autoCapitalize="none"
                  spellCheck={false}
                  {...form.register("email")}
                  aria-invalid={Boolean(form.formState.errors.email)}
                  className="h-10 w-full sm:h-11 rounded-lg border border-line bg-surface-inset px-3.5 text-sm text-fg outline-none transition placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
                  placeholder="voce@empresa.com"
                />
                {form.formState.errors.email && (
                  <p className="mt-1.5 text-xs text-danger">{form.formState.errors.email.message}</p>
                )}
              </div>

              {apiError && (
                <div className="rounded-lg border border-danger/30 bg-danger-soft px-3.5 py-3 text-sm text-danger" role="alert">
                  {apiError}
                </div>
              )}

              <button
                type="submit"
                disabled={mutation.isPending}
                className="flex h-10 w-full items-center sm:h-11 justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand focus:outline-none focus:ring-2 focus:ring-brand focus:ring-offset-2 focus:ring-offset-[#0d1015] disabled:cursor-wait disabled:opacity-70"
              >
                {mutation.isPending && <LoaderCircle size={16} className="animate-spin" />}
                {mutation.isPending ? "Enviando..." : "Enviar link"}
              </button>
            </form>
          )}

          <p className="mt-4 border-t border-line-soft pt-4 sm:mt-6 sm:pt-5 text-sm text-muted">
            Lembrou a senha?{" "}
            <Link to="/login" className="font-medium text-accent hover:text-white">
              Entrar
            </Link>
          </p>
        </div>
      </section>
    </AuthShell>
  );
}
