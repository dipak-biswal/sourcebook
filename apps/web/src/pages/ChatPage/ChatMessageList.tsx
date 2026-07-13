import { Link, useNavigate } from "react-router-dom";
import { AlertCircle, Bot, Loader2, MessageCircle, Sparkles } from "lucide-react";
import { TypingIndicator } from "@/components/chat/TypingIndicator";
import { AgentRunPanel } from "@/components/agents/AgentRunPanel";
import { GenerativeUIView } from "@/components/agents/GenerativeUI";
import { extractGenerativeUIFromSteps } from "@/components/agents/generative-ui";
import { CitationList } from "@/components/chat/CitationList";
import { isDenialMessage, shouldShowSources } from "@/components/chat/citations";
import { CopyButton } from "@/components/chat/CopyButton";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { MessageListSkeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/api";
import type { AgentThreadItem } from "@/types/chat";
import { useChatSuggestions } from "@/hooks/queries";
import { useChatPage } from "./chat-page-context";

function ChatBubble({
  isUser,
  children,
}: {
  isUser: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "max-w-[min(90%,36rem)] rounded-vercel-md border px-3.5 py-2.5 text-body-sm leading-relaxed",
        isUser
          ? "rounded-br-sm border-ink bg-ink text-[var(--canvas)]"
          : "rounded-bl-sm border-hairline bg-canvas text-body shadow-[var(--elevation-2)]",
      )}
    >
      {children}
    </div>
  );
}

function DenialBubble({
  content,
}: {
  content: string;
}) {
  const navigate = useNavigate();

  return (
    <div className="max-w-[90%] rounded-vercel-md border border-warning-border bg-warning-soft px-3.5 py-3 text-body-sm text-warning-text">
      <div className="mb-1.5 flex items-center gap-1.5 font-medium">
        <AlertCircle
          className="h-4 w-4 shrink-0"
          strokeWidth={1.5}
        />
        No grounded match
      </div>
      <div className="whitespace-pre-wrap leading-relaxed">
        {content}
      </div>
      <button
        type="button"
        className="mt-3 text-xs font-medium text-ink underline-offset-2 hover:underline"
        onClick={() => navigate("/documents")}
      >
        Go to Documents → ingest
      </button>
    </div>
  );
}

function AgentBubbleHeader({ pending }: { pending?: boolean }) {
  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5">
      <Bot className="h-3.5 w-3.5 text-mute" strokeWidth={1.5} />
      <Badge variant="secondary" className="text-[10px]">
        Agent
      </Badge>
      {pending && (
        <Loader2 className="h-3.5 w-3.5 animate-spin text-mute" />
      )}
    </div>
  );
}

function ChatMessageItem({
  message,
  streaming = false,
}: {
  message: ChatMessage;
  streaming?: boolean;
}) {
  const isUser = message.role === "user";
  const denial =
    !isUser && message.content && isDenialMessage(message.content);
  const showTyping = !isUser && streaming && !message.content;

  return (
    <div
      className={cn(
        "flex flex-col",
        isUser ? "items-end" : "items-start",
      )}
    >
      {denial ? (
        <DenialBubble content={message.content} />
      ) : (
        <ChatBubble isUser={isUser}>
          {isUser ? (
            <div className="whitespace-pre-wrap">{message.content}</div>
          ) : showTyping ? (
            <TypingIndicator />
          ) : (
            <MarkdownContent content={message.content} />
          )}
        </ChatBubble>
      )}
      {!isUser && message.content && !denial && (
        <div className="mt-1">
          <CopyButton text={message.content} />
        </div>
      )}
      {!isUser &&
        shouldShowSources(message.content, message.citations) && (
          <CitationList citations={message.citations} />
        )}
    </div>
  );
}

const TERMINAL_RUN_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "waiting_approval",
]);

