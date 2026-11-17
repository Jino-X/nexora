"use client";

import type { ApprovalRequest, Message, ResultCard, RunEvent } from "@nexora/shared-types";
import { useQueryClient } from "@tanstack/react-query";
import { CloudSun, Compass, MessageSquareText, Newspaper, PanelLeft, Sparkles } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Composer } from "@/components/assistant/composer";
import { ConversationList } from "@/components/assistant/conversation-list";
import { MessageBubble, type ToolProgress } from "@/components/assistant/message-bubble";
import { ErrorState, IconTile, Spinner, type Tone } from "@/components/common";
import { Stagger, StaggerItem } from "@/components/fx/motion";
import { Orb3D } from "@/components/fx/orb-3d";
import { TiltCard } from "@/components/fx/tilt-card";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useGeolocation } from "@/hooks/use-geolocation";
import { ApiError } from "@/lib/api/client";
import { qk, useApprovals, useConversation, useMe } from "@/lib/api/hooks";
import { cancelRun, streamRun, type StreamHandle } from "@/lib/api/sse";
import { useToday } from "@/hooks/use-today";

interface StreamingTurn {
  userText: string | null;
  text: string;
  tools: ToolProgress[];
  cards: ResultCard[];
  approvals: ApprovalRequest[];
  status: "streaming" | "complete" | "error" | "cancelled";
  statusText: string | null;
  error: string | null;
  offline: boolean;
  runId: string | null;
}

const SUGGESTIONS: { icon: typeof CloudSun; text: string; tone: Tone }[] = [
  { icon: CloudSun, text: "What's the weather today?", tone: "amber" },
  { icon: Newspaper, text: "Give me today's important AI news", tone: "sky" },
  { icon: Compass, text: "Find a petrol pump near me", tone: "rose" },
  { icon: Sparkles, text: "Remind me to call my client tomorrow at 10am", tone: "violet" },
];

function reduce(turn: StreamingTurn, ev: RunEvent): StreamingTurn {
  switch (ev.event) {
    case "token":
      return { ...turn, text: turn.text + ev.data.text, statusText: null };
    case "status":
      return { ...turn, statusText: ev.data.text };
    case "tool_start":
      return { ...turn, tools: [...turn.tools, { id: ev.data.id, tool: ev.data.tool, status: "running" }] };
    case "tool_end": {
      const exists = turn.tools.some((t) => t.id === ev.data.id);
      const entry: ToolProgress = {
        id: ev.data.id,
        tool: ev.data.tool,
        status: ev.data.ok ? "ok" : "error",
        message: ev.data.message,
      };
      return {
        ...turn,
        tools: exists ? turn.tools.map((t) => (t.id === ev.data.id ? entry : t)) : [...turn.tools, entry],
        cards: ev.data.card ? [...turn.cards, { tool: ev.data.tool, ...ev.data.card } as ResultCard] : turn.cards,
      };
    }
    case "approval_required":
      return { ...turn, approvals: [...turn.approvals, ev.data] };
    case "message_end":
      return { ...turn, status: "complete", offline: ev.data.offline, text: turn.text || ev.data.content };
    case "error":
      return { ...turn, status: "error", error: ev.data.message };
    case "cancelled":
      return { ...turn, status: "cancelled" };
    default:
      return turn;
  }
}

