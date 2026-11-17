"use client";

import { ExternalLink, Newspaper, Search } from "lucide-react";
import { useDeferredValue, useState } from "react";

import { EmptyState, ErrorState, PageHeader } from "@/components/common";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useNews } from "@/lib/api/hooks";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const CATEGORIES = [
  { id: "", label: "For you" },
  { id: "ai", label: "AI" },
  { id: "technology", label: "Technology" },
  { id: "world", label: "World" },
  { id: "india", label: "India" },
  { id: "business", label: "Business" },
  { id: "science", label: "Science" },
];

export default function NewsPage() {
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const deferred = useDeferredValue(query);
  const news = useNews(category || undefined, deferred || undefined, 40);

  return (
    <div>
      <PageHeader
        tone="sky"
        title="News & AI updates"
        icon={Newspaper}
        description="Headlines from publishers' RSS feeds, de-duplicated and linked to the original source."
      />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex scrollbar-thin gap-1.5 overflow-x-auto">
          {CATEGORIES.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setCategory(c.id)}
              className={cn(
                "shrink-0 rounded-full border px-3.5 py-1.5 text-sm transition-colors",
                category === c.id ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
              )}
            >
              {c.label}
            </button>
          ))}
        </div>
        <div className="relative sm:ml-auto sm:w-64">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter headlines"
            className="pl-8"
          />
        </div>
      </div>
      {news.isPending ? (
        <div className="grid gap-3 md:grid-cols-2">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : news.error ? (
        <ErrorState error={news.error} onRetry={() => news.refetch()} />
      ) : news.data?.length === 0 ? (
        <EmptyState
          icon={Newspaper}
          title="No headlines"
          description="Try another category, or check that the feeds are reachable."
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {news.data?.map((n) => (
            <a
              key={n.id}
              href={n.link}
              target="_blank"
              rel="noreferrer"
              className="group glass hover:border-brand/40 flex gap-4 rounded-2xl p-4 transition-all hover:-translate-y-0.5"
            >
              {n.image_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={n.image_url}
                  alt=""
                  loading="lazy"
                  className="hidden size-20 shrink-0 rounded-xl object-cover sm:block"
                />
              )}
              <div className="min-w-0">
                <p className="text-muted-foreground text-xs">
                  <span className="text-foreground font-medium">{n.source}</span>
                  {n.published_at && ` · ${timeAgo(n.published_at)}`}
                  <span className="bg-muted ml-1.5 rounded-full px-1.5 py-0.5 capitalize">
                    {n.category === "ai" ? "AI" : n.category}
                  </span>
                </p>
                <p className="mt-1 line-clamp-2 font-medium group-hover:underline">{n.title}</p>
                {n.summary && <p className="text-muted-foreground mt-1 line-clamp-2 text-sm">{n.summary}</p>}
              </div>
              <ExternalLink className="text-muted-foreground size-4 shrink-0" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
