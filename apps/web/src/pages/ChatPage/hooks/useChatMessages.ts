import { useQueryClient } from "@tanstack/react-query";
import { api, type ChatMessage } from "@/api";
import { formatError } from "@/lib/utils";

export function useChatMessages(
  workspaceId: string,
  conversationId: string,
  setConversationId: (id: string) => void,
  setError: (err: string | null) => void,
  setMessages: (msgs: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => void,
  setInput: (v: string) => void,
) {
  const queryClient = useQueryClient();

  async function onSendChat(text: string) {
    const userTempId = `temp-user-${Date.now()}`;
    const asstTempId = `temp-asst-${Date.now()}`;

    setMessages((prev) => [
      ...prev,
      {
        id: userTempId,
        conversation_id: conversationId || "pending",
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
      },
      {
        id: asstTempId,
        conversation_id: conversationId || "pending",
        role: "assistant",
        content: "",
        citations: [],
        created_at: new Date().toISOString(),
      },
    ]);

    try {
      let convId = conversationId;
      if (!convId) {
        const conv = await api.createConversation(workspaceId, "New chat");
        convId = conv.id;
        setConversationId(convId);
      }

      await api.chatStream(convId, text, {
        onToken: (chunk) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === asstTempId
                ? { ...m, content: m.content + chunk }
                : m,
            ),
          );
        },
        onCitations: (citations) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === asstTempId ? { ...m, citations } : m,
            ),
          );
        },
      });

      await queryClient.invalidateQueries({ queryKey: ["messages", convId] });
      await queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] });
      const updated = queryClient.getQueryData<ChatMessage[]>(["messages", convId]);
      if (updated) {
        setMessages(
          [...updated].sort((a, b) => {
            const ta = new Date(a.created_at).getTime();
            const tb = new Date(b.created_at).getTime();
            if (ta !== tb) return ta - tb;
            if (a.role === "user" && b.role === "assistant") return -1;
            if (a.role === "assistant" && b.role === "user") return 1;
            return a.id.localeCompare(b.id);
          }),
        );
      }
      if (convId !== conversationId) setConversationId(convId);
    } catch (err) {
      setError(formatError(err));
      setMessages((prev) =>
        prev.filter((m) => m.id !== userTempId && m.id !== asstTempId),
      );
      setInput(text);
    }
  }

  return { onSendChat };
}
