import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Image as ImageIcon,
  MessageCircle,
  RefreshCw,
  Star,
  UsersRound,
} from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { InstagramAvatar } from "@/components/InstagramAvatar";
import { ApiError, apiRequest } from "@/services/api";

type InstagramAccount = {
  id: string;
  username: string;
  profile_picture_url: string | null;
  follower_count: number | null;
  media_count: number | null;
  token_expires_at: string;
  status: "connected" | "disconnected" | "error";
  has_highlights: boolean;
};

type InstagramAccountsResponse = {
  accounts: InstagramAccount[];
};

type InstagramFeedMedia = {
  id: string;
  media_type: string;
  media_url: string | null;
  thumbnail_url: string | null;
  permalink: string | null;
  timestamp: string | null;
  caption: string | null;
  like_count: number | null;
  comments_count: number | null;
};

type InstagramAccountFeedResponse = {
  account_id: string;
  username: string;
  followers_count: number | null;
  media_count: number | null;
  follows_count: number | null;
  media: InstagramFeedMedia[];
};

function formatCount(value: number | null | undefined): string {
  return value == null ? "—" : new Intl.NumberFormat("pt-BR").format(value);
}

function formatTimestamp(value: string | null): string {
  if (!value) return "Data indisponível";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data indisponível";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  }).format(date);
}

function displayError(error: unknown, fallback: string): string | null {
  if (!error) return null;
  return error instanceof ApiError ? error.message : fallback;
}

function FeedMetric({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: typeof UsersRound;
}) {
  return (
    <div className="rounded-lg border border-[#202838] bg-[#0d151c] p-3">
      <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
        <Icon className="text-[#8295ff]" size={14} />
        {label}
      </div>
      <p className="mt-2 text-lg font-semibold text-[#f5f7fb]">{value}</p>
    </div>
  );
}

