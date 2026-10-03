import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ErrorState, LoadingState } from "@/components/PageState";
import { useAuth } from "@/features/auth/AuthProvider";
import { ApiError, apiRequest, type User, type Workspace } from "@/services/api";
import { isValidPublicNickname, normalizePublicNickname } from "@/features/auth/nickname";

const profileSchema = z.object({
  full_name: z.string().trim().min(1, "Informe seu nome.").max(160),
  nickname: z
    .string()
    .refine(isValidPublicNickname, "Use um apelido entre 2 e 40 caracteres."),
});
type ProfileValues = z.infer<typeof profileSchema>;

export function ProfilePage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [avatarError, setAvatarError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const profile = useQuery({
    queryKey: ["profile"],
    queryFn: () => apiRequest<User>("/api/profile"),
  });
  const workspace = useQuery({
    queryKey: ["workspace"],
    queryFn: () => apiRequest<Workspace>("/api/workspace"),
    enabled: user?.role !== "SUPER_ADMIN",
    retry: false,
  });
  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: { full_name: "", nickname: "" },
  });
  const nicknameInput = form.register("nickname");
  useEffect(() => {
    if (profile.data) {
      form.reset({
        full_name: profile.data.full_name,
        nickname: profile.data.nickname,
      });
    }
  }, [profile.data, form]);

  const update = useMutation({
    mutationFn: (values: ProfileValues) =>
      apiRequest<User>("/api/profile", {
        method: "PATCH",
        body: {
          full_name: values.full_name,
          nickname: normalizePublicNickname(values.nickname),
        },
      }),
    onSuccess: (updatedUser) => {
      queryClient.setQueryData(["profile"], updatedUser);
      queryClient.setQueryData(["auth", "me"], updatedUser);
    },
  });
  const uploadAvatar = useMutation({
    mutationFn: (file: File) =>
      apiRequest<User>("/api/profile/avatar", {
        method: "POST",
        headers: { "Content-Type": file.type },
        body: file,
      }),
    onSuccess: (updatedUser) => {
      queryClient.setQueryData(["profile"], updatedUser);
      queryClient.setQueryData(["auth", "me"], updatedUser);
      setAvatarFile(null);
      setAvatarPreview(null);
      setAvatarError(null);
    },
  });
  useEffect(() => {
    if (!avatarFile) {
      setAvatarPreview(null);
      return;
    }
    const preview = URL.createObjectURL(avatarFile);
    setAvatarPreview(preview);
    return () => URL.revokeObjectURL(preview);
  }, [avatarFile]);
  const saveProfile = async (values: ProfileValues) => {
    setAvatarError(null);
    setSubmitError(null);
    try {
      await update.mutateAsync(values);
      if (avatarFile) {
        await uploadAvatar.mutateAsync(avatarFile);
      }
    } catch (error) {
      setSubmitError(
        error instanceof ApiError
          ? error.message
          : "Não foi possível salvar as alterações do perfil.",
      );
    }
  };

  if (
    profile.isLoading ||
    (user?.role !== "SUPER_ADMIN" && workspace.isLoading)
  ) {
    return <LoadingState label="Carregando perfil" />;
  }
  if (profile.error || !profile.data) {
    return <ErrorState message="Não foi possível carregar seu perfil." />;
  }
  if (user?.role !== "SUPER_ADMIN" && (workspace.error || !workspace.data)) {
    return <ErrorState message="Não foi possível carregar o workspace do perfil." />;
  }

  const apiError =
    submitError ??
    (update.error instanceof ApiError
      ? update.error.message
      : update.error
        ? "Não foi possível atualizar o perfil."
        : uploadAvatar.error instanceof ApiError
          ? uploadAvatar.error.message
          : uploadAvatar.error
            ? "Não foi possível enviar a imagem de perfil."
            : null);
  const workspaceName =
    user?.role === "SUPER_ADMIN"
      ? "Acesso global"
      : workspace.data?.name ?? "—";

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <div>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
          Conta
        </p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
          Perfil
        </h2>
        <p className="mt-2 text-sm text-[#94a3b8]">
          Consulte seus dados e atualize seu nome, apelido e imagem de perfil.
        </p>
      </div>

      <section className="rounded-xl border border-[#202838] bg-[#0d1015] p-5 sm:p-7">
        <div className="mb-7 flex items-center gap-4 border-b border-[#202838] pb-6">
          {avatarPreview || profile.data.avatar_url ? (
            <img
              src={avatarPreview ?? profile.data.avatar_url ?? undefined}
              alt=""
              className="size-14 rounded-full border border-[#27334a] object-cover"
            />
          ) : (
            <span className="grid size-14 place-items-center rounded-full bg-[#171e31] text-lg font-semibold text-[#aab7ff]">
              {profile.data.full_name.slice(0, 1).toUpperCase()}
            </span>
          )}
          <div className="min-w-0">
            <p className="truncate font-medium text-[#f5f7fb]">
              {profile.data.full_name}
            </p>
            <p className="mt-1 truncate text-sm text-[#64748b]">
              {profile.data.email}
            </p>
            <p className="mt-1 truncate text-xs text-[#8295ff]">
              {profile.data.nickname}
            </p>
          </div>
        </div>

        <form
          className="space-y-5"
          onSubmit={form.handleSubmit((values) => void saveProfile(values))}
          noValidate
        >
          <div>
            <label htmlFor="profile-name" className="mb-2 block text-sm font-medium text-[#c7cfdd]">
              Nome
            </label>
            <input
              id="profile-name"
              autoComplete="name"
              {...form.register("full_name")}
              aria-invalid={Boolean(form.formState.errors.full_name)}
              className="h-11 w-full rounded-lg border border-[#27334a] bg-[#090b0e] px-3.5 text-sm text-[#f5f7fb] outline-none focus:border-[#536dfe] focus:ring-2 focus:ring-[#536dfe]/20"
            />
            {form.formState.errors.full_name && (
              <p className="mt-1.5 text-xs text-[#f1a3ad]">
                {form.formState.errors.full_name.message}
              </p>
            )}
          </div>
          <div>
            <label htmlFor="profile-email" className="mb-2 block text-sm font-medium text-[#c7cfdd]">
              E-mail
            </label>
            <input
              id="profile-email"
              value={profile.data.email}
              readOnly
              className="h-11 w-full cursor-not-allowed rounded-lg border border-[#202838] bg-[#0a0d11] px-3.5 text-sm text-[#64748b]"
            />
          </div>
          <div>
            <label htmlFor="profile-nickname" className="mb-2 block text-sm font-medium text-[#c7cfdd]">
              Apelido
            </label>
            <input
              id="profile-nickname"
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
              aria-invalid={Boolean(form.formState.errors.nickname)}
              className="h-11 w-full rounded-lg border border-[#27334a] bg-[#090b0e] px-3.5 text-sm text-[#f5f7fb] outline-none focus:border-[#536dfe] focus:ring-2 focus:ring-[#536dfe]/20"
            />
            <p className="mt-1.5 text-xs text-[#64748b]">
              Este será o nome público exibido no ranking e na plataforma.
            </p>
            {form.formState.errors.nickname && (
              <p className="mt-1.5 text-xs text-[#f1a3ad]">
                {form.formState.errors.nickname.message}
              </p>
            )}
          </div>
          <div>
            <label htmlFor="profile-avatar" className="mb-2 block text-sm font-medium text-[#c7cfdd]">
              Foto de perfil <span className="font-normal text-[#64748b]">(JPEG, PNG ou WebP; até 5 MB)</span>
            </label>
            <input
              id="profile-avatar"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => {
                const file = event.currentTarget.files?.[0] ?? null;
                event.currentTarget.value = "";
                if (!file) return;
                if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
                  setAvatarFile(null);
                  setAvatarError("Selecione uma imagem JPEG, PNG ou WebP.");
                  return;
                }
                if (file.size > 5 * 1024 * 1024) {
                  setAvatarFile(null);
                  setAvatarError("A imagem deve ter até 5 MB.");
                  return;
                }
                setAvatarError(null);
                setAvatarFile(file);
              }}
              className="block min-h-11 w-full rounded-lg border border-[#27334a] bg-[#090b0e] text-sm text-[#c7cfdd] file:mr-3 file:min-h-11 file:border-0 file:bg-[#171e31] file:px-4 file:font-medium file:text-[#aab7ff]"
            />
            {avatarError && (
              <p className="mt-1.5 text-xs text-[#f1a3ad]">
                {avatarError}
              </p>
            )}
            {avatarFile && !avatarError && (
              <p className="mt-1.5 text-xs text-[#94a3b8]">{avatarFile.name} selecionada.</p>
            )}
          </div>
          <div className="grid gap-3 border-t border-[#202838] pt-5 sm:grid-cols-2">
            <Info label="Permissão" value={profile.data.role} />
            <Info
              label="Workspace"
              value={workspaceName}
            />
            <Info
              label="Criado em"
              value={new Date(profile.data.created_at).toLocaleDateString("pt-BR", {
                timeZone: "America/Sao_Paulo",
              })}
            />
          </div>
          {apiError && (
            <p role="alert" className="text-sm text-[#f1a3ad]">
              {apiError}
            </p>
          )}
          {update.isSuccess && (
            <p role="status" className="text-sm text-[#2dd4a0]">
              Perfil atualizado.
            </p>
          )}
          <button
            type="submit"
            disabled={update.isPending}
            className="min-h-11 rounded-lg bg-[#536dfe] px-5 text-sm font-semibold text-white transition hover:bg-[#667eea] disabled:opacity-60"
          >
            {update.isPending || uploadAvatar.isPending ? "Salvando..." : "Salvar alterações"}
          </button>
        </form>
      </section>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.12em] text-[#64748b]">{label}</p>
      <p className="mt-1.5 text-sm text-[#c7cfdd]">{value}</p>
    </div>
  );
}
