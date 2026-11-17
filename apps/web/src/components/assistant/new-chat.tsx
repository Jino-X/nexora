"use client";

import { useSearchParams } from "next/navigation";

import { ChatView } from "@/components/assistant/chat-view";

/** A fresh chat. "New conversation" links add ?new=<ts> so the view remounts with clean state. */
export function NewChat() {
  const params = useSearchParams();
  return <ChatView key={params.get("new") ?? "new"} initialConversationId={null} />;
}