export function FeedPage() {
  const queryClient = useQueryClient();
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<InstagramAccountsResponse>("/api/instagram/accounts"),
    refetchInterval: 60_000,
    retry: false,
  });
  const selectedAccount =
    accounts.data?.accounts.find((account) => account.id === selectedAccountId) ??
    accounts.data?.accounts[0] ??
    null;
  const feed = useQuery({
    queryKey: ["instagram", "feed", selectedAccount?.id],
    queryFn: () =>
      apiRequest<InstagramAccountFeedResponse>(
        `/api/instagram/accounts/${selectedAccount?.id}/feed`,
      ),
    enabled: Boolean(selectedAccount),
    refetchInterval: 5 * 60_000,
    retry: false,
  });
  const updateHighlights = useMutation({
    mutationFn: (has_highlights: boolean) =>
      apiRequest(`/api/instagram/accounts/${selectedAccount?.id}/highlights`, {
        method: "PATCH",
        body: { has_highlights },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["instagram", "accounts"] }),
  });

  useEffect(() => {
    if (
      selectedAccountId &&
      accounts.data &&
      !accounts.data.accounts.some((account) => account.id === selectedAccountId)
    ) {
      setSelectedAccountId(accounts.data.accounts[0]?.id ?? null);
    }
  }, [accounts.data, selectedAccountId]);

  if (accounts.isLoading) return <LoadingState label="Carregando contas do Feed" />;
  if (accounts.error || !accounts.data) {
    return <ErrorState message="Não foi possível carregar as contas deste workspace." />;
  }
  if (accounts.data.accounts.length === 0) {
    return (
      <div className="mx-auto max-w-[1280px] space-y-6">
        <FeedHeading />
        <EmptyState message="Conecte uma conta Instagram para visualizar o Feed." />
      </div>
    );
  }

  const updateError = displayError(
    updateHighlights.error,
    "Não foi possível guardar a opção de destaques.",
  );

  return (
    <div className="mx-auto max-w-[1440px] space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <FeedHeading />
        <button
          className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-[#27334a] bg-[#0d151c] px-3 text-sm text-[#cbd5e1] transition hover:bg-[#151b24] disabled:opacity-60"
          type="button"
          disabled={feed.isFetching || accounts.isFetching}
          onClick={() => {
            void accounts.refetch();
            void feed.refetch();
          }}
        >
          <RefreshCw className={feed.isFetching ? "animate-spin" : ""} size={14} />
          Atualizar
        </button>
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[216px_minmax(0,1fr)]">
        <nav
          aria-label="Perfis Instagram"
          className="flex gap-2 overflow-x-auto pb-1 xl:max-h-[calc(100vh-190px)] xl:flex-col xl:overflow-y-auto xl:overflow-x-hidden xl:pr-1"
        >
          {accounts.data.accounts.map((account) => {
            const selected = selectedAccount?.id === account.id;
            return (
              <button
                className={`flex min-w-[190px] items-center gap-3 rounded-lg border p-2.5 text-left transition xl:w-full ${
                  selected
                    ? "border-[#00c9d8] bg-[#0d2229]"
                    : "border-[#202838] bg-[#0d151c] hover:border-[#3a4a60]"
                }`}
                key={account.id}
                type="button"
                aria-current={selected ? "true" : undefined}
                onClick={() => setSelectedAccountId(account.id)}
              >
                <InstagramAvatar
                  className="size-10 shrink-0 rounded-full border border-[#27334a] object-cover"
                  src={account.profile_picture_url}
                  username={account.username}
                />
                <span className="min-w-0">
                  <span className="block truncate text-xs font-semibold text-[#f5f7fb]">
                    @{account.username}
                  </span>
                  <span className="mt-0.5 block text-[10px] text-[#94a3b8]">
                    {formatCount(account.follower_count)} seguidores
                  </span>
                </span>
              </button>
            );
          })}
        </nav>

        {selectedAccount && (
          <section className="min-w-0 space-y-3" aria-label={`Feed de ${selectedAccount.username}`}>
            <header className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#202838] bg-[#0d151c] px-3 py-2.5">
              <div className="flex min-w-0 items-center gap-2">
                <Star className="shrink-0 text-[#f2d48a]" size={15} />
                <h2 className="truncate text-sm font-semibold text-[#f5f7fb]">
                  @{selectedAccount.username}
                </h2>
                <span
                  className={`size-2 shrink-0 rounded-full ${
                    selectedAccount.status === "connected" ? "bg-[#22c58b]" : "bg-[#f17380]"
                  }`}
                  aria-label={
                    selectedAccount.status === "connected" ? "Conta conectada" : "Conta com erro"
                  }
                />
              </div>
              <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-[#cbd5e1]">
                <input
                  className="size-3.5 accent-[#00c9d8]"
                  type="checkbox"
                  checked={selectedAccount.has_highlights}
                  disabled={updateHighlights.isPending}
                  onChange={(event) => updateHighlights.mutate(event.target.checked)}
                />
                Tem destaques
              </label>
            </header>

            {updateError && <ErrorState message={updateError} />}

            <div className="grid gap-2 sm:grid-cols-3">
              <FeedMetric
                icon={UsersRound}
                label="Seguidores"
                value={formatCount(feed.data?.followers_count ?? selectedAccount.follower_count)}
              />
              <FeedMetric
                icon={ImageIcon}
                label="Posts"
                value={formatCount(feed.data?.media_count ?? selectedAccount.media_count)}
              />
              <FeedMetric
                icon={UsersRound}
                label="Seguindo"
                value={formatCount(feed.data?.follows_count)}
              />
            </div>

            <div className="flex items-center justify-between gap-3">
              <h3 className="text-xs font-medium text-[#94a3b8]">Mídias recentes</h3>
              {feed.data && (
                <span className="text-[10px] text-[#64748b]">
                  {feed.data.media.length} exibidas
                </span>
              )}
            </div>

            {feed.isLoading ? (
              <LoadingState label={`Carregando mídias de @${selectedAccount.username}`} />
            ) : feed.error ? (
              <ErrorState
                message={
                  displayError(feed.error, "Não foi possível carregar as mídias recentes.") ??
                  "Não foi possível carregar as mídias recentes."
                }
              />
            ) : feed.data?.media.length ? (
              <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
                {feed.data.media.map((item) => (
                  <article
                    className="overflow-hidden rounded-lg border border-[#202838] bg-[#0d151c]"
                    key={item.id}
                  >
                    {item.permalink ? (
                      <a
                        className="group relative block aspect-square overflow-hidden bg-[#080b10]"
                        href={item.permalink}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Abrir publicação de ${formatTimestamp(item.timestamp)} no Instagram`}
                      >
                        <MediaImage item={item} />
                        <MediaTypeBadge mediaType={item.media_type} />
                      </a>
                    ) : (
                      <div className="relative aspect-square overflow-hidden bg-[#080b10]">
                        <MediaImage item={item} />
                        <MediaTypeBadge mediaType={item.media_type} />
                      </div>
                    )}
                    <div className="space-y-2 p-2.5">
                      <div className="flex items-center gap-3 text-[10px] text-[#94a3b8]">
                        <span className="inline-flex items-center gap-1">
                          <UsersRound size={11} />
                          {formatCount(item.like_count)}
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <MessageCircle size={11} />
                          {formatCount(item.comments_count)}
                        </span>
                      </div>
                      <time className="block text-[9px] text-[#64748b]">
                        {formatTimestamp(item.timestamp)}
                      </time>
                      {item.caption && (
                        <p className="line-clamp-2 text-[10px] leading-4 text-[#aeb9ce]">
                          {item.caption}
                        </p>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState message="O Instagram não retornou mídias recentes para este perfil." />
            )}
          </section>
        )}
      </div>

      <p className="text-[11px] leading-5 text-[#64748b]">
        O Instagram não disponibiliza a contagem de perfis seguidos nesta integração; por isso esse
        indicador aparece como “—”. O Feed mostra até 25 publicações recentes por perfil.
      </p>
    </div>
  );
}

function FeedHeading() {
  return (
    <header>
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
        Perfis &amp; Métricas
      </p>
      <h1 className="mt-1 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb]">
        Veja seguidores, posts e mídias de cada perfil.
      </h1>
    </header>
  );
}

function MediaImage({ item }: { item: InstagramFeedMedia }) {
  const source = item.thumbnail_url ?? item.media_url;
  if (!source) {
    return (
      <div className="grid size-full place-items-center text-[#64748b]">
        <ImageIcon size={28} />
      </div>
    );
  }
  return (
    <img
      alt={item.caption?.slice(0, 140) || "Publicação recente do Instagram"}
      className="size-full object-cover transition duration-300 group-hover:scale-[1.02]"
      loading="lazy"
      referrerPolicy="no-referrer"
      src={source}
    />
  );
}

function MediaTypeBadge({ mediaType }: { mediaType: string }) {
  return (
    <span className="absolute right-2 top-2 rounded bg-[#080b10]/75 p-1 text-white">
      {mediaType === "VIDEO" || mediaType === "REELS" ? (
        <span className="text-[9px] font-semibold">REEL</span>
      ) : (
        <ImageIcon size={12} />
      )}
    </span>
  );
}
