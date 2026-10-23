import { useOutletContext } from "react-router-dom";

export type NoticeItem = { title: string; message: string; at?: string | null };

/** What the shell hands its pages: the notices shown in the Avisos tab. */
export type ShellContext = { notificationItems: NoticeItem[] };

export function useShellContext(): ShellContext {
  return useOutletContext<ShellContext | undefined>() ?? { notificationItems: [] };
}
