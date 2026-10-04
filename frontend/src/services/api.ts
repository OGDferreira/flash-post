export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

function isRawBody(body: unknown): body is BodyInit {
  return (
    typeof body === "string" ||
    body instanceof Blob ||
    body instanceof FormData ||
    body instanceof URLSearchParams ||
    body instanceof ArrayBuffer ||
    ArrayBuffer.isView(body)
  );
}

let csrfToken: string | undefined;

export function setCsrfToken(token: string | undefined) {
  csrfToken = token;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body !== undefined && !isRawBody(options.body)) {
    headers.set("Content-Type", "application/json");
  }

  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    if (!csrfToken) {
      const tokenResponse = await fetch("/api/auth/csrf", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!tokenResponse.ok) {
        throw new ApiError(tokenResponse.status, "Could not start a secure session.");
      }
      const tokenBody = (await tokenResponse.json()) as { csrf_token: string };
      csrfToken = tokenBody.csrf_token;
    }
    headers.set("X-CSRF-Token", csrfToken);
  }

  const response = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: "same-origin",
    body:
      options.body === undefined
        ? undefined
        : isRawBody(options.body)
          ? options.body
          : JSON.stringify(options.body),
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const body = (await response.json().catch(() => null)) as
    | { detail?: string; csrf_token?: string }
    | null;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      body?.detail ?? "The request could not be completed.",
    );
  }
  if (body && typeof body.csrf_token === "string") {
    csrfToken = body.csrf_token;
  }
  return body as T;
}

export type User = {
  id: string;
  email: string;
  username: string | null;
  nickname: string;
  full_name: string;
  avatar_url: string | null;
  role: "SUPER_ADMIN" | "OWNER" | "COLLABORATOR" | "USER";
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
};

export type Workspace = {
  id: string;
  name: string;
  slug: string;
  status: string;
  role: string;
  created_at: string;
};

export type AdminSummary = {
  users_total: number;
  workspaces_total: number;
  owners: number;
  collaborators: number;
  active_users: number;
};

export type AdminUser = {
  id: string;
  full_name: string;
  email: string;
  role: string;
  status: string;
  workspace_name: string | null;
  created_at: string;
  last_login_at: string | null;
};

export type AdminWorkspace = {
  id: string;
  name: string;
  slug: string;
  owner_name: string;
  owner_email: string;
  status: string;
  members_count: number;
  created_at: string;
};

export type CollaboratorReport = {
  member_id: string;
  user_id: string;
  full_name: string;
  nickname: string;
  email: string;
  rate_per_connection: number;
  daily_connection_goal: number;
  monthly_connection_goal: number;
  monthly_bonus: number;
  connections_today: number;
  connections_month: number;
  earnings_today: number;
  earnings_month: number;
  paid_month: number;
  due_month: number;
  paid_total: number;
  projected_month: number;
  recent_days: number[];
  recent_earnings: number[];
  recent_payments: number[];
  account_earnings: {
    account_id: string;
    username: string;
    connected_at: string | null;
    rate_per_connection: number;
  }[];
};

export type CollaboratorDashboard = Omit<
  CollaboratorReport,
  "member_id" | "user_id" | "email"
> & {
  avatar_url: string | null;
  daily_progress: number;
  monthly_progress: number;
};

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};
