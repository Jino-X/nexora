import { describe, expect, it } from "vitest";

import { SSEParser } from "@/lib/api/sse";

describe("SSEParser", () => {
  it("parses complete events with ids and JSON data", () => {
    const p = new SSEParser();
    const events = p.feed('id: 1\nevent: token\ndata: {"text":"Hel"}\n\nid: 2\nevent: token\ndata: {"text":"lo"}\n\n');
    expect(events).toEqual([
      { id: 1, event: "token", data: { text: "Hel" } },
      { id: 2, event: "token", data: { text: "lo" } },
    ]);
  });

  it("buffers events split across chunks (including inside UTF-8 text)", () => {
    const p = new SSEParser();
    expect(p.feed('id: 7\nevent: message_end\ndata: {"content":"வணக்')).toEqual([]);
    expect(p.feed('கம்"}\n')).toEqual([]);
    expect(p.feed("\n")).toEqual([{ id: 7, event: "message_end", data: { content: "வணக்கம்" } }]);
  });

  it("ignores comments, keep-alives and retry fields", () => {
    const p = new SSEParser();
    expect(p.feed("retry: 2000\n\n: keep-alive\n\n")).toEqual([]);
    expect(p.feed("event: done\ndata: {}\n\n")).toEqual([{ id: null, event: "done", data: {} }]);
  });

  it("normalizes CRLF line endings", () => {
    const p = new SSEParser();
    expect(p.feed('event: status\r\ndata: {"text":"x"}\r\n\r\n')).toEqual([
      { id: null, event: "status", data: { text: "x" } },
    ]);
  });
});
