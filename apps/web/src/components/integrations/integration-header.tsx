"use client";

import type { IntegrationStatus } from "@nexora/shared-types";
import { ArrowLeft, Info, Loader2, Unplug, Wrench } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { StatusBadge } from "@/components/common";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useIntegrationMutations, useIntegrations } from "@/lib/api/hooks";
import { formatDateTime } from "@/lib/format";

export function useIntegration(provider: string): { integration: IntegrationStatus | undefined; isPending: boolean } {
  const q = useIntegrations();
  return { integration: q.data?.find((i) => i.provider === provider), isPending: q.isPending };
}

export function IntegrationHeader({
  provider,
  icon,
  children,
}: {
  provider: string;
  icon: ReactNode;
  children?: ReactNode;
}) {
  const { integration } = useIntegration(provider);
  const { disconnect } = useIntegrationMutations();

  return (
    <div className="mb-6">
      <Link
        href="/integrations"
        className="text-muted-foreground hover:text-foreground mb-4 inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" /> Integrations
      </Link>
      <div className="glass gradient-border flex flex-col gap-4 rounded-3xl p-5 sm:flex-row sm:items-center">
        <span className="brand-gradient animate-float grid size-16 shrink-0 place-items-center rounded-3xl text-white shadow-[0_12px_30px_-10px_rgba(124,77,255,0.6)]">
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold">{integration?.name ?? provider}</h1>
            {integration && <StatusBadge status={integration.status} />}
          </div>
          <p className="text-muted-foreground mt-0.5 text-sm">{integration?.description}</p>
          {integration?.account_label && (
            <p className="mt-1 text-sm">
              Connected as <span className="font-medium">{integration.account_label}</span>
              {integration.connected_at && (
                <span className="text-muted-foreground"> · since {formatDateTime(integration.connected_at)}</span>
              )}
            </p>
          )}
        </div>
        {integration?.kind === "per_user" && (integration.status === "connected" || integration.status === "error") && (
          <Button variant="outline" onClick={() => disconnect.mutate(provider)} disabled={disconnect.isPending}>
            {disconnect.isPending ? <Loader2 className="animate-spin" /> : <Unplug />} Disconnect
          </Button>
        )}
      </div>
      {integration?.last_error && (
        <Alert variant="destructive" className="mt-3">
          <Info />
          <AlertTitle>Needs attention</AlertTitle>
          <AlertDescription>{integration.last_error}</AlertDescription>
        </Alert>
      )}
      {integration && !integration.available && (
        <Alert className="mt-3">
          <Wrench />
          <AlertTitle>Not configured on this server</AlertTitle>
          <AlertDescription>{integration.setup_hint} See docs/integrations.md for setup steps.</AlertDescription>
        </Alert>
      )}
      {integration && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {integration.scopes.map((s) => (
            <Badge key={s} variant="outline" className="font-mono text-[0.7rem]">
              {s.replace("https://www.googleapis.com/auth/", "")}
            </Badge>
          ))}
          {integration.tools.map((t) => (
            <Badge key={t} variant="secondary" className="text-[0.7rem]">
              tool: {t}
            </Badge>
          ))}
        </div>
      )}
      {children}
    </div>
  );
}
