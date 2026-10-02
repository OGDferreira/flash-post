import { useEffect, useState } from "react";
import type { InputHTMLAttributes } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, LoaderCircle, ShieldCheck } from "lucide-react";
import { useForm, type UseFormRegisterReturn } from "react-hook-form";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { z } from "zod";

import { useAuth } from "@/features/auth/AuthProvider";
import { ApiError, apiRequest, type User } from "@/services/api";
import { isValidPublicNickname, normalizePublicNickname } from "@/features/auth/nickname";

const registerSchema = z
  .object({
    full_name: z.string().trim().min(1, "Informe seu nome completo.").max(160),
    email: z.string().trim().email("Informe um e-mail válido."),
    nickname: z
      .string()
      .refine(isValidPublicNickname, "Use um apelido entre 2 e 40 caracteres."),
    password: z.string().min(8, "Use pelo menos 8 caracteres.").max(256),
    confirm_password: z.string().min(1, "Confirme sua senha."),
  })
  .refine((values) => values.password === values.confirm_password, {
    message: "As senhas não coincidem.",
    path: ["confirm_password"],
  });

type RegisterValues = z.infer<typeof registerSchema>;
type RegisterResponse = { user: User; csrf_token: string };

export function RegisterPage() {
  const { user, isLoading } = useAuth();
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [confirmVisible, setConfirmVisible] = useState(false);
  const [debouncedNickname, setDebouncedNickname] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    mode: "onChange",
    defaultValues: {
      full_name: "",
      email: "",
      nickname: "",
      password: "",
      confirm_password: "",
    },
  });
  const nicknameInput = form.register("nickname");
  const nickname = form.watch("nickname");
  const normalizedNickname = normalizePublicNickname(nickname);
  const nicknameIsValid = isValidPublicNickname(nickname);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedNickname(nicknameIsValid ? normalizedNickname : "");
    }, 350);
    return () => window.clearTimeout(timer);
  }, [nickname, nicknameIsValid]);

  const availability = useQuery({
    queryKey: ["nickname-availability", debouncedNickname.toLowerCase()],
    queryFn: () =>
      apiRequest<{ available: boolean }>(
        `/api/auth/nickname-availability?nickname=${encodeURIComponent(debouncedNickname)}`,
      ),
    enabled: Boolean(debouncedNickname),
    retry: false,
    staleTime: 10_000,
  });
  const mutation = useMutation({
    mutationFn: (values: RegisterValues) =>
      apiRequest<RegisterResponse>("/api/auth/register", {
        method: "POST",
        body: {
          ...values,
          nickname: normalizePublicNickname(values.nickname),
        },
      }),
    onSuccess: ({ user: signedInUser }) => {
      queryClient.setQueryData(["auth", "me"], signedInUser);
      navigate("/dashboard", { replace: true });
    },
  });

  if (isLoading) return <RegisterLoading />;
  if (user) return <Navigate to="/dashboard" replace />;

  const apiError =
    mutation.error instanceof ApiError ? mutation.error.message : null;
  const availabilityMatchesInput =
    debouncedNickname.toLowerCase() === normalizedNickname.toLowerCase();
  const availabilityMessage = !availabilityMatchesInput
    ? null
    : availability.isFetching
      ? "Verificando disponibilidade..."
      : availability.data?.available === false
        ? "Este apelido já está em uso."
        : availability.data?.available
          ? "Apelido disponível."
          : availability.error
            ? "Não foi possível verificar agora; confirmaremos ao criar a conta."
            : null;
  const nicknameMessage =
    form.formState.errors.nickname?.message ?? availabilityMessage;

  return (
    <main className="relative grid min-h-svh place-items-center overflow-x-hidden bg-[#070809] px-4 py-6 sm:px-6 sm:py-10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_20%_48%,rgba(83,109,254,0.08),transparent_45%)]" />
      <div className="relative grid w-full max-w-[960px] overflow-hidden rounded-2xl border border-[#202838] bg-[#0d1015] shadow-[0_24px_80px_rgba(0,0,0,0.28)] md:grid-cols-[0.95fr_1.05fr]">
        <section className="flex flex-col justify-between gap-10 p-6 sm:p-8 md:min-h-[540px] md:p-9">
          <Link to="/" className="flex w-fit items-center gap-3">
            <img
              src="/flashpost-logo.png"
              alt="FlashPost"
              width="40"
              height="40"
              className="size-10 shrink-0 object-contain"
            />
            <span className="text-base font-semibold tracking-[-0.03em] text-[#f5f7fb]">
              flashpost<span className="text-[#7186ff]">.</span>
            </span>
          </Link>
          <div className="max-w-sm md:my-auto">
            <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-[#27334a] bg-[#0d1015] px-3 py-1.5 text-xs text-[#aeb9ce]">
              <ShieldCheck size={14} className="text-[#8295ff]" />
              Crie seu acesso seguro
            </p>
            <h1 className="text-4xl font-semibold leading-tight tracking-[-0.06em] text-[#f5f7fb] sm:text-5xl">
              Sua operação,
              <br />
              <span className="text-[#7186ff]">em um só lugar.</span>
            </h1>
            <p className="mt-5 max-w-md text-base leading-7 text-[#94a3b8]">
              Crie sua conta e comece a organizar seu espaço de trabalho no FlashPost.
            </p>
          </div>
          <p className="hidden text-xs text-[#64748b] md:block">
            FlashPost · Acesso protegido
          </p>
        </section>

        <section className="flex items-center border-t border-[#202838] p-6 sm:p-8 md:border-l md:border-t-0 md:p-9">
          <div className="w-full max-w-md md:mx-auto">
          <div className="mb-7">
            <h2 className="text-xl font-semibold tracking-[-0.035em] text-[#f5f7fb]">
              Criar conta
            </h2>
            <p className="mt-2 text-sm text-[#94a3b8]">
              Cadastre-se para criar seu workspace de proprietário.
            </p>
          </div>
          <form
            className="space-y-4"
            onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
            noValidate
          >
            <Field
              id="register-name"
              label="Nome completo"
              error={form.formState.errors.full_name?.message}
              inputProps={{
                autoComplete: "name",
                ...form.register("full_name"),
              }}
            />
            <Field
              id="register-email"
              label="E-mail"
              error={form.formState.errors.email?.message}
              inputProps={{
                type: "email",
                autoComplete: "email",
                inputMode: "email",
                autoCapitalize: "none",
                spellCheck: false,
                ...form.register("email"),
              }}
            />
            <div>
              <label htmlFor="register-nickname" className="mb-2 block text-sm font-medium text-[#c7cfdd]">
                Apelido
              </label>
              <input
                id="register-nickname"
                autoComplete="nickname"
                spellCheck={false}
                {...nicknameInput}
                onBlur={(event) => {
                  void nicknameInput.onBlur(event);
                  form.setValue("nickname", normalizePublicNickname(event.target.value), {
                    shouldValidate: true,
                    shouldDirty: true,
                  });
                }}
                aria-invalid={
                  Boolean(form.formState.errors.nickname) ||
                  (availabilityMatchesInput &&
                    availability.data?.available === false)
                }
                aria-describedby="register-nickname-hint register-nickname-status"
                className="h-11 w-full rounded-lg border border-[#27334a] bg-[#090b0e] px-3.5 text-sm text-[#f5f7fb] outline-none transition placeholder:text-[#536176] focus:border-[#536dfe] focus:ring-2 focus:ring-[#536dfe]/20"
                placeholder="Ex.: Gui Ferreira"
              />
              <p id="register-nickname-hint" className="mt-1.5 text-xs text-[#64748b]">
                Este será o nome público exibido no ranking e na plataforma. Use o nome pelo qual você quer ser conhecido.
              </p>
              <p
                id="register-nickname-status"
                role={availability.data?.available === false || form.formState.errors.nickname ? "alert" : "status"}
                className={`mt-1 text-xs ${availability.data?.available ? "text-[#2dd4a0]" : "text-[#f1a3ad]"}`}
              >
                {nicknameMessage}
              </p>
            </div>
            <PasswordField
              id="register-password"
              label="Senha"
              visible={passwordVisible}
              onToggle={() => setPasswordVisible((visible) => !visible)}
              error={form.formState.errors.password?.message}
              autoComplete="new-password"
              register={form.register("password")}
            />
            <PasswordField
              id="register-confirm-password"
              label="Confirmar senha"
              visible={confirmVisible}
              onToggle={() => setConfirmVisible((visible) => !visible)}
              error={form.formState.errors.confirm_password?.message}
              autoComplete="new-password"
              register={form.register("confirm_password")}
            />

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
              disabled={mutation.isPending || availability.data?.available === false}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#536dfe] px-4 text-sm font-semibold text-white transition hover:bg-[#667eea] focus:outline-none focus:ring-2 focus:ring-[#8da0ff] focus:ring-offset-2 focus:ring-offset-[#0d1015] disabled:cursor-wait disabled:opacity-70"
            >
              {mutation.isPending && <LoaderCircle size={16} className="animate-spin" />}
              {mutation.isPending ? "Criando conta..." : "Criar conta"}
            </button>
          </form>
          <p className="mt-6 border-t border-[#202838] pt-5 text-sm text-[#64748b]">
            Já tem uma conta?{" "}
            <Link to="/login" className="font-medium text-[#aab7ff] hover:text-white">
              Entrar
            </Link>
          </p>
          </div>
        </section>
      </div>
    </main>
  );
}

