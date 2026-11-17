"use client";

import { ChevronRight, CloudSun, Mail, MapPin, MessageCircle, Music, Newspaper, Plug, MonitorPlay } from "lucide-react";
import Link from "next/link";

import { ErrorState, IconTile, PageHeader, StatusBadge, type Tone } from "@/components/common";
import { Skeleton } from "@/components/ui/skeleton";
import { useIntegrations } from "@/lib/api/hooks";

const ICONS: Record<string, typeof Mail> = {
  gmail: Mail,
  whatsapp: MessageCircle,
  youtube: MonitorPlay,
  music: Music,
  weather: CloudSun,
  maps: MapPin,
  news: Newspaper,
};

const DETAIL_PAGES = new Set(["gmail", "whatsapp", "youtube", "music"]);

const PROVIDER_TONES: Record<string, Tone> = {
  gmail: "rose",
  whatsapp: "emerald",
  youtube: "rose",
  music: "pink",
  weather: "amber",
  maps: "cyan",
  news: "sky",
};

export default function IntegrationsPage() {
  const integrations = useIntegrations();
  const groups = [
    {
      title: "Your accounts",
      kind: "per_user" as const,
      note: "Connected with your own credentials. Tokens are encrypted, and you can disconnect any time.",
    },
    {
      title: "Built-in services",
      kind: "server" as const,
      note: "Provided by this Nexora server through official APIs and open data.",
    },
  ];

  return (
    <div>
      <PageHeader
        tone="lime"
        title="Integrations"
        icon={Plug}
        description="Services Nexora can use on your behalf, and exactly what each one can do."
      />
      {integrations.error && <ErrorState error={integrations.error} onRetry={() => integrations.refetch()} />}
      <div className="space-y-8">
        {groups.map((g) => (
          <section key={g.kind}>
            <h2 className="text-sm font-semibold">{g.title}</h2>
            <p className="text-muted-foreground mb-3 text-xs">{g.note}</p>
            <div className="grid gap-3 sm:grid-cols-2">
              {integrations.isPending
                ? Array.from({ length: 2 }, (_, i) => <Skeleton key={i} className="h-24" />)
                : integrations.data
                    ?.filter((i) => i.kind === g.kind)
                    .map((i) => {
                      const Icon = ICONS[i.provider] ?? Plug;
                      const body = (
                        <div className="glass hover:border-brand/40 flex h-full items-start gap-3 rounded-2xl p-4 transition-colors">
                          <IconTile icon={Icon} tone={PROVIDER_TONES[i.provider] ?? "violet"} size="lg" />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between gap-2">
                              <p className="font-medium">{i.name}</p>
                              <StatusBadge status={i.status} />
                            </div>
                            <p className="text-muted-foreground mt-1 text-sm">{i.description}</p>
                            {i.account_label && <p className="mt-1 truncate text-xs">{i.account_label}</p>}
                            {!i.available && i.setup_hint && (
                              <p className="text-warning mt-1 text-xs">{i.setup_hint}</p>
                            )}
                          </div>
                          {DETAIL_PAGES.has(i.provider) && (
                            <ChevronRight className="text-muted-foreground size-4 self-center" />
                          )}
                        </div>
                      );
                      return DETAIL_PAGES.has(i.provider) ? (
                        <Link key={i.provider} href={`/integrations/${i.provider}`}>
                          {body}
                        </Link>
                      ) : (
                        <div key={i.provider}>{body}</div>
                      );
                    })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
