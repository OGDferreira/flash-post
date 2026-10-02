import {
  createContext,
  useContext,
  type PropsWithChildren,
} from "react";
import { useQuery } from "@tanstack/react-query";

import { ApiError, apiRequest, type User } from "@/services/api";

type AuthState = {
  user: User | null;
  isLoading: boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const auth = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiRequest<User>("/api/auth/me"),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 401) && failureCount < 1,
    staleTime: 30_000,
  });

  const isUnauthorized = auth.error instanceof ApiError && auth.error.status === 401;
  const user = auth.data ?? null;

  return (
    <AuthContext.Provider
      value={{ user, isLoading: auth.isLoading && !isUnauthorized }}
    >
      {children}
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
