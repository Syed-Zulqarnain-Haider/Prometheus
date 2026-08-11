import type { Metadata } from "next";

import { ChatClient } from "@/components/chat/chat-client";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Chat - Prometheus" };

export default function ChatPage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Chat"
        description="Message anyone on the team. Green dot = active now; admins can review all conversations."
      />
      <ChatClient />
    </div>
  );
}
