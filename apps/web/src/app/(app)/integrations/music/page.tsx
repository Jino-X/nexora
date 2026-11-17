"use client";

import { Loader2, Music, Search } from "lucide-react";
import { useState, type FormEvent } from "react";

import { MusicList } from "@/components/assistant/result-cards";
import { ErrorState } from "@/components/common";
import { IntegrationHeader } from "@/components/integrations/integration-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useMusicSearch } from "@/lib/api/hooks";

const MOODS = ["Relaxing", "Focus", "Tamil melodies", "A. R. Rahman", "Lo-fi", "Carnatic"];

export default function MusicPage() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const results = useMusicSearch(query);

  function submit(e: FormEvent) {
    e.preventDefault();
    setQuery(input.trim());
  }

  return (
    <div>
      <IntegrationHeader provider="music" icon={<Music className="size-7" />} />
      <p className="text-muted-foreground mb-4 text-xs">
        Results come from official catalogues: Spotify embeds when configured, otherwise Apple Music links with
        30-second previews. Nexora never downloads or re-hosts music.
      </p>
      <form onSubmit={submit} className="mb-3 flex gap-2">
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Song, artist or mood" />
        <Button type="submit" disabled={!input.trim()}>
          {results.isFetching ? <Loader2 className="animate-spin" /> : <Search />} Search
        </Button>
      </form>
      <div className="mb-5 flex flex-wrap gap-1.5">
        {MOODS.map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => {
              setInput(m);
              setQuery(m);
            }}
            className="hover:bg-muted rounded-full border px-3 py-1 text-sm"
          >
            {m}
          </button>
        ))}
      </div>
      {results.error && <ErrorState error={results.error} />}
      {results.data && (
        <Card className="overflow-hidden p-0">
          {results.data.length ? (
            <MusicList items={results.data} />
          ) : (
            <p className="text-muted-foreground p-6 text-center text-sm">No results.</p>
          )}
        </Card>
      )}
    </div>
  );
}
