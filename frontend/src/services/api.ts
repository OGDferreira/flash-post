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
let diagnosticsQueue: Promise<void> = Promise.resolve();
const reportedClientErrors = new Map<string, number>();

export function setCsrfToken(token: string | undefined) {
  csrfToken = token;
}

export function reportClientError(
  source: "browser" | "client_api",
  message: string,
  stack?: string,
): Promise<void> {
  if (!message.trim()) return Promise.resolve();
  const path = window.location.pathname;
  const dedupeKey = `${source}:${path}:${message}`;
  const previousReport = reportedClientErrors.get(dedupeKey) ?? 0;
  if (Date.now() - previousReport < 10_000) return Promise.resolve();
  reportedClientErrors.set(dedupeKey, Date.now());

  const submit = async () => {
    try {
      if (!csrfToken) {
        const csrfResponse = await fetch("/api/auth/csrf", {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (!csrfResponse.ok) return;
        const csrfBody = (await csrfResponse.json()) as { csrf_token: string };
        csrfToken = csrfBody.csrf_token;
      }
      await fetch("/api/diagnostics/events", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({
          source,
          level: "error",
          message: message.slice(0, 2000),
          stack: stack?.slice(0, 8000) ?? null,
          path,
        }),
      });
    } catch {
      // Diagnostics are best-effort and must not trigger a second browser error.
    }
    if (reportedClientErrors.size > 200) {
      const oldestKey = reportedClientErrors.keys().next().value;
      if (oldestKey) reportedClientErrors.delete(oldestKey);
    }
  };
  diagnosticsQueue = diagnosticsQueue.then(submit, submit);
  return diagnosticsQueue;
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
    if (response.status === 401 && !path.startsWith("/api/auth/")) {
      // The session ended (logout elsewhere, expiry): let the app go back to the login page.
      window.dispatchEvent(new Event("flashpost:session-ended"));
    }
    if (response.status >= 500 && !path.startsWith("/api/diagnostics/")) {
      const message =
        body?.detail ?? `The server returned HTTP ${response.status}.`;
      void reportClientError(
        "client_api",
        `${method} ${path.split("?")[0]}: ${message}`,
      );
    }
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
  workspace_role: "OWNER" | "COLLABORATOR" | null;
  home_panel: "flashpost" | "flashbot" | null;
  is_active: boolean;
  is_verified: boolean;
  is_approved: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
  /** Set while a Super Admin is inside this account via "Entrar". */
  impersonator_name?: string | null;
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
  flashbot_sales_today: number;
  flashbot_revenue_today: string;
  transaction_fees_today: string;
  transaction_fee_default: string;
  fee_pix_generated_today: number;
  fee_pix_paid_today: number;
};

export type AdminUser = {
  id: string;
  full_name: string;
  email: string;
  role: string;
  platform_role?: "USER" | "SUPER_ADMIN";
  status: "PENDING_APPROVAL" | "ACTIVE" | "BLOCKED";
  is_approved: boolean;
  is_active?: boolean;
  workspace_name: string | null;
  created_at: string;
  last_login_at: string | null;
  hierarchy?: "chief" | "partner" | "independent";
  transaction_fee?: string | null; // own Flash fee per sale; null = the default
  transaction_fee_effective?: string;
  withdrawals_blocked?: boolean;
  can_invite_partners?: boolean;
  chief_name?: string | null;
  invited_by_name?: string | null;
};

export type AdminWorkspace = {
  id: string;
  name: string;
  slug: string;
  owner_id?: string | null;
  owner_name: string;
  owner_email: string;
  status: string;
  members_count: number;
  connected_accounts: number;
  errored_accounts: number;
  active_posts: number;
  collaborators: { id: string; full_name: string; email: string }[];
  created_at: string;
};

export type CollaboratorReport = {
  member_id: string;
  user_id: string;
  membership_started_at: string;
  access_status: "ACTIVE" | "SUSPENDED";
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
  recent_dates: string[];
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
