import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { LoaderCircle } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { apiRequest } from "@/services/api";

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  const ran = useRef(false);

  const mutation = useMutation({
    mutationFn: () =>
      apiRequest<{ message: string }>("/api/auth/verify-email", {
        method: "POST",
        body: { token },
      }),
    onSuccess: () => setStatus("success"),
    onError: () => setStatus("error"),
  });

  useEffect(() => {
    if (!token || ran.current) return;
    ran.current = true;
    mutation.mutate();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <main className="grid min-h-screen place-items-center bg-transparent p-4">
      <div className="w-full max-w-sm rounded-xl border border-line bg-surface p-8 text-center">
        {status === "pending" && (
          <div className="flex flex-col items-center gap-4">
            <LoaderCircle size={32} className="animate-spin text-brand" />
            <p className="text-sm text-muted">Verificando seu e-mail...</p>
          </div>
        )}
        {status === "success" && (
          <div className="flex flex-col items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-soft text-brand text-2xl">✓</div>
            <div>
              <p className="font-semibold text-fg">E-mail confirmado!</p>
              <p className="mt-1 text-sm text-muted">Sua conta está ativa. Agora é só entrar.</p>
            </div>
            <Link
              to="/login"
              className="mt-2 flex h-10 w-full items-center justify-center rounded-lg bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand"
            >
              Entrar
            </Link>
          </div>
        )}
        {status === "error" && (
          <div className="flex flex-col items-center gap-4">
            <p className="font-semibold text-fg">Link inválido ou expirado</p>
            <p className="text-sm text-muted">
              O link de verificação expirou ou já foi utilizado. Faça login e solicite um novo.
            </p>
            <Link
              to="/login"
              className="mt-2 flex h-10 w-full items-center justify-center rounded-lg bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand"
            >
              Ir para o login
            </Link>
          </div>
        )}
      </div>
    </main>
  );
}
