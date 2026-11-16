"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import { SessionSidebar, type SessionItem } from "@/components/chat/SessionSidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { CartHeaderButton } from "@/components/cart/CartHeaderButton";

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

  // Alt+N (Option+N on Mac): new chat — browser reserves Ctrl+N (new window) and Ctrl+Shift+N (Incognito)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.altKey && e.key.toLowerCase() === "n") {
        e.preventDefault();
        e.stopPropagation();
        window.dispatchEvent(new CustomEvent("rag:new-chat"));
      }
    };
    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, []);

  if (!mounted) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
        Loading…
      </div>
    );
  }

  return (
    <TooltipProvider delayDuration={300}>
      <SidebarProvider className="h-full min-h-0 overflow-hidden bg-transparent">
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

        {/* Clinick-shaped shell: transparent inset + separate topbar/main cards */}
        <SidebarInset className="min-h-0 overflow-hidden bg-transparent p-2 sm:p-3">
          <div className="flex min-h-0 flex-1 flex-col gap-2 sm:gap-3">
            <header className="flex h-12 shrink-0 items-center justify-between gap-2 rounded-xl border border-border/60 bg-card px-3 shadow-modern">
              <div className="flex items-center gap-2 min-w-0">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <SidebarTrigger className="-ml-1" />
                  </TooltipTrigger>
                  <TooltipContent side="right" sideOffset={8}>
                    <p>Toggle sidebar</p>
                    <p className="text-xs text-muted-foreground">Ctrl+B</p>
                    <p className="text-xs text-muted-foreground mt-1">New chat: Alt+N</p>
                  </TooltipContent>
                </Tooltip>
                <span className="text-sm font-medium text-muted-foreground truncate min-w-0">
                  {currentSession?.title || "New Chat"}
                </span>
              </div>
              <CartHeaderButton />
            </header>

            <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-border/60 bg-card shadow-modern">
              <ChatPanel sessionId={currentSession?.id ?? null} />
            </div>
          </div>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  );
}
