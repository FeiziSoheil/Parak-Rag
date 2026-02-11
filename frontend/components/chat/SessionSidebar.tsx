"use client";

import { Button } from "@/components/ui/button";
import {
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuAction,
} from "@/components/ui/sidebar";
import { listSessions, createSession, deleteSession, getCurrentUser, getAvatarUrl, type UserProfile } from "@/lib/api";
import { clearToken } from "@/lib/auth";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Plus, Trash2, Settings, User, LogOut } from "lucide-react";

export type SessionItem = { id: number; title: string; created_at: string };

type Props = {
  currentSessionId: number | null;
  onNewSession: (session: SessionItem) => void;
  onSelectSession: (session: SessionItem) => void;
  onSessionDeleted?: (sessionId: number) => void;
};

export function SessionSidebar({ currentSessionId, onNewSession, onSelectSession, onSessionDeleted }: Props) {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);

  useEffect(() => {
    listSessions()
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  async function handleNewChat() {
    try {
      const session = await createSession("New Chat");
      setSessions((prev) => [session, ...prev]);
      onNewSession(session);
      onSelectSession(session);
    } catch {
      router.replace("/login");
    }
  }

  async function handleDeleteSession(e: React.MouseEvent, sessionId: number) {
    e.stopPropagation();
    if (deletingId !== null) return;
    try {
      setDeletingId(sessionId);
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      onSessionDeleted?.(sessionId);
    } catch {
      router.replace("/login");
    } finally {
      setDeletingId(null);
    }
  }

  function handleLogout() {
    clearToken();
    router.replace("/login");
    router.refresh();
  }

  return (
    <>
      <SidebarHeader className="border-b border-sidebar-border">
        <Link
          href="/chat"
          className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-sidebar-accent hover:text-sidebar-accent-foreground transition-colors min-w-0 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-2 group-data-[collapsible=icon]:[&_span]:hidden"
          aria-label="RAG Chat Home"
        >
          <Image
            src="/favicon.ico"
            alt=""
            width={28}
            height={28}
            className="shrink-0 rounded-md"
          />
          <span className="font-semibold text-sm truncate">RAG Chat</span>
        </Link>
        <Button
          className="w-full rounded-lg group-data-[collapsible=icon]:size-9 group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:shrink-0 group-data-[collapsible=icon]:[&_span]:hidden"
          onClick={handleNewChat}
          disabled={loading}
          title="New Chat"
        >
          <Plus className="h-4 w-4" />
          <span>New Chat</span>
        </Button>
      </SidebarHeader>
      <SidebarContent className="group-data-[collapsible=icon]:hidden">
        <SidebarGroup>
          <SidebarGroupContent>
            {loading ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground px-2 py-3">
                <div className="h-1.5 w-1.5 bg-muted-foreground rounded-full animate-pulse" />
                Loading…
              </div>
            ) : (
              <SidebarMenu>
                {sessions.map((s) => {
                  const isActive = currentSessionId === s.id;
                  return (
                  <SidebarMenuItem key={s.id} className="group/menu-item">
                    <SidebarMenuButton
                      isActive={isActive}
                      onClick={() => onSelectSession(s)}
                      className={isActive ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium rounded-md" : undefined}
                    >
                      <span className="truncate">{s.title || "Untitled"}</span>
                    </SidebarMenuButton>
                    <SidebarMenuAction
                      showOnHover
                      onClick={(e) => handleDeleteSession(e, s.id)}
                      disabled={deletingId === s.id}
                      className="text-muted-foreground/80 hover:bg-sidebar-accent hover:text-destructive/70 focus-visible:opacity-100"
                      aria-label="Delete session"
                    >
                      <Trash2 className="h-4 w-4 text-current" />
                    </SidebarMenuAction>
                  </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            )}
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      {/* Spacer: when sidebar is collapsed, takes remaining space to push footer to bottom */}
      <div className="hidden min-h-0 flex-1 group-data-[collapsible=icon]:block" aria-hidden />
      <SidebarFooter className="border-t border-sidebar-border group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:items-center group-data-[collapsible=icon]:gap-1 group-data-[collapsible=icon]:overflow-hidden shrink-0">
        <div className="p-2 flex items-center gap-3 min-w-0 w-full group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-2">
          <div className="size-9 shrink-0 rounded-full overflow-hidden bg-sidebar-accent text-sidebar-accent-foreground flex items-center justify-center text-sm font-medium">
            {user?.avatar_url ? (
              <img src={getAvatarUrl(user.avatar_url) ?? ""} alt="" className="size-full object-cover" />
            ) : (
              (user?.username ?? "?").charAt(0).toUpperCase()
            )}
          </div>
          <div className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
            <p className="text-sm font-medium truncate">
              {[user?.first_name, user?.last_name].filter(Boolean).join(" ") || (user?.username ?? "…")}
            </p>
            {user?.email && (
              <p className="text-xs text-muted-foreground truncate" title={user.email}>
                {user.email}
              </p>
            )}
          </div>
        </div>
        <SidebarMenu className="w-full group-data-[collapsible=icon]:[&_span]:hidden group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:items-center">
          <SidebarMenuItem>
            <SidebarMenuButton asChild>
              <Link href="/profile">
                <User className="h-4 w-4" />
                <span>Profile</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton asChild>
              <Link href="/settings">
                <Settings className="h-4 w-4" />
                <span>Settings</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={handleLogout}>
              <LogOut className="h-4 w-4" />
              <span>Log out</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </>
  );
}
