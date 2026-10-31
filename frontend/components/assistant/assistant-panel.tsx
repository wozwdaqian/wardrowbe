"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { Bot, Loader2, MessageSquarePlus, Send, Undo2 } from "lucide-react";
import { api, ApiError, streamApi, type StreamEvent } from "@/lib/api";
import { queryKeys } from "@/lib/hooks/query-keys";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export type AssistantAction = {
  id: string;
  tool: string;
  status: "pending" | "applied" | "rejected" | "undone" | "failed";
  summary: string;
  result: Record<string, unknown> | null;
  undoable: boolean;
  created_at?: string | null;
};
type Entry =
  | {
      kind: "message";
      key: string;
      role: "user" | "assistant";
      content: string;
    }
  | { kind: "action"; key: string; action: AssistantAction };
type Conversation = {
  id: string;
  messages: {
    id: string;
    role: "user" | "assistant";
    content: string;
    created_at: string;
  }[];
  actions: AssistantAction[];
};

const STORAGE_KEY = "wardrowbe.assistant.conversation";
export const OPEN_EVENT = "wardrowbe:assistant-open";

// Lets any page open the panel, optionally with a prepared question.
export function openAssistant(prompt?: string) {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: { prompt } }));
}

function rememberedConversation(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}
function remember(id: string | null) {
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage can be unavailable (private mode); the panel then starts fresh each time.
  }
}

// What a tool may have changed, so open pages show the new data at once.
export function refreshAfter(queryClient: QueryClient, tool: string) {
  const keys: readonly (readonly unknown[])[] =
    tool === "update_profile"
      ? [queryKeys.userProfile, queryKeys.bodyStyling.todayAll]
      : tool === "log_wear"
        ? [
            queryKeys.items.all,
            queryKeys.wearStats.all,
            queryKeys.wearHistory.all,
          ]
        : [
            queryKeys.bodyStyling.history.all,
            queryKeys.bodyStyling.reports,
            queryKeys.bodyStyling.unread,
          ];
  for (const queryKey of keys) queryClient.invalidateQueries({ queryKey });
}

