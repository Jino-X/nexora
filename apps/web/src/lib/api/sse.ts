/**
 * Assistant run streaming over SSE using fetch (EventSource cannot send Authorization headers).
 * If the connection drops before `done`, the stream resumes from the last event id with
 * GET /assistant/runs/{id}/events?after=N, so no tokens are lost.
 */

import type { RunEvent } from "@nexora/shared-types";

import { ApiError, authHeaders, buildUrl, toApiError } from "@/lib/api/client";

export interface ParsedEvent {
  id: number | null;
  event: string;
  data: unknown;
}

/** Incremental SSE parser: feed raw text chunks, get complete events back. */
export class SSEParser {
  private buffer = "";

  feed(chunk: string): ParsedEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const events: ParsedEvent[] = [];
    let index: number;
    while ((index = this.buffer.indexOf("\n\n")) !== -1) {
      const block = this.buffer.slice(0, index);
      this.buffer = this.buffer.slice(index + 2);
      let id: number | null = null;
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (!line || line.startsWith(":")) continue;
        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
        if (field === "id") id = Number.parseInt(value, 10);
        else if (field === "event") event = value;
        else if (field === "data") data.push(value);
      }
      if (data.length === 0) continue;
      let parsed: unknown = data.join("\n");
      try {
        parsed = JSON.parse(parsed as string);
      } catch {
        /* keep raw string */
      }
      events.push({ id, event, data: parsed });
    }
    return events;
  }
}

export interface StartRunInput {
  message: string;
  conversation_id?: string | null;
  location?: { latitude: number; longitude: number; label?: string | null } | null;
  language?: "auto" | "en" | "ta" | null;
  regenerate?: boolean;
}

export interface StreamHandle {
  runId: () => string | null;
  done: Promise<void>;
  abort: () => void;
}

const MAX_RESUMES = 4;

export function streamRun(input: StartRunInput, onEvent: (event: RunEvent) => void): StreamHandle {
  const controller = new AbortController();
  let runId: string | null = null;
  let lastSeq = 0;
  let finished = false;

  async function consume(res: Response) {
    if (!res.ok || !res.body) throw await toApiError(res);
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    const parser = new SSEParser();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const ev of parser.feed(value)) {
        if (ev.id !== null && Number.isFinite(ev.id)) lastSeq = ev.id;
        if (ev.event === "run_started") runId = (ev.data as { run_id: string }).run_id;
        if (ev.event === "done") finished = true;
        onEvent({ event: ev.event, data: ev.data } as RunEvent);
      }
    }
  }

  const done = (async () => {
    const res = await fetch(buildUrl("/assistant/runs"), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...(await authHeaders()) },
      body: JSON.stringify(input),
      signal: controller.signal,
    });
    try {
      await consume(res);
    } catch (error) {
      if (controller.signal.aborted || error instanceof ApiError) throw error;
    }
    for (let attempt = 1; !finished && runId && attempt <= MAX_RESUMES; attempt++) {
      if (controller.signal.aborted) return;
      await new Promise((r) => setTimeout(r, 500 * 2 ** (attempt - 1)));
      try {
        const resumed = await fetch(buildUrl(`/assistant/runs/${runId}/events`, { after: lastSeq }), {
          headers: { Accept: "text/event-stream", ...(await authHeaders()) },
          signal: controller.signal,
        });
        await consume(resumed);
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 404) break;
      }
    }
    if (!finished && !controller.signal.aborted) {
      throw new ApiError(
        0,
        "stream_interrupted",
        "The connection dropped. Your answer may still be saved, so refresh.",
      );
    }
  })();

  return { runId: () => runId, done, abort: () => controller.abort() };
}

export async function cancelRun(runId: string): Promise<void> {
  await fetch(buildUrl(`/assistant/runs/${runId}/cancel`), { method: "POST", headers: await authHeaders() });
}
