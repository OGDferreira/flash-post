import { homePath } from "@/features/auth/homePanel";
import { useEffect, useState } from "react";
import type { InputHTMLAttributes } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, LoaderCircle } from "lucide-react";
import { useForm, type UseFormRegisterReturn } from "react-hook-form";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { useAuth } from "@/features/auth/AuthProvider";
import { AuthShell } from "@/features/auth/AuthShell";
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
    invite_code: z.string().trim().max(40).optional(),
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
  const [searchParams] = useSearchParams();
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
      // /register?invite=CODE (shared by a chief) prefills the field.
      invite_code: (searchParams.get("invite") ?? "").slice(0, 40),
    },
  });
  // A link with ?terms= carries the commission the chief offers (signed by the server).
  const inviteTerms = (searchParams.get("terms") ?? "").slice(0, 300);
  const inviteCode = form.watch("invite_code")?.trim() ?? "";
  const linkCode = (searchParams.get("invite") ?? "").trim();
  const preview = useQuery({
    queryKey: ["invite-preview", linkCode, inviteTerms],
    queryFn: () =>
      apiRequest<{ chief_name: string; percent: string | null }>(
        `/api/affiliates/invite/preview?${new URLSearchParams({ code: linkCode, terms: inviteTerms })}`,
      ),
    enabled: Boolean(linkCode && inviteTerms),
    retry: false,
    staleTime: 60_000,
  });
  const offer = preview.data?.percent && inviteCode.toUpperCase() === linkCode.toUpperCase() ? preview.data : null;
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
          invite_code: values.invite_code?.trim() || undefined,
          invite_terms: offer ? inviteTerms : undefined,
          nickname: normalizePublicNickname(values.nickname),
        },
      }),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ["auth", "me"] });
      navigate("/login", { replace: true, state: { registrationPending: true } });
    },
  });

  if (isLoading) return <RegisterLoading />;
  if (user) return <Navigate to={homePath(user)} replace />;

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
    <AuthShell mode="register">
        <section className="flex items-center border-t border-line-soft p-4 sm:p-8 md:border-l md:border-t-0 md:p-10">
          <div className="w-full max-w-md md:mx-auto">
          <div className="mb-4 sm:mb-7">
            <h2 className="text-xl font-semibold tracking-[-0.035em] text-fg">
              Criar conta
            </h2>
            <p className="mt-2 text-sm text-muted">
              Cadastre-se para criar seu workspace de proprietário.
            </p>
          </div>
          <form
            className="space-y-3 sm:space-y-4"
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
              <label htmlFor="register-nickname" className="mb-1.5 block text-sm font-medium text-fg-2 sm:mb-2">
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
                className="h-10 w-full sm:h-11 rounded-lg border border-line bg-surface-inset px-3.5 text-sm text-fg outline-none transition placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
                placeholder="Ex.: Gui Ferreira"
              />
              <p id="register-nickname-hint" className="mt-1.5 text-xs text-muted">
                Este será o nome público exibido no ranking e na plataforma. Use o nome pelo qual você quer ser conhecido.
              </p>
              <p
                id="register-nickname-status"
                role={availability.data?.available === false || form.formState.errors.nickname ? "alert" : "status"}
                className={`mt-1 text-xs ${availability.data?.available ? "text-success" : "text-danger"}`}
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

            <div>
              <label htmlFor="register-invite" className="mb-1.5 block text-sm font-medium text-fg-2 sm:mb-2">
                Código de convite <span className="font-normal text-muted">(opcional)</span>
              </label>
              <input
                id="register-invite"
                autoComplete="off"
                autoCapitalize="characters"
                className="field uppercase tracking-widest"
                maxLength={40}
                placeholder="Se alguém convidou você"
                {...form.register("invite_code")}
              />
              <p className="mt-1.5 text-xs text-muted">
                Ao usar o código você passa a ser filiado de quem convidou. Essa pessoa vê as métricas da sua operação,
                mas não tem acesso às suas contas nem à sua senha.
              </p>
              {offer && (
                <div className="mt-2 rounded-xl border border-brand/40 bg-brand-soft p-3 text-xs text-fg-2">
                  <strong className="text-fg">Comissão de {Number(offer.percent).toLocaleString("pt-BR")}% para {offer.chief_name}.</strong>{" "}
                  Nas vendas feitas com os funis compartilhados por {offer.chief_name}, essa porcentagem é separada automaticamente
                  pelo gateway. O sócio que convidou define a comissão, que pode ser atualizada para vendas futuras sem aceite adicional.
                </div>
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
              disabled={mutation.isPending || availability.data?.available === false}
              className="flex h-10 w-full items-center sm:h-11 justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand focus:outline-none focus:ring-2 focus:ring-brand focus:ring-offset-2 focus:ring-offset-[#0d1015] disabled:cursor-wait disabled:opacity-70"
            >
              {mutation.isPending && <LoaderCircle size={16} className="animate-spin" />}
              {mutation.isPending ? "Criando conta..." : "Criar conta"}
            </button>
          </form>
          <p className="mt-4 border-t border-line-soft pt-4 sm:mt-6 sm:pt-5 text-sm text-muted">
            Já tem uma conta?{" "}
            <Link to="/login" className="font-medium text-accent hover:text-white">
              Entrar
            </Link>
          </p>
          </div>
        </section>
    </AuthShell>
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
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-fg-2 sm:mb-2">
        {label}
      </label>
      <input
        id={id}
        {...inputProps}
        aria-invalid={Boolean(error)}
        className="h-10 w-full sm:h-11 rounded-lg border border-line bg-surface-inset px-3.5 text-sm text-fg outline-none transition placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
      />
      {error && <p className="mt-1.5 text-xs text-danger">{error}</p>}
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
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-fg-2 sm:mb-2">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          {...register}
          aria-invalid={Boolean(error)}
          className="h-10 w-full sm:h-11 rounded-lg border border-line bg-surface-inset px-3.5 pr-12 text-sm text-fg outline-none transition placeholder:text-muted focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
        <button
          type="button"
          onClick={onToggle}
          aria-label={visible ? "Ocultar senha" : "Mostrar senha"}
          className="absolute inset-y-0 right-0 grid w-11 place-items-center text-muted hover:text-fg-2"
        >
          {visible ? <EyeOff size={17} /> : <Eye size={17} />}
        </button>
      </div>
      {error && <p className="mt-1.5 text-xs text-danger">{error}</p>}
    </div>
  );
}

function RegisterLoading() {
  return (
    <main className="grid min-h-screen place-items-center bg-transparent text-sm text-muted">
      Verificando sessão segura...
    </main>
  );
}
