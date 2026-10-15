
import { type PendingCollaborator } from "@/components/CollaboratorInvitesPanel";
import { ApiError, type CollaboratorReport } from "@/services/api";

export type CollaboratorsResponse = {
  pending?: PendingCollaborator[];
  collaborators: CollaboratorReport[];
  owner_connections_today: number;
  team_connections_today: number;
};

export type CollaboratorRankingResponse = {
  month: string;
  total_connections: number;
  collaborators: {
    user_id: string;
    full_name: string;
    nickname: string;
    connections: number;
    position: number;
  }[];
};

export type CollaboratorDraft = {
  rate_per_connection: number;
  daily_connection_goal: number;
  monthly_connection_goal: number;
  monthly_bonus: number;
};

export type CollaboratorUpdateDraft = CollaboratorDraft & {
  apply_rate_to_existing_accounts: boolean;
};

export type WorkDaysResponse = {
  month: string;
  daily_rate: number;
  total_connections: number;
  total_amount: number;
  days: { day: string; connections: number; amount: number; paid: boolean }[];
};

export type NewCollaboratorForm = CollaboratorDraft & {
  full_name: string;
  nickname: string;
  email: string;
  password: string;
};

export const blankForm: NewCollaboratorForm = {
  full_name: "",
  nickname: "",
  email: "",
  password: "",
  rate_per_connection: 0,
  daily_connection_goal: 0,
  monthly_connection_goal: 0,
  monthly_bonus: 0,
};

export function money(value: number) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

export function formatConnectionDate(value: string | null) {
  if (!value) return "Data indisponível";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  }).format(new Date(value));
}

export function displayError(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : error ? fallback : null;
}

export function draftFrom(item: CollaboratorReport): CollaboratorUpdateDraft {
  return {
    rate_per_connection: item.rate_per_connection,
    daily_connection_goal: item.daily_connection_goal,
    monthly_connection_goal: item.monthly_connection_goal,
    monthly_bonus: item.monthly_bonus,
    apply_rate_to_existing_accounts: false,
  };
}
