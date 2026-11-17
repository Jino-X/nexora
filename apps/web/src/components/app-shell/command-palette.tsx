"use client";

import { CloudSun, Fuel, Moon, Newspaper, Sparkles, Sun, Wand2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { NAV } from "@/components/app-shell/nav";
import { ASK_VALUE_PREFIX, paletteFilter } from "@/components/app-shell/palette-filter";
import { IconTile } from "@/components/common";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";

const PROMPTS = [
  { text: "What's the weather today?", icon: CloudSun },
  { text: "Give me today's important AI news", icon: Newspaper },
  { text: "Find a petrol pump near me", icon: Fuel },
  { text: "Give me my daily briefing", icon: Sparkles },
];

/** ⌘K palette: jump anywhere, or hand any text straight to the assistant. */
export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const [query, setQuery] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  function go(href: string) {
    onOpenChange(false);
    setQuery("");
    router.push(href);
  }

  function ask(text: string) {
    go(`/assistant?prompt=${encodeURIComponent(text)}`);
  }

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Command palette" description="Search or ask Nexora">
      {/* CommandDialog is only the dialog shell; cmdk's parts need a <Command> root for their shared store. */}
      <Command filter={paletteFilter}>
        <CommandInput placeholder="Search pages or ask Nexora anything…" value={query} onValueChange={setQuery} />
        <CommandList className="max-h-[60vh] scrollbar-thin">
          <CommandEmpty>
            <button type="button" onClick={() => ask(query)} className="text-brand mx-auto flex items-center gap-2">
              <Wand2 className="size-4" /> Ask Nexora “{query}”
            </button>
          </CommandEmpty>
          <CommandGroup heading="Go to">
            {NAV.map((item) => (
              <CommandItem key={item.href} value={item.label} onSelect={() => go(item.href)}>
                <IconTile icon={item.icon} tone={item.tone} size="sm" className="size-7 rounded-lg" />
                {item.label}
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandSeparator />
          <CommandGroup heading="Try asking">
            {PROMPTS.map((p) => (
              <CommandItem key={p.text} value={p.text} onSelect={() => ask(p.text)}>
                <p.icon className="text-brand" />
                {p.text}
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandSeparator />
          <CommandGroup heading="Appearance">
            <CommandItem
              value="toggle theme dark light"
              onSelect={() => {
                setTheme(resolvedTheme === "dark" ? "light" : "dark");
                onOpenChange(false);
              }}
            >
              {resolvedTheme === "dark" ? <Sun /> : <Moon />}
              Switch to {resolvedTheme === "dark" ? "light" : "dark"} theme
            </CommandItem>
          </CommandGroup>
          {/* Last on purpose: cmdk selects the first visible item, so Enter on "vault" opens the Vault page and only
              asks the assistant when nothing else matches (paletteFilter also ranks this item last). */}
          {query.trim() && (
            <CommandGroup heading="Assistant">
              <CommandItem value={`${ASK_VALUE_PREFIX}${query}`} onSelect={() => ask(query)}>
                <IconTile icon={Wand2} tone="pink" size="sm" className="size-7 rounded-lg" />
                Ask Nexora “{query}”<CommandShortcut>↵</CommandShortcut>
              </CommandItem>
            </CommandGroup>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
