"use client";

import { Check, Loader2, ShieldAlert, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useApprovalDecision } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

const TOOL_TITLES: Record<string, string> = {
  gmail_send_email: "Send email",
  gmail_create_draft: "Save email draft",
  whatsapp_send_message: "Send WhatsApp message",
};

export function ApprovalCard({
  approvalId,
  tool,
  summary,
  initialStatus = "pending",
}: {
  approvalId: string;
  tool: string;
  summary: string;
  initialStatus?: string;
}) {
  const decide = useApprovalDecision();
  const [status, setStatus] = useState(initialStatus);
  const [pending, setPending] = useState<"approve" | "reject" | null>(null);

  async function act(approve: boolean) {
    setPending(approve ? "approve" : "reject");
    try {
      const result = await decide.mutateAsync({ id: approvalId, approve });
      setStatus(result.status);
      if (result.status === "failed") toast.error(result.result.message ?? "The action failed");
      else if (approve) toast.success(result.result.message ?? "Done");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't record your decision");
    } finally {
      setPending(null);
    }
  }

  const decided = status !== "pending";
  return (
    <div
      className={cn("rounded-2xl border p-4", decided ? "bg-muted/40" : "border-warning/50 bg-warning/5 shadow-sm")}
      role="group"
      aria-label="Approval required"
    >
      <div className="flex items-start gap-3">
        <ShieldAlert className={cn("mt-0.5 size-5 shrink-0", decided ? "text-muted-foreground" : "text-warning")} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{TOOL_TITLES[tool] ?? tool.replace(/_/g, " ")}</p>
          <p className="text-muted-foreground mt-1 text-sm break-words whitespace-pre-wrap">{summary}</p>
          {decided ? (
            <p className="mt-3 text-sm font-medium capitalize">
              {status === "executed" ? "✓ Approved and completed" : status}
            </p>
          ) : (
            <div className="mt-3 flex gap-2">
              <Button size="sm" onClick={() => act(true)} disabled={pending !== null}>
                {pending === "approve" ? <Loader2 className="animate-spin" /> : <Check />} Approve
              </Button>
              <Button size="sm" variant="outline" onClick={() => act(false)} disabled={pending !== null}>
                {pending === "reject" ? <Loader2 className="animate-spin" /> : <X />} Decline
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