export function ChatView({ initialConversationId }: { initialConversationId: string | null }) {
  const qc = useQueryClient();
  const me = useMe();
  // Becomes set when the first run creates a conversation (the URL is updated without remounting).
  const [conversationId, setConversationId] = useState<string | null>(initialConversationId);
  const conversation = useConversation(conversationId);
  const approvals = useApprovals();
  const [turn, setTurn] = useState<StreamingTurn | null>(null);
  const [locationOn, setLocationOn] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const geo = useGeolocation();
  const handle = useRef<StreamHandle | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const conversationIdRef = useRef(conversationId);
  const streaming = turn?.status === "streaming";

  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  // Pages key this component by conversation, so switching chats remounts with fresh state.
  useEffect(() => () => handle.current?.abort(), []);

  // Prompts handed over from the dashboard (/assistant?prompt=...) are sent once on arrival.
  const searchParams = useSearchParams();
  const handedOff = useRef(false);
  const initialPrompt = searchParams.get("prompt");

  const approvalStatus = useMemo(() => {
    const map = new Map<string, string>();
    approvals.data?.items.forEach((a) => map.set(a.id, a.status));
    return map;
  }, [approvals.data]);

  const messages = useMemo(() => conversation.data?.messages ?? [], [conversation.data]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: streaming ? "auto" : "smooth", block: "end" });
  }, [messages.length, turn?.text, turn?.tools.length, turn?.cards.length, streaming]);

  const send = useCallback(
    async (text: string, opts: { regenerate?: boolean } = {}) => {
      if (handle.current && streaming) return;
      setTurn({
        userText: opts.regenerate ? null : text,
        text: "",
        tools: [],
        cards: [],
        approvals: [],
        status: "streaming",
        statusText: "Thinking…",
        error: null,
        offline: false,
        runId: null,
      });
      const location =
        locationOn && geo.coords ? { latitude: geo.coords.latitude, longitude: geo.coords.longitude } : null;
      const h = streamRun(
        { message: text, conversation_id: conversationId, location, regenerate: opts.regenerate },
        (ev) => {
          if (ev.event === "run_started") {
            setTurn((t) => (t ? { ...t, runId: ev.data.run_id } : t));
            if (ev.data.created_conversation) {
              conversationIdRef.current = ev.data.conversation_id;
              setConversationId(ev.data.conversation_id);
              window.history.replaceState(null, "", `/assistant/${ev.data.conversation_id}`);
              qc.invalidateQueries({ queryKey: ["conversations"] });
            }
            return;
          }
          setTurn((t) => (t ? reduce(t, ev) : t));
        },
      );
      handle.current = h;
      try {
        await h.done;
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.code === "rate_limited"
              ? "You're sending messages too quickly. Wait a moment."
              : err.message
            : "Something went wrong.";
        setTurn((t) => (t ? { ...t, status: "error", error: message } : t));
        if (!(err instanceof ApiError && err.status === 0 && err.code === "stream_interrupted")) toast.error(message);
      } finally {
        handle.current = null;
        const convId = conversationIdRef.current;
        if (convId) await qc.invalidateQueries({ queryKey: qk.conversation(convId) });
        qc.invalidateQueries({ queryKey: ["conversations"] });
        qc.invalidateQueries({ queryKey: ["approvals"] });
        // Once a run started, the API persisted this turn (even failures and cancellations), so the
        // refetched messages replace the live view. Failures before the run started stay visible.
        setTurn((t) => (t && (t.runId || t.status === "complete") ? null : t));
      }
    },
    [conversationId, geo.coords, locationOn, qc, streaming],
  );

  useEffect(() => {
    if (!initialPrompt || handedOff.current || conversationId) return;
    handedOff.current = true;
    window.history.replaceState(null, "", "/assistant");
    void send(initialPrompt);
  }, [initialPrompt, conversationId, send]);

  const stop = useCallback(async () => {
    const runId = turn?.runId;
    if (runId) await cancelRun(runId).catch(() => undefined);
    else handle.current?.abort();
  }, [turn?.runId]);

  const retry = useCallback(() => void send("", { regenerate: true }), [send]);

  const toggleLocation = useCallback(() => {
    if (geo.status === "denied") {
      toast.error("Location permission was denied. Allow it in your browser settings.");
      return;
    }
    if (!locationOn && !geo.coords) geo.request();
    setLocationOn((v) => !v);
  }, [geo, locationOn]);

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const showEmpty = !conversationId && !turn;
  const name = me.data?.profile.display_name;
  const today = useToday();

  const bubble = (m: Message) => (
    <MessageBubble
      key={m.id}
      role={m.role === "user" ? "user" : "assistant"}
      content={m.content}
      createdAt={m.created_at}
      status={m.status}
      channel={m.channel}
      cards={m.meta.cards ?? []}
      offline={m.meta.offline}
      tools={(m.tool_calls ?? [])
        .filter((t) => t.status !== "approval_required")
        .map((t) => ({
          id: t.id,
          tool: t.tool,
          status: t.status === "ok" ? "ok" : "error",
          message: t.message ?? t.reason,
        }))}
      approvals={(m.meta.approvals ?? []).map((a) => ({ ...a, status: approvalStatus.get(a.approval_id) }))}
      errorText={m.status === "error" ? "This response failed." : null}
      onRetry={m.id === lastAssistant?.id && !streaming ? retry : undefined}
    />
  );

  return (
    <div className="flex h-[calc(100dvh-7.5rem)] gap-4 md:h-[calc(100dvh-6.5rem)]">
      <aside className="glass hidden w-72 shrink-0 rounded-3xl p-4 lg:block">
        <ConversationList activeId={conversationId} />
      </aside>
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 py-3 lg:hidden">
          <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
            <SheetTrigger asChild>
              <Button variant="outline" size="sm">
                <PanelLeft /> Chats
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-80 p-4">
              <SheetHeader className="p-0 pb-3">
                <SheetTitle>Conversations</SheetTitle>
              </SheetHeader>
              <ConversationList activeId={conversationId} onNavigate={() => setHistoryOpen(false)} />
            </SheetContent>
          </Sheet>
          <p className="truncate text-sm font-medium">{conversation.data?.conversation.title ?? "New conversation"}</p>
        </div>

        <div className="flex-1 scrollbar-thin overflow-y-auto py-4" aria-live="polite">
          {showEmpty ? (
            <div className="mx-auto flex min-h-full max-w-2xl flex-col items-center justify-center py-6 text-center">
              <Orb3D mood={streaming ? "thinking" : "idle"} className="w-44 sm:w-52" />
              <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
                {today?.greeting ?? "Hello"}
                {name ? (
                  <>
                    , <span className="text-shimmer">{name}</span>
                  </>
                ) : null}
              </h1>
              <p className="text-muted-foreground mt-2">How can I help? Type below, or tap the mic to talk.</p>
              <Stagger className="mt-8 grid w-full gap-3 sm:grid-cols-2" delay={0.15}>
                {SUGGESTIONS.map((s) => (
                  <StaggerItem key={s.text}>
                    <TiltCard
                      as="button"
                      onClick={() => void send(s.text)}
                      max={6}
                      className="glass flex w-full items-center gap-3 rounded-2xl p-3.5 text-left text-sm"
                    >
                      <IconTile icon={s.icon} tone={s.tone} size="sm" />
                      <span className="font-medium">{s.text}</span>
                    </TiltCard>
                  </StaggerItem>
                ))}
              </Stagger>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-6">
              {conversation.isPending && conversationId && <Spinner className="mx-auto" />}
              {conversation.error && <ErrorState error={conversation.error} onRetry={() => conversation.refetch()} />}
              {messages.map(bubble)}
              {turn?.userText && <MessageBubble role="user" content={turn.userText} />}
              {turn && (
                <MessageBubble
                  role="assistant"
                  content={turn.text}
                  status={turn.status}
                  tools={turn.tools}
                  cards={turn.cards}
                  approvals={turn.approvals}
                  offline={turn.offline}
                  statusText={turn.statusText}
                  errorText={turn.error}
                  onRetry={turn.status === "error" || turn.status === "cancelled" ? retry : undefined}
                />
              )}
              {!messages.length && !turn && conversation.data && (
                <div className="text-muted-foreground py-12 text-center text-sm">
                  <MessageSquareText className="mx-auto mb-2 size-6" /> No messages yet.
                </div>
              )}
              <div ref={bottom} />
            </div>
          )}
        </div>

        <div className="mx-auto w-full max-w-3xl pb-2">
          <Composer
            onSend={(t) => void send(t)}
            onStop={() => void stop()}
            streaming={streaming}
            conversationId={conversationId}
            locationOn={locationOn && Boolean(geo.coords)}
            locating={geo.status === "locating"}
            onToggleLocation={toggleLocation}
            autoFocus
          />
          <p className="text-muted-foreground mt-2 text-center text-[0.7rem]">
            Nexora can make mistakes. Sensitive actions always ask for your approval.
          </p>
        </div>
      </section>
    </div>
  );
}
