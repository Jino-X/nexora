import { defaultFilter } from "cmdk";

/** Value prefix of the palette's free-text "Ask Nexora …" item. */
export const ASK_VALUE_PREFIX = "nexora-ask:";

/**
 * cmdk's default ranking, except the free-text "Ask Nexora" item (which matches any query) ranks last, so Enter on
 * "vault" opens the Vault page and only asks the assistant when nothing else matches.
 */
export function paletteFilter(value: string, search: string, keywords?: string[]): number {
  if (value.startsWith(ASK_VALUE_PREFIX)) return search.trim() ? 0.001 : 0;
  return defaultFilter(value, search, keywords);
}
