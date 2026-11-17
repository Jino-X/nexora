import { describe, expect, it } from "vitest";

import { ASK_VALUE_PREFIX, paletteFilter } from "@/components/app-shell/palette-filter";

describe("command palette ranking", () => {
  it("ranks real matches above the free-text 'Ask Nexora' item", () => {
    const ask = paletteFilter(`${ASK_VALUE_PREFIX}vault`, "vault");
    expect(paletteFilter("Vault", "vault")).toBeGreaterThan(ask);
    expect(paletteFilter("Memory", "memo")).toBeGreaterThan(paletteFilter(`${ASK_VALUE_PREFIX}memo`, "memo"));
  });

  it("keeps 'Ask Nexora' visible when nothing else matches, hidden for an empty query", () => {
    expect(paletteFilter("Vault", "what is the time")).toBe(0);
    expect(paletteFilter(`${ASK_VALUE_PREFIX}what is the time`, "what is the time")).toBeGreaterThan(0);
    expect(paletteFilter(`${ASK_VALUE_PREFIX}`, "  ")).toBe(0);
  });
});
