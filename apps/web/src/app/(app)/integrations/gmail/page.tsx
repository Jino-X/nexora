"use client";

import type { EmailSummary } from "@nexora/shared-types";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Mail, RefreshCw, ShieldCheck } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/common";
import { IntegrationHeader, useIntegration } from "@/components/integrations/integration-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { useIntegrationMutations } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

function GmailInner() {
  const params = useSearchParams();
  const { integration } = useIntegration("gmail");
  const { connectGmail } = useIntegrationMutations();
  const connected = integration?.status === "connected";
  const inbox = useQuery({
    queryKey: ["gmail-unread"],
    queryFn: () => api<EmailSummary[]>("/gmail/messages", { query: { unread: true, limit: 10 } }),
    enabled: connected,
    retry: false,
  });

  useEffect(() => {
    const status = params.get("status");
    if (status === "connected") toast.success("Gmail connected");
    if (status === "error") toast.error(`Gmail connection failed: ${params.get("reason") ?? "unknown error"}`);
  }, [params]);

  async function connect() {
    try {
      const { authorization_url } = await connectGmail.mutateAsync();
      window.location.assign(authorization_url);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't start Google sign-in");
    }
  }

  return (
    <div>
      <IntegrationHeader provider="gmail" icon={<Mail className="size-7" />} />
      <div className="grid gap-4 lg:grid-cols-[1fr_1.3fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <ShieldCheck className="text-brand size-4" /> Permissions
            </CardTitle>
          </CardHeader>
          <CardContent className="text-muted-foreground space-y-3 text-sm">
            <p>
              <span className="text-foreground font-medium">Read</span> (gmail.readonly): list, search and read messages
              so Nexora can summarise them.
            </p>
            <p>
              <span className="text-foreground font-medium">Compose</span> (gmail.compose): create drafts and send them,{" "}
              <em>only after you approve each one</em>.
            </p>
            <p>
              Nexora never deletes email or changes settings. Tokens are encrypted at rest, and disconnecting revokes
              access at Google.
            </p>
            {!connected && (
              <Button onClick={connect} disabled={!integration?.available || connectGmail.isPending} className="mt-2">
                {connectGmail.isPending ? <Loader2 className="animate-spin" /> : <Mail />} Connect Gmail
              </Button>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm">Unread in your inbox</CardTitle>
            {connected && (
              <Button size="icon-sm" variant="ghost" onClick={() => inbox.refetch()} aria-label="Refresh">
                <RefreshCw />
              </Button>
            )}
          </CardHeader>
          <CardContent className="px-0">
            {!connected ? (
              <p className="text-muted-foreground px-4 text-sm">Connect Gmail to preview unread mail here.</p>
            ) : inbox.isPending ? (
              <Skeleton className="mx-4 h-40" />
            ) : inbox.error ? (
              <ErrorState error={inbox.error} className="mx-4" />
            ) : inbox.data?.length === 0 ? (
              <p className="text-muted-foreground px-4 text-sm">Inbox zero. Nothing unread.</p>
            ) : (
              <ul className="divide-y">
                {inbox.data?.map((e) => (
                  <li key={e.id} className="px-4 py-3 text-sm">
                    <p className={cn("truncate", e.unread && "font-semibold")}>{e.subject || "(no subject)"}</p>
                    <p className="text-muted-foreground truncate text-xs">
                      {e.from_} · {e.date}
                    </p>
                    {e.snippet && <p className="text-muted-foreground mt-1 line-clamp-2 text-xs">{e.snippet}</p>}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function GmailPage() {
  return (
    <Suspense>
      <GmailInner />
    </Suspense>
  );
}
