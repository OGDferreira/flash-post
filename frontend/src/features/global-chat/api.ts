import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "@/services/api";

export type ChatMessage = {
  id: string;
  author_id: string;
  author_nickname: string;
  author_avatar_url: string | null;
  body: string | null;
  has_image: boolean;
  image_url: string | null;
  is_mine: boolean;
  can_delete: boolean;
  created_at: string;
};

type MessageListResponse = {
  items: ChatMessage[];
  server_time: string;
};

const CHAT_KEY = ["global-chat", "messages"] as const;

/** The whole visible window, refreshed on a short poll (messages live only 36h). */
export function useChatMessages() {
  return useQuery({
    queryKey: CHAT_KEY,
    queryFn: () => apiRequest<MessageListResponse>("/api/global-chat/messages?limit=80"),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
    staleTime: 2000,
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) =>
      apiRequest<ChatMessage>("/api/global-chat/messages", {
        method: "POST",
        body: { body },
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: CHAT_KEY }),
  });
}

export function useSendPhoto() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, caption }: { file: File; caption: string }) => {
      const query = caption.trim() ? `?caption=${encodeURIComponent(caption.trim())}` : "";
      return apiRequest<ChatMessage>(`/api/global-chat/messages/photo${query}`, {
        method: "POST",
        headers: { "Content-Type": file.type },
        body: file,
      });
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: CHAT_KEY }),
  });
}

export function useDeleteMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/api/global-chat/messages/${id}`, { method: "DELETE" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: CHAT_KEY }),
  });
}
