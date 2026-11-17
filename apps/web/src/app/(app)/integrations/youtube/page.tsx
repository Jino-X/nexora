"use client";

import { Loader2, Search, MonitorPlay } from "lucide-react";
import { useState, type FormEvent } from "react";

import { YouTubeGrid } from "@/components/assistant/result-cards";
import { ErrorState } from "@/components/common";
import { IntegrationHeader, useIntegration } from "@/components/integrations/integration-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useYouTubeSearch } from "@/lib/api/hooks";

export default function YouTubePage() {
  const { integration } = useIntegration("youtube");
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("video");
  const results = useYouTubeSearch(query, kind);

  function submit(e: FormEvent) {
    e.preventDefault();
    setQuery(input.trim());
  }

  return (
    <div>
      <IntegrationHeader provider="youtube" icon={<MonitorPlay className="size-7" />} />
      <p className="text-muted-foreground mb-4 text-xs">
        Uses the official YouTube Data API and embedded player. Each search costs 100 quota units of the project&apos;s
        daily 10,000, so results are cached for an hour.
      </p>
      <form onSubmit={submit} className="mb-5 flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="React tutorials, Ilaiyaraaja live…"
          disabled={!integration?.available}
        />
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger className="w-32" aria-label="Type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="video">Videos</SelectItem>
            <SelectItem value="channel">Channels</SelectItem>
            <SelectItem value="playlist">Playlists</SelectItem>
          </SelectContent>
        </Select>
        <Button type="submit" disabled={!input.trim() || !integration?.available}>
          {results.isFetching ? <Loader2 className="animate-spin" /> : <Search />} Search
        </Button>
      </form>
      {results.error && <ErrorState error={results.error} />}
      {results.data && (
        <div className="-mx-3">
          <YouTubeGrid items={results.data} />
        </div>
      )}
    </div>
  );
}