function Field({
  id,
  label,
  error,
  inputProps,
}: {
  id: string;
  label: string;
  error?: string;
  inputProps: InputHTMLAttributes<HTMLInputElement>;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-sm font-medium text-[#c7cfdd]">
        {label}
      </label>
      <input
        id={id}
        {...inputProps}
        aria-invalid={Boolean(error)}
        className="h-11 w-full rounded-lg border border-[#27334a] bg-[#090b0e] px-3.5 text-sm text-[#f5f7fb] outline-none transition placeholder:text-[#536176] focus:border-[#536dfe] focus:ring-2 focus:ring-[#536dfe]/20"
      />
      {error && <p className="mt-1.5 text-xs text-[#f1a3ad]">{error}</p>}
    </div>
  );
}

function PasswordField({
  id,
  label,
  visible,
  onToggle,
  error,
  autoComplete,
  register,
}: {
  id: string;
  label: string;
  visible: boolean;
  onToggle: () => void;
  error?: string;
  autoComplete: string;
  register: UseFormRegisterReturn;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-sm font-medium text-[#c7cfdd]">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          {...register}
          aria-invalid={Boolean(error)}
          className="h-11 w-full rounded-lg border border-[#27334a] bg-[#090b0e] px-3.5 pr-12 text-sm text-[#f5f7fb] outline-none transition placeholder:text-[#536176] focus:border-[#536dfe] focus:ring-2 focus:ring-[#536dfe]/20"
        />
        <button
          type="button"
          onClick={onToggle}
          aria-label={visible ? "Ocultar senha" : "Mostrar senha"}
          className="absolute inset-y-0 right-0 grid w-11 place-items-center text-[#64748b] hover:text-[#c7cfdd]"
        >
          {visible ? <EyeOff size={17} /> : <Eye size={17} />}
        </button>
      </div>
      {error && <p className="mt-1.5 text-xs text-[#f1a3ad]">{error}</p>}
    </div>
  );
}

function RegisterLoading() {
  return (
    <main className="grid min-h-screen place-items-center bg-[#070809] text-sm text-[#94a3b8]">
      Verificando sessão segura...
    </main>
  );
}