export function AssistantPanel() {
  const t = useTranslations("assistant");
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [tool, setTool] = useState<string | null>(null);
  const [error, setError] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const loaded = useRef(false);

  useEffect(() => {
    function onOpen(event: Event) {
      const prompt = (event as CustomEvent<{ prompt?: string }>).detail?.prompt;
      setOpen(true);
      if (prompt) setInput(prompt);
    }
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_EVENT, onOpen);
  }, []);

  useEffect(() => {
    if (!open || loaded.current) return;
    loaded.current = true;
    const id = rememberedConversation();
    if (!id) return;
    api
      .get<Conversation>(`/assistant/conversations/${id}`)
      .then((conversation) => {
        setConversationId(conversation.id);
        const timeline = [
          ...conversation.messages.map((m) => ({
            at: m.created_at,
            entry: {
              kind: "message",
              key: m.id,
              role: m.role,
              content: m.content,
            } as Entry,
          })),
          ...conversation.actions.map((a) => ({
            at: a.created_at || "",
            entry: { kind: "action", key: a.id, action: a } as Entry,
          })),
        ].sort((a, b) => a.at.localeCompare(b.at));
        setEntries(timeline.map((item) => item.entry));
      })
      .catch(() => remember(null));
  }, [open]);

  useEffect(() => {
    listRef.current?.scrollTo?.({ top: listRef.current.scrollHeight });
  }, [entries, tool]);

  const upsertAction = useCallback((action: AssistantAction) => {
    setEntries((current) =>
      current.some((e) => e.kind === "action" && e.action.id === action.id)
        ? current.map((e) =>
            e.kind === "action" && e.action.id === action.id
              ? { ...e, action }
              : e,
          )
        : [...current, { kind: "action", key: action.id, action }],
    );
  }, []);

  const consume = useCallback(
    async (events: AsyncGenerator<StreamEvent>) => {
      for await (const event of events) {
        if (event.type === "tool") setTool(String(event.name));
        else if (event.type === "message") {
          setTool(null);
          setEntries((current) => [
            ...current,
            {
              kind: "message",
              key: String(event.id),
              role: "assistant",
              content: String(event.content),
            },
          ]);
        } else if (event.type === "action") {
          const action = event.action as AssistantAction;
          upsertAction(action);
          if (action.status === "applied")
            refreshAfter(queryClient, action.tool);
        } else if (event.type === "error") {
          setError(
            t(
              "error." +
                (event.code === "ai_unavailable"
                  ? "ai_unavailable"
                  : "ai_failed"),
            ),
          );
        }
      }
    },
    [queryClient, t, upsertAction],
  );

  async function run(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 429
          ? t("error.rate")
          : err instanceof ApiError && err.status === 409
            ? t("error.action", { message: err.message })
            : t("error.generic"),
      );
    } finally {
      setBusy(false);
      setTool(null);
    }
  }

  function send(event?: FormEvent) {
    event?.preventDefault();
    const content = input.trim();
    if (!content || busy) return;
    setInput("");
    setEntries((current) => [
      ...current,
      { kind: "message", key: `local-${Date.now()}`, role: "user", content },
    ]);
    run(async () => {
      let id = conversationId;
      if (!id) {
        id = (await api.post<{ id: string }>("/assistant/conversations")).id;
        setConversationId(id);
        remember(id);
      }
      await consume(
        streamApi(`/assistant/conversations/${id}/messages`, { content }),
      );
    });
  }

  function decide(
    action: AssistantAction,
    verb: "confirm" | "reject" | "undo",
  ) {
    run(async () => {
      const updated = await api.post<AssistantAction>(
        `/assistant/actions/${action.id}/${verb}`,
      );
      upsertAction(updated);
      if (updated.status === "applied" || updated.status === "undone")
        refreshAfter(queryClient, updated.tool);
      // The model reacts to a decision on a proposal; an undo is only noted for later turns.
      if (verb !== "undo" && conversationId)
        await consume(
          streamApi(`/assistant/conversations/${conversationId}/continue`),
        );
    });
  }

  function newChat() {
    remember(null);
    setConversationId(null);
    setEntries([]);
    setError("");
  }

  const prompts = ["today", "explain", "commute", "waist"] as const;

  return (
    <>
      <Button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-20 right-4 z-40 h-12 rounded-full bg-emerald-800 px-4 text-white shadow-lg hover:bg-emerald-900 lg:bottom-6"
        aria-label={t("open")}
      >
        <Bot className="h-5 w-5 sm:mr-2" />
        <span className="hidden sm:inline">{t("open")}</span>
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="left-auto right-0 top-0 flex h-full max-h-screen w-full max-w-md translate-x-0 translate-y-0 flex-col gap-0 p-0 data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:rounded-none">
          <div className="flex items-center justify-between gap-2 border-b px-4 py-3 pr-12">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Bot className="h-5 w-5 text-emerald-700" />
              {t("title")}
            </DialogTitle>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={newChat}
              disabled={busy}
            >
              <MessageSquarePlus className="mr-1.5 h-4 w-4" />
              {t("newChat")}
            </Button>
          </div>
          <DialogDescription className="sr-only">
            {t("intro")}
          </DialogDescription>
          <div
            ref={listRef}
            className="flex-1 space-y-3 overflow-y-auto px-4 py-4"
            aria-live="polite"
          >
            {!entries.length && (
              <div className="space-y-3">
                <p className="text-sm leading-6 text-muted-foreground">
                  {t("intro")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {prompts.map((key) => (
                    <Button
                      key={key}
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-auto whitespace-normal py-1.5 text-left text-xs"
                      onClick={() => setInput(t("prompts." + key))}
                    >
                      {t("prompts." + key)}
                    </Button>
                  ))}
                </div>
              </div>
            )}
            {entries.map((entry) =>
              entry.kind === "message" ? (
                <div
                  key={entry.key}
                  className={cn(
                    "max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm leading-6",
                    entry.role === "user"
                      ? "ml-auto bg-emerald-800 text-white"
                      : "bg-muted",
                  )}
                >
                  {entry.content}
                </div>
              ) : (
                <ActionCard
                  key={entry.key}
                  action={entry.action}
                  busy={busy}
                  onDecide={(verb) => decide(entry.action, verb)}
                />
              ),
            )}
            {busy && (
              <p
                className="flex items-center gap-2 text-xs text-muted-foreground"
                role="status"
              >
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {tool
                  ? t("usingTool", { tool: t("tools." + tool) })
                  : t("thinking")}
              </p>
            )}
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </div>
          <form onSubmit={send} className="flex items-end gap-2 border-t p-3">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={2}
              maxLength={2000}
              placeholder={t("placeholder")}
              aria-label={t("placeholder")}
              className="min-h-[44px] flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
            <Button
              type="submit"
              size="icon"
              disabled={busy || !input.trim()}
              aria-label={t("send")}
            >
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ActionCard({
  action,
  busy,
  onDecide,
}: {
  action: AssistantAction;
  busy: boolean;
  onDecide: (verb: "confirm" | "reject" | "undo") => void;
}) {
  const t = useTranslations("assistant");
  const reportId =
    action.status === "applied" && typeof action.result?.id === "string"
      ? action.result.id
      : null;
  return (
    <div
      className={cn(
        "rounded-xl border p-3 text-sm",
        action.status === "pending"
          ? "border-amber-300 bg-amber-50/60 dark:border-amber-800 dark:bg-amber-950/20"
          : "bg-background",
      )}
      data-testid="assistant-action"
    >
      <p className="text-xs font-medium text-muted-foreground">
        {t("status." + action.status)}
      </p>
      <p
        className={cn(
          "mt-1 leading-6",
          action.status === "undone" && "line-through",
        )}
      >
        {action.summary}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {action.status === "pending" && (
          <>
            <Button
              type="button"
              size="sm"
              disabled={busy}
              onClick={() => onDecide("confirm")}
            >
              {t("confirm")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => onDecide("reject")}
            >
              {t("reject")}
            </Button>
          </>
        )}
        {action.undoable && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => onDecide("undo")}
          >
            <Undo2 className="mr-1.5 h-3.5 w-3.5" />
            {t("undo")}
          </Button>
        )}
        {reportId && (
          <Button asChild type="button" size="sm" variant="ghost">
            <Link
              href={`/dashboard/body-styling?report=${encodeURIComponent(reportId)}`}
            >
              {t("openReport")}
            </Link>
          </Button>
        )}
      </div>
    </div>
  );
}
