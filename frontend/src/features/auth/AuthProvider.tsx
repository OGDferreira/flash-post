import {
  createContext,
  useContext,
  useEffect,
  type PropsWithChildren,
} from "react";
import { useIsRestoring, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, apiRequest, type User } from "@/services/api";
import { ImpersonationBanner } from "@/features/auth/ImpersonationBanner";
import { claimCache } from "@/lib/queryCache";

type AuthState = {
  user: User | null;
  isLoading: boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient();
  useEffect(() => {
    const ended = () => {
      if (queryClient.getQueryData(["auth", "me"])) void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    };
    window.addEventListener("flashpost:session-ended", ended);
    return () => window.removeEventListener("flashpost:session-ended", ended);
  }, [queryClient]);
  const auth = useQuery({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      const me = await apiRequest<User>("/api/auth/me");
      claimCache(queryClient, me.id); // never show data cached for another login
      return me;
    },
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 401) && failureCount < 1,
    staleTime: 30_000,
  });

  const restoring = useIsRestoring();
  const isUnauthorized = auth.error instanceof ApiError && auth.error.status === 401;
  const user = isUnauthorized ? null : (auth.data ?? null);

  return (
    <AuthContext.Provider
      // While the saved cache is being restored the session query hasn't started yet (pending
      // but not fetching): still loading, never "logged out" (that bounced deep links to /login).
      value={{ user, isLoading: (auth.isPending || restoring) && !isUnauthorized }}
    >
      {children}
      {user?.impersonator_name && (
        <ImpersonationBanner userName={user.full_name} adminName={user.impersonator_name} />
      )}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return context;
}
