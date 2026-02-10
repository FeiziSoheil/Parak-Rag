"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import { SessionSidebar, type SessionItem } from "@/components/chat/SessionSidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import {
  SidebarProvider,
  Sidebar,
  SidebarInset,
  SidebarTrigger,
} from "@/components/ui/sidebar";

export default function ChatPage() {
  const router = useRouter();
  const [currentSession, setCurrentSession] = useState<SessionItem | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
  }, [mounted, router]);

  if (!mounted) {
    return (
      <div className="h-screen flex items-center justify-center text-muted-foreground text-sm">
        Loading…
      </div>
    );
  }

  return (
    <SidebarProvider className="h-full min-h-0 overflow-hidden">
      <Sidebar collapsible="icon">
        <SessionSidebar
          currentSessionId={currentSession?.id ?? null}
          onNewSession={setCurrentSession}
          onSelectSession={(session) =>
            setCurrentSession((prev) => (prev?.id === session.id ? prev : session))
          }
          onSessionDeleted={(sessionId) => {
            setCurrentSession((prev) => (prev?.id === sessionId ? null : prev));
          }}
        />
      </Sidebar>
      <SidebarInset className="min-h-0">
        <header className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-border px-3">
          <SidebarTrigger className="-ml-1" />
          <span className="text-sm font-medium text-muted-foreground truncate min-w-0">
            {currentSession?.title || "New Chat"}
          </span>
        </header>
        <main className="flex-1 flex flex-col min-w-0 min-h-0">
          <ChatPanel sessionId={currentSession?.id ?? null} />
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
