import type { User } from "@/services/api";

export function canChooseHome(user: User | null) {
  return user?.role === "OWNER" || (user?.role === "SUPER_ADMIN" && user.workspace_role === "OWNER");
}

export function homePath(user: User) {
  if (canChooseHome(user)) return user.home_panel === "flashbot" ? "/bot" : "/dashboard";
  if (user.role === "COLLABORATOR" || user.workspace_role === "COLLABORATOR") return "/feature/accounts";
  return user.role === "SUPER_ADMIN" ? "/admin" : "/dashboard";
}
