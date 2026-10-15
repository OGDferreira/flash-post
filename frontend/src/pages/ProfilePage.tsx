import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AffiliateLinkCard } from "@/features/affiliates/AffiliateLinkCard";
import { DailyViewsGoalCard } from "@/components/DailyViewsGoalCard";
import { ErrorState, LoadingState } from "@/components/PageState";
import { useAuth } from "@/features/auth/AuthProvider";
import { resizeAvatar } from "@/lib/image";
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
  const hasWorkspaceAccess =
    user?.role !== "SUPER_ADMIN" || user.workspace_role !== null;
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
    enabled: hasWorkspaceAccess,
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
    (hasWorkspaceAccess && workspace.isLoading)
  ) {
    return <LoadingState label="Carregando perfil" />;
  }
  if (profile.error || !profile.data) {
    return <ErrorState message="Não foi possível carregar seu perfil." />;
  }
  if (hasWorkspaceAccess && (workspace.error || !workspace.data)) {
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
    !hasWorkspaceAccess
      ? "Acesso global"
      : workspace.data?.name ?? "—";

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">
          Conta
        </p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
          Perfil
        </h2>
        <p className="mt-2 text-sm text-muted">
          Consulte seus dados e atualize seu nome, apelido e imagem de perfil.
        </p>
      </div>

      <section className="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
        <div className="mb-7 flex items-center gap-4 border-b border-line-soft pb-6">
          {avatarPreview || profile.data.avatar_url ? (
            <img
              src={avatarPreview ?? profile.data.avatar_url ?? undefined}
              alt=""
              className="size-14 rounded-full border border-line object-cover"
            />
          ) : (
            <span className="grid size-14 place-items-center rounded-full bg-brand-soft text-lg font-semibold text-accent">
              {profile.data.full_name.slice(0, 1).toUpperCase()}
            </span>
          )}
          <div className="min-w-0">
            <p className="truncate font-medium text-fg">
              {profile.data.full_name}
            </p>
            <p className="mt-1 truncate text-sm text-muted">
              {profile.data.email}
            </p>
            <p className="mt-1 truncate text-xs text-accent">
              {profile.data.nickname}
            </p>
          </div>
        </div>

        <form
          className="space-y-4"
          onSubmit={form.handleSubmit((values) => void saveProfile(values))}
          noValidate
        >
          <div>
            <label htmlFor="profile-name" className="mb-2 block text-sm font-medium text-fg-2">
              Nome
            </label>
            <input
              id="profile-name"
              autoComplete="name"
              {...form.register("full_name")}
              aria-invalid={Boolean(form.formState.errors.full_name)}
              className="h-11 w-full rounded-lg border border-line bg-surface-inset px-3.5 text-sm text-fg outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
            {form.formState.errors.full_name && (
              <p className="mt-1.5 text-xs text-danger">
                {form.formState.errors.full_name.message}
              </p>
            )}
          </div>
          <div>
            <label htmlFor="profile-email" className="mb-2 block text-sm font-medium text-fg-2">
              E-mail
            </label>
            <input
              id="profile-email"
              value={profile.data.email}
              readOnly
              className="h-11 w-full cursor-not-allowed rounded-lg border border-line-soft bg-well px-3.5 text-sm text-muted"
            />
          </div>
          <div>
            <label htmlFor="profile-nickname" className="mb-2 block text-sm font-medium text-fg-2">
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
              className="h-11 w-full rounded-lg border border-line bg-surface-inset px-3.5 text-sm text-fg outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
            />
            <p className="mt-1.5 text-xs text-muted">
              Este será o nome público exibido no ranking e na plataforma.
            </p>
            {form.formState.errors.nickname && (
              <p className="mt-1.5 text-xs text-danger">
                {form.formState.errors.nickname.message}
              </p>
            )}
          </div>
          <div>
            <label htmlFor="profile-avatar" className="mb-2 block text-sm font-medium text-fg-2">
              Foto de perfil <span className="font-normal text-muted">(JPEG, PNG ou WebP; enviada ao selecionar)</span>
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
                void resizeAvatar(file).then((small) => {
                  setAvatarFile(small);
                  uploadAvatar.mutate(small);
                });
              }}
              className="block min-h-11 w-full rounded-lg border border-line bg-surface-inset text-sm text-fg-2 file:mr-3 file:min-h-11 file:border-0 file:bg-brand-soft file:px-4 file:font-medium file:text-accent"
            />
            {avatarError && (
              <p className="mt-1.5 text-xs text-danger">
                {avatarError}
              </p>
            )}
            {avatarFile && !avatarError && (
              <p className="mt-1.5 text-xs text-muted">Enviando…</p>
            )}
          </div>
          <div className="grid gap-3 border-t border-line-soft pt-5 sm:grid-cols-2">
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
            <p role="alert" className="text-sm text-danger">
              {apiError}
            </p>
          )}
          {update.isSuccess && (
            <p role="status" className="text-sm text-success">
              Perfil atualizado.
            </p>
          )}
          <button
            type="submit"
            disabled={update.isPending}
            className="min-h-11 rounded-lg bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand disabled:opacity-60"
          >
            {update.isPending || uploadAvatar.isPending ? "Salvando..." : "Salvar alterações"}
          </button>
        </form>
      </section>
      <AffiliateLinkCard />
      <DailyViewsGoalCard />
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.12em] text-muted">{label}</p>
      <p className="mt-1.5 text-sm text-fg-2">{value}</p>
    </div>
  );
}
