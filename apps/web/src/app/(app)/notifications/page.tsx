"use client";

import { Bell, BellRing, CheckCheck, Plug, ShieldAlert, Workflow } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

const noopSubscribe = () => () => {};

import { EmptyState, ErrorState, IconTile, PageHeader, type Tone } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarkRead, useNotifications } from "@/lib/api/hooks";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const NOTE_TONES: Record<string, Tone> = {
  reminder: "pink",
  approval: "amber",
  automation: "violet",
  integration: "emerald",
};

const ICONS: Record<string, typeof Bell> = {
  reminder: BellRing,
  approval: ShieldAlert,
  automation: Workflow,
  integration: Plug,
};

/** Shows browser notifications for new items while the app is open (opt-in). */
function useBrowserNotifications(
  items: { id: string; title: string; body: string; read_at: string | null }[] | undefined,
) {
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!items) return;
    if (seen.current === null) {
      seen.current = new Set(items.map((i) => i.id));
      return;
    }
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    for (const item of items) {
      if (!seen.current.has(item.id) && !item.read_at) new Notification(item.title, { body: item.body, tag: item.id });
      seen.current.add(item.id);
    }
  }, [items]);
}

export default function NotificationsPage() {
  const [unreadOnly, setUnreadOnly] = useState(false);
  const notes = useNotifications(unreadOnly);
  const markRead = useMarkRead();
  const browserPermission = useSyncExternalStore(
    noopSubscribe,
    () => (typeof Notification === "undefined" ? "unsupported" : Notification.permission),
    () => "unsupported",
  );
  const [requested, setPermission] = useState<string | null>(null);
  const permission = requested ?? browserPermission;
  useBrowserNotifications(notes.data?.items);

  return (
    <div>
      <PageHeader
        tone="pink"
        title="Notifications"
        icon={Bell}
        description="Reminders, automation results, approvals and integration events."
        actions={
          <>
            {permission === "default" && (
              <Button variant="outline" onClick={async () => setPermission(await Notification.requestPermission())}>
                <BellRing /> Enable browser alerts
              </Button>
            )}
            <Button variant="outline" onClick={() => markRead.mutate(undefined)}>
              <CheckCheck /> Mark all read
            </Button>
          </>
        }
      />
      <p className="text-muted-foreground mb-4 text-xs">
        Browser alerts appear while Nexora is open in a tab. Background push notifications (Web Push) are not set up
        yet.
      </p>
      <div className="mb-3 flex gap-1.5">
        {[false, true].map((u) => (
          <button
            key={String(u)}
            type="button"
            onClick={() => setUnreadOnly(u)}
            className={cn(
              "rounded-full border px-3 py-1 text-sm",
              unreadOnly === u ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
            )}
          >
            {u ? "Unread" : "All"}
          </button>
        ))}
      </div>
      {notes.isPending ? (
        <Skeleton className="h-48" />
      ) : notes.error ? (
        <ErrorState error={notes.error} onRetry={() => notes.refetch()} />
      ) : notes.data?.items.length === 0 ? (
        <EmptyState
          icon={Bell}
          tone="pink"
          title="You are all caught up"
          description="Reminders, automation results and approvals show up here."
        />
      ) : (
        <ul className="glass divide-y overflow-hidden rounded-2xl">
          {notes.data?.items.map((n) => {
            const Icon = ICONS[n.kind] ?? Bell;
            const href =
              typeof n.data.conversation_id === "string"
                ? `/assistant/${n.data.conversation_id}`
                : n.kind === "approval"
                  ? "/tasks"
                  : typeof n.data.automation_id === "string"
                    ? "/automations"
                    : null;
            return (
              <li key={n.id} className={cn("flex gap-3 p-4", !n.read_at && "bg-brand-soft/40")}>
                <IconTile
                  icon={Icon}
                  tone={NOTE_TONES[n.kind] ?? "violet"}
                  size="sm"
                  className={cn(n.read_at && "opacity-60")}
                />
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{n.title}</p>
                  {n.body && <p className="text-muted-foreground mt-0.5 text-sm whitespace-pre-wrap">{n.body}</p>}
                  <p className="text-muted-foreground mt-1 text-xs">
                    {timeAgo(n.created_at)}
                    {href && (
                      <>
                        {" · "}
                        <Link href={href} className="text-brand">
                          Open
                        </Link>
                      </>
                    )}
                  </p>
                </div>
                {!n.read_at && (
                  <Button size="sm" variant="ghost" onClick={() => markRead.mutate([n.id])}>
                    Mark read
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
