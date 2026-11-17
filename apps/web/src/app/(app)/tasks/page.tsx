"use client";

import { ListChecks, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ApprovalCard } from "@/components/assistant/approval-card";
import { EmptyState, ErrorState, PageHeader, StatusBadge } from "@/components/common";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApprovals, useTasks } from "@/lib/api/hooks";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const FILTERS = ["", "running", "succeeded", "failed", "retrying"];

export default function TasksPage() {
  const [status, setStatus] = useState("");
  const tasks = useTasks(status || undefined);
  const pending = useApprovals("pending");
  const decided = useApprovals();

  return (
    <div>
      <PageHeader
        tone="sky"
        title="Tasks & approvals"
        icon={ListChecks}
        description="Actions Nexora ran for you and actions waiting for your decision."
      />
      <Tabs defaultValue={pending.data?.items.length ? "approvals" : "tasks"}>
        <TabsList>
          <TabsTrigger value="approvals">
            Approvals{pending.data?.items.length ? ` (${pending.data.items.length})` : ""}
          </TabsTrigger>
          <TabsTrigger value="tasks">Task runs</TabsTrigger>
        </TabsList>

        <TabsContent value="approvals" className="mt-4 space-y-6">
          {pending.isPending ? (
            <Skeleton className="h-24" />
          ) : pending.data?.items.length ? (
            <div className="grid gap-3 md:grid-cols-2">
              {pending.data.items.map((a) => (
                <ApprovalCard
                  key={a.id}
                  approvalId={a.id}
                  tool={a.tool_name}
                  summary={a.summary}
                  initialStatus={a.status}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={ShieldCheck}
              tone="emerald"
              title="Nothing waiting"
              description="Emails and messages Nexora prepares appear here for approval before anything is sent."
            />
          )}
          <div>
            <h2 className="text-muted-foreground mb-2 text-sm font-medium">Recent decisions</h2>
            <ul className="divide-y rounded-2xl border">
              {decided.data?.items
                .filter((a) => a.status !== "pending")
                .map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center gap-3 p-3 text-sm">
                    <StatusBadge status={a.status} />
                    <span className="min-w-0 flex-1 truncate">{a.summary}</span>
                    <span className="text-muted-foreground text-xs">
                      {formatDateTime(a.decided_at ?? a.created_at)}
                    </span>
                    {a.conversation_id && (
                      <Link className="text-brand text-xs" href={`/assistant/${a.conversation_id}`}>
                        Chat
                      </Link>
                    )}
                  </li>
                ))}
            </ul>
          </div>
        </TabsContent>

        <TabsContent value="tasks" className="mt-4">
          <div className="mb-3 flex flex-wrap gap-1.5">
            {FILTERS.map((f) => (
              <button
                key={f || "all"}
                type="button"
                onClick={() => setStatus(f)}
                className={cn(
                  "rounded-full border px-3 py-1 text-sm capitalize",
                  status === f ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
                )}
              >
                {f || "All"}
              </button>
            ))}
          </div>
          {tasks.isPending ? (
            <Skeleton className="h-40" />
          ) : tasks.error ? (
            <ErrorState error={tasks.error} />
          ) : tasks.data?.items.length === 0 ? (
            <EmptyState
              icon={ListChecks}
              tone="sky"
              title="No task runs"
              description="Automations and approved actions appear here."
            />
          ) : (
            <div className="overflow-x-auto rounded-2xl border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-muted-foreground text-left text-xs">
                  <tr>
                    <th className="px-4 py-2">Task</th>
                    <th className="px-4 py-2">Status</th>
                    <th className="hidden px-4 py-2 sm:table-cell">Type</th>
                    <th className="px-4 py-2">When</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {tasks.data?.items.map((t) => (
                    <tr key={t.id} className="align-top">
                      <td className="px-4 py-2.5">
                        <p className="font-medium">{t.title || t.kind}</p>
                        {t.error && <p className="text-destructive text-xs">{t.error}</p>}
                        {typeof t.result?.message === "string" && (
                          <p className="text-muted-foreground text-xs">{t.result.message}</p>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusBadge status={t.status} />
                      </td>
                      <td className="text-muted-foreground hidden px-4 py-2.5 capitalize sm:table-cell">{t.kind}</td>
                      <td className="text-muted-foreground px-4 py-2.5 whitespace-nowrap">
                        {formatDateTime(t.finished_at ?? t.started_at ?? t.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
