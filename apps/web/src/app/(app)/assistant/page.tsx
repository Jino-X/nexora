import type { Metadata } from "next";
import { Suspense } from "react";

import { NewChat } from "@/components/assistant/new-chat";

export const metadata: Metadata = { title: "Assistant" };

export default function AssistantPage() {
  return (
    <Suspense>
      <NewChat />
    </Suspense>
  );
}
