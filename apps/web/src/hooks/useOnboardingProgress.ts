import { useQueries } from "@tanstack/react-query";
import { api } from "@/api";
import type { OnboardingStep } from "@/lib/onboarding";
import { useConversations, useDocuments } from "./queries";

const MESSAGE_PROBE_LIMIT = 5;

export function useOnboardingProgress(workspaceId: string | undefined) {
  const { data: documents = [], isLoading: docsLoading } =
    useDocuments(workspaceId);
  const { data: conversations = [], isLoading: convsLoading } =
    useConversations(workspaceId);

  const convIds = conversations.slice(0, MESSAGE_PROBE_LIMIT).map((c) => c.id);
  const messageQueries = useQueries({
    queries: convIds.map((id) => ({
      queryKey: ["messages", id],
      queryFn: () => api.messages(id),
      enabled: !!workspaceId && convIds.length > 0,
      staleTime: 60_000,
    })),
  });

  const hasUploaded = documents.length > 0;
  const hasReady = documents.some((d) => d.status === "ready");
  const hasChatted = messageQueries.some((q) =>
    q.data?.some((m) => m.role === "user" && m.content.trim()),
  );

  const messagesLoading =
    convIds.length > 0 && messageQueries.some((q) => q.isLoading);

  const steps: OnboardingStep[] = [
    {
      id: "upload",
      label: "Upload a document",
      description: "Add PDF, DOCX, or text files to your workspace",
      href: "/documents",
      done: hasUploaded,
    },
    {
      id: "ingest",
      label: "Ingest for chat",
      description: "Run ingest until status shows ready",
      href: "/documents",
      done: hasReady,
    },
    {
      id: "chat",
      label: "Ask your first question",
      description: "Use Chat mode for grounded answers with citations",
      href: "/chat",
      done: hasChatted,
    },
  ];

  const completedCount = steps.filter((s) => s.done).length;
  const isComplete = completedCount === steps.length;
  const loading = docsLoading || convsLoading || messagesLoading;
  const currentStep = steps.find((s) => !s.done) ?? null;

  return {
    steps,
    completedCount,
    totalSteps: steps.length,
    isComplete,
    loading,
    currentStep,
  };
}