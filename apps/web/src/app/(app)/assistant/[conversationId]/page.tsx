"use client";

import { useParams } from "next/navigation";
import { Suspense } from "react";

import { ChatView } from "@/components/assistant/chat-view";
import { Spinner } from "@/components/common";

/** The conversation id is only known at request time, so it is read inside the Suspense boundary. */
function Conversation() {
  const params = useParams<{ conversationId: string }>();
  return <ChatView key={params.conversationId} initialConversationId={params.conversationId} />;
}

export default function ConversationPage() {
  return (
    <Suspense
      fallback={
        <div className="grid h-[calc(100dvh-7.5rem)] place-items-center md:h-[calc(100dvh-6.5rem)]">
          <Spinner className="size-6" />
        </div>
      }
    >
      <Conversation />
    </Suspense>
  );
}
