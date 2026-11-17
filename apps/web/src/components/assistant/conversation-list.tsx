"use client";

import { Mic, MoreHorizontal, Plus, Search, Trash2, Workflow } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Spinner } from "@/components/common";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { useConversations, useDeleteConversation } from "@/lib/api/hooks";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ConversationList({ activeId, onNavigate }: { activeId?: string | null; onNavigate?: () => void }) {
  const [q, setQ] = useState("");
  const list = useConversations(q || undefined, 50);
  const remove = useDeleteConversation();
  const router = useRouter();

  return (
    <div className="flex h-full flex-col">
      <Button
        className="mb-3 w-full justify-start"
        variant="outline"
        onClick={() => {
          onNavigate?.();
          router.push(`/assistant?new=${Date.now()}`);
        }}
      >
        <Plus /> New conversation
      </Button>
      <div className="relative mb-3">
        <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search chats" className="pl-8" />
      </div>
      <div className="-mx-1 flex-1 scrollbar-thin space-y-0.5 overflow-y-auto px-1">
        {list.isPending && <Spinner className="mx-auto mt-6" />}
        {list.data?.items.length === 0 && (
          <p className="text-muted-foreground px-2 py-6 text-center text-sm">No conversations yet.</p>
        )}
        {list.data?.items.map((c) => (
          <div
            key={c.id}
            className={cn(
              "group flex items-center rounded-lg pr-1 text-sm",
              c.id === activeId ? "bg-accent text-accent-foreground" : "hover:bg-muted",
            )}
          >
            <Link href={`/assistant/${c.id}`} onClick={onNavigate} className="min-w-0 flex-1 px-3 py-2">
              <span className="flex items-center gap-1.5 truncate">
                {c.channel === "voice" && <Mic className="text-muted-foreground size-3.5 shrink-0" />}
                {c.channel === "automation" && <Workflow className="text-muted-foreground size-3.5 shrink-0" />}
                <span className="truncate">{c.title}</span>
              </span>
              <span className="text-muted-foreground block text-[0.7rem]">{timeAgo(c.last_message_at)}</span>
            </Link>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  size="icon-xs"
                  variant="ghost"
                  className="opacity-60 group-hover:opacity-100"
                  aria-label="Conversation actions"
                >
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  variant="destructive"
                  onClick={async () => {
                    await remove.mutateAsync(c.id);
                    if (c.id === activeId) router.push("/assistant");
                  }}
                >
                  <Trash2 /> Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ))}
      </div>
    </div>
  );
}