function AgentMessageItem({
  item,
}: {
  item: AgentThreadItem;
}) {
  const { approving, savingNote, onApproveAgent, onSaveLearningNote } = useChatPage();
  const isUser = item.role === "user";
  const showAgentsLink =
    !isUser &&
    !item.pending &&
    item.run &&
    TERMINAL_RUN_STATUSES.has(item.run.status);

  return (
    <div
      className={cn(
        "flex flex-col",
        isUser ? "items-end" : "items-start",
      )}
    >
      <ChatBubble isUser={isUser}>
        {!isUser && <AgentBubbleHeader pending={item.pending} />}
        {isUser ? (
          <div className="whitespace-pre-wrap">{item.content}</div>
        ) : (
          <MarkdownContent content={item.content} />
        )}
      </ChatBubble>

      {!isUser && item.content && !item.pending && (
        <div className="mt-1">
          <CopyButton text={item.content} />
        </div>
      )}

      {!isUser &&
        (() => {
          const gen = extractGenerativeUIFromSteps(
            item.liveSteps ?? item.run?.steps ?? [],
          );
          return gen ? (
            <div className="mt-2 w-full max-w-[min(100%,36rem)]">
              <GenerativeUIView
                payload={gen}
                onSaveAsNote={(t, b) =>
                  onSaveLearningNote(t, b)
                }
                savingNote={savingNote}
              />
            </div>
          ) : null;
        })()}

      {showAgentsLink && (
        <Link
          to={`/agents?run=${item.run!.id}`}
          className="mt-2 text-xs font-medium text-ink underline-offset-2 hover:underline"
        >
          Open full trace in Agents →
        </Link>
      )}

      {!isUser && (item.run || item.pending) && (
        <div className="mt-2 w-full max-w-[min(100%,40rem)]">
          <AgentRunPanel
            run={item.run}
            pending={!!item.pending}
            goal={item.goal || item.run?.goal}
            liveSteps={item.liveSteps}
            liveTokenUsage={item.liveTokenUsage}
            liveLlmEvents={item.liveLlmEvents}
            liveTrace={item.liveTrace}
            approving={approving}
            forceOpenWhilePending
            onApprove={
              item.run
                ? () =>
                    onApproveAgent(
                      item.id,
                      item.run!.id,
                      true,
                    )
                : undefined
            }
            onReject={
              item.run
                ? () =>
                    onApproveAgent(
                      item.id,
                      item.run!.id,
                      false,
                    )
                : undefined
            }
          />
        </div>
      )}
    </div>
  );
}

function SuggestionChips({
  questions,
  onSend,
  disabled,
}: {
  questions: string[];
  onSend: (q: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="mx-auto mt-4 flex max-w-lg flex-wrap justify-center gap-2">
      {questions.map((q, i) => (
        <button
          key={i}
          type="button"
          disabled={disabled}
          onClick={() => onSend(q)}
          className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-canvas px-3.5 py-1.5 text-xs font-medium text-body transition-colors hover:border-ink hover:bg-canvas-soft hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Sparkles className="h-3 w-3 shrink-0 text-mute" strokeWidth={1.5} />
          <span className="line-clamp-1 max-w-[240px]">{q}</span>
        </button>
      ))}
    </div>
  );
}

export function ChatMessageList() {
  const navigate = useNavigate();
  const {
    mode,
    messages,
    agentThread,
    sending,
    error,
    empty,
    workspaceId,
    bottomRef,
    loadingMessageHistory,
    onSendMessage,
  } = useChatPage();

  const streamingMessageId =
    sending && mode === "chat"
      ? [...messages].reverse().find((m) => m.role === "assistant")?.id
      : undefined;

  const { data: suggestions, isLoading: loadingSuggestions } = useChatSuggestions(
    mode === "chat" ? workspaceId : undefined,
  );

  return (
    <>
      {error && (
        <div className="px-4 pt-3 sm:px-6">
          <Alert variant="danger">{error}</Alert>
        </div>
      )}

      <div className="document-scroll min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
        {loadingMessageHistory && mode === "chat" ? (
          <MessageListSkeleton />
        ) : empty ? (
          <div className="flex flex-col items-center">
            <EmptyState
              icon={mode === "agent" ? Bot : MessageCircle}
              title={
                mode === "agent"
                  ? "Quick agent run"
                  : "Ask about your documents"
              }
              description={
                mode === "agent"
                  ? "Run tools in this thread — list/search docs or create a note (writes need approval). For full history, traces, and notes, use the Agents page."
                  : "Upload PDF, DOCX, or text files, ingest until ready, then ask grounded questions here."
              }
              actionLabel={mode === "chat" ? "Open documents" : "Open Agents page"}
              onAction={
                mode === "chat"
                  ? () => navigate("/documents")
                  : () => navigate("/agents")
              }
            />
            {mode === "chat" && suggestions && suggestions.length > 0 && (
              <>
                <p className="mt-6 text-center text-[11px] font-medium uppercase tracking-wide text-mute">
                  Suggested questions
                </p>
                <SuggestionChips
                  questions={suggestions}
                  onSend={onSendMessage}
                  disabled={sending}
                />
              </>
            )}
            {mode === "chat" && loadingSuggestions && (
              <div className="mt-6 flex items-center gap-2 text-xs text-mute">
                <Loader2 className="h-3 w-3 animate-spin" />
                Generating suggestions…
              </div>
            )}
          </div>
        ) : (
          <div
            className="mx-auto flex max-w-2xl flex-col gap-4"
            aria-live="polite"
            aria-relevant="additions text"
          >
            {mode === "chat"
              ? messages.map((m) => (
                  <ChatMessageItem
                    key={m.id}
                    message={m}
                    streaming={m.id === streamingMessageId}
                  />
                ))
              : agentThread.map((item) => (
                  <AgentMessageItem
                    key={item.id}
                    item={item}
                  />
                ))}
            <div ref={bottomRef} aria-hidden className="h-px shrink-0" />
          </div>
        )}
      </div>
    </>
  );
}
