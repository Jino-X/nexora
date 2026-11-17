"use client";

import { Archive, History, MessageSquare, Mic, Search, Workflow } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState } from "react";

import { EmptyState, ErrorState, IconTile, PageHeader, StatusBadge, type Tone } from "@/components/common";
import { Stagger, StaggerItem } from "@/components/fx/motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useConversations, useUpdateConversation, useVoiceSessions } from "@/lib/api/hooks";
import { formatDateTime, timeAgo } from "@/lib/format";

const CHANNEL_ICON = { text: MessageSquare, voice: Mic, automation: Workflow } as const;
const CHANNEL_TONE: Record<string, Tone> = { text: "violet", voice: "pink", automation: "amber" };

export default function HistoryPage() {
  const [q, setQ] = useState("");
  const deferred = useDeferredValue(q);
  const conversations = useConversations(deferred || undefined, 100);
  const voice = useVoiceSessions();
  const archive = useUpdateConversation();

  return (
    <div>
      <PageHeader
        tone="violet"
        title="History"
        icon={History}
        description="Every conversation and voice session, searchable."
      />
      <Tabs defaultValue="conversations">
        <TabsList>
          <TabsTrigger value="conversations">Conversations</TabsTrigger>
          <TabsTrigger value="voice">Voice sessions</TabsTrigger>
        </TabsList>
        <TabsContent value="conversations" className="mt-4">
          <div className="relative mb-3 max-w-sm">
            <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by title" className="pl-8" />
          </div>
          {conversations.isPending ? (
            <Skeleton className="h-48" />
          ) : conversations.error ? (
            <ErrorState error={conversations.error} />
          ) : conversations.data?.items.length === 0 ? (
            <EmptyState
              icon={MessageSquare}
              title={deferred ? "No matching conversations" : "No conversations yet"}
              description={deferred ? "Try a different word." : "Chats with Nexora show up here."}
            />
          ) : (
            <Stagger as="ul" className="space-y-2">
              {conversations.data?.items.map((c) => {
                const Icon = CHANNEL_ICON[c.channel] ?? MessageSquare;
                return (
                  <StaggerItem
                    as="li"
                    key={c.id}
                    className="glass group flex items-center gap-3 rounded-2xl p-3 transition-all hover:-translate-y-0.5 hover:shadow-[var(--shadow-glow)]"
                  >
                    <IconTile icon={Icon} tone={CHANNEL_TONE[c.channel] ?? "violet"} />
                    <Link href={`/assistant/${c.id}`} className="min-w-0 flex-1">
                      <p className="group-hover:text-brand truncate font-medium transition-colors">{c.title}</p>
                      <p className="text-muted-foreground text-xs">
                        {formatDateTime(c.created_at)} · active {timeAgo(c.last_message_at)}
                      </p>
                    </Link>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      aria-label="Archive"
                      onClick={() => archive.mutate({ id: c.id, archived: true })}
                    >
                      <Archive />
                    </Button>
                  </StaggerItem>
                );
              })}
            </Stagger>
          )}
        </TabsContent>
        <TabsContent value="voice" className="mt-4">
          {voice.isPending ? (
            <Skeleton className="h-40" />
          ) : voice.data?.items.length === 0 ? (
            <EmptyState
              icon={Mic}
              tone="pink"
              title="No voice sessions yet"
              description="Tap the mic or say “Hey Nexora” to start one."
            />
          ) : (
            <Stagger as="ul" className="space-y-2">
              {voice.data?.items.map((s) => (
                <StaggerItem
                  as="li"
                  key={s.id}
                  className="glass flex flex-wrap items-center gap-3 rounded-2xl p-3 text-sm"
                >
                  <IconTile icon={Mic} tone="pink" size="sm" />
                  <span className="font-medium">{formatDateTime(s.created_at)}</span>
                  <StatusBadge status={s.status} />
                  <span className="text-muted-foreground">
                    {s.activation === "wake_word" ? "Wake word" : "Push to talk"} · {s.turn_count} turn(s)
                    {s.end_reason && ` · ended: ${s.end_reason}`}
                  </span>
                  {s.conversation_id && (
                    <Link className="text-brand ml-auto" href={`/assistant/${s.conversation_id}`}>
                      Transcript
                    </Link>
                  )}
                </StaggerItem>
              ))}
            </Stagger>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
