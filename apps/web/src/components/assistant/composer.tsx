"use client";

import { ArrowUp, Loader2, LocateFixed, Square } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { VoiceButton } from "@/components/voice/voice-button";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function Composer({
  onSend,
  onStop,
  streaming,
  conversationId,
  locationOn,
  locating,
  onToggleLocation,
  autoFocus,
  placeholder = "Ask Nexora anything…",
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
  conversationId?: string | null;
  locationOn: boolean;
  locating: boolean;
  onToggleLocation: () => void;
  autoFocus?: boolean;
  placeholder?: string;
}) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  function submit() {
    const value = text.trim();
    if (!value || streaming) return;
    onSend(value);
    setText("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="glass focus-within:border-brand/50 focus-within:ring-brand/15 rounded-3xl p-2 shadow-[0_18px_50px_-24px_rgba(124,77,255,0.55)] transition focus-within:ring-4">
      <textarea
        ref={ref}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        rows={1}
        maxLength={8000}
        autoFocus={autoFocus}
        placeholder={placeholder}
        aria-label="Message"
        className="placeholder:text-muted-foreground block max-h-[200px] w-full resize-none bg-transparent px-3 py-2 text-[0.95rem] outline-none"
      />
      <div className="flex items-center gap-1 px-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={onToggleLocation}
              className={cn("rounded-full", locationOn && "bg-brand-soft text-brand hover:bg-brand-soft")}
              aria-pressed={locationOn}
            >
              {locating ? <Loader2 className="animate-spin" /> : <LocateFixed />}
              <span className="hidden sm:inline">{locationOn ? "Location on" : "Location"}</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>Share your location with this message (for nearby places and weather)</TooltipContent>
        </Tooltip>
        <div className="flex-1" />
        <VoiceButton conversationId={conversationId} size="sm" label={false} />
        {streaming ? (
          <Button type="button" size="icon" className="rounded-full" onClick={onStop} aria-label="Stop generating">
            <Square className="size-3.5 fill-current" />
          </Button>
        ) : (
          <Button
            type="button"
            size="icon"
            className="brand-gradient rounded-full text-white"
            onClick={submit}
            disabled={!text.trim()}
            aria-label="Send message"
          >
            <ArrowUp />
          </Button>
        )}
      </div>
    </div>
  );
}
