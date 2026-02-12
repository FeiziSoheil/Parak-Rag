"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  useSidebar,
} from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  listSessions,
  createSession,
  deleteSession,
  getCurrentUser,
  getAvatarUrl,
  searchSessionMessages,
  type UserProfile,
  type MessageSearchResult,
} from "@/lib/api";
import { clearToken } from "@/lib/auth";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useState, useRef } from "react";
import { SquarePen, Trash2, Settings, User, LogOut, Search } from "lucide-react";

export type SessionItem = { id: number; title: string; created_at: string };

type Props = {
  currentSessionId: number | null;
  onNewSession: (session: SessionItem) => void;
  onSelectSession: (session: SessionItem) => void;
  onSessionDeleted?: (sessionId: number) => void;
};

export function SessionSidebar({ currentSessionId, onNewSession, onSelectSession, onSessionDeleted }: Props) {
  const router = useRouter();
  const { setOpen } = useSidebar();
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<MessageSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleNewChatRef = useRef<() => void>(() => {});

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

  useEffect(() => {
    const q = searchQuery.trim();
    if (!q) {
      setSearchResults([]);
      setSearchLoading(false);
      return;
    }
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(() => {
      setSearchLoading(true);
      searchSessionMessages(q)
        .then(setSearchResults)
        .catch(() => setSearchResults([]))
        .finally(() => setSearchLoading(false));
    }, 300);
    return () => {
      if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    };
  }, [searchQuery]);

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

  handleNewChatRef.current = handleNewChat;
  useEffect(() => {
    const handler = () => handleNewChatRef.current();
    window.addEventListener("rag:new-chat", handler);
    return () => window.removeEventListener("rag:new-chat", handler);
  }, []);

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

  function handleSearchResultClick(result: MessageSearchResult) {
    const session =
      sessions.find((s) => s.id === result.session_id) ||
      ({ id: result.session_id, title: result.session_title, created_at: "" } as SessionItem);
    onSelectSession(session);
    setSearchQuery("");
  }

  const showSearchResults = searchQuery.trim().length > 0;

  return (
    <>
      <SidebarHeader className="shrink-0 border-b border-sidebar-border flex flex-col gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              href="/chat"
              className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-sidebar-accent hover:text-sidebar-accent-foreground transition-colors min-w-0 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-2 group-data-[collapsible=icon]:[&_span]:hidden"
              aria-label="PARAK - دستیار هوشمند"
            >
              <Image
                src="/favicon.ico"
                alt=""
                width={28}
                height={28}
                className="shrink-0 rounded-md"
              />
              <span className="font-semibold text-sm truncate">PARAK</span>
            </Link>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={8}>
            <p>PARAK (پَرَک) — دستیار هوشمند</p>
          </TooltipContent>
        </Tooltip>
        <div className="flex gap-1 w-full group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:gap-1 group-data-[collapsible=icon]:w-auto">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                className="flex-1 rounded-lg group-data-[collapsible=icon]:size-9 group-data-[collapsible=icon]:min-w-9 group-data-[collapsible=icon]:flex-none group-data-[collapsible=icon]:p-0 group-data-[collapsible=icon]:shrink-0 group-data-[collapsible=icon]:[&_span]:hidden group-data-[collapsible=icon]:items-center gap-2 group-data-[collapsible=icon]:justify-center"
                onClick={handleNewChat}
                disabled={loading}
              >
                <SquarePen className="h-4 w-4 shrink-0" />
                <span>New Chat</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={8}>
              <p>New Chat</p>
              <p className="text-xs text-muted-foreground">Alt+N</p>
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                className="hidden group-data-[collapsible=icon]:flex size-9 min-w-9 shrink-0 rounded-lg items-center justify-center p-0 bg-transparent hover:bg-sidebar-accent hover:text-sidebar-accent-foreground shadow-none text-sidebar-foreground"
                onClick={() => setOpen(true)}
                aria-label="Search in sessions"
              >
                <Search className="h-4 w-4 shrink-0" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={8}>
              <p>Search in sessions</p>
            </TooltipContent>
          </Tooltip>
        </div>
      </SidebarHeader>
      <SidebarContent className="group-data-[collapsible=icon]:hidden">
        <div className="sticky top-0 z-10 shrink-0 p-2 border-b border-sidebar-border bg-sidebar">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              type="search"
              placeholder="Search…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 h-9 bg-sidebar-accent/50 border-sidebar-border"
              aria-label="Search in sessions"
            />
          </div>
        </div>
        <SidebarGroup>
          <SidebarGroupContent>
            {showSearchResults ? (
              <>
                {searchLoading ? (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground px-2 py-3">
                    <div className="h-1.5 w-1.5 bg-muted-foreground rounded-full animate-pulse" />
                    در حال جستجو…
                  </div>
                ) : searchResults.length === 0 ? (
                  <div className="text-xs text-muted-foreground px-2 py-3">
                    نتیجه‌ای یافت نشد.
                  </div>
                ) : (
                  <SidebarMenu className="flex flex-col gap-1">
                    {searchResults.map((r) => (
                      <SidebarMenuItem key={`${r.session_id}-${r.message_id}`} className="min-h-0">
                        <SidebarMenuButton
                          isActive={currentSessionId === r.session_id}
                          onClick={() => handleSearchResultClick(r)}
                          className="h-auto min-h-[4.25rem] flex flex-col items-stretch gap-1 py-2.5 text-left rounded-md [&>span:last-child]:line-clamp-2 [&>span:last-child]:whitespace-normal [&>span:last-child]:break-words"
                        >
                          <span className="truncate text-xs font-medium text-sidebar-foreground shrink-0">
                            {r.session_title || "Untitled"}
                          </span>
                          <span className="text-xs text-muted-foreground overflow-hidden">
                            {r.content_snippet}
                          </span>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    ))}
                  </SidebarMenu>
                )}
              </>
            ) : loading ? (
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
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <SidebarMenuAction
                          showOnHover
                          onClick={(e) => handleDeleteSession(e, s.id)}
                          disabled={deletingId === s.id}
                          className="text-muted-foreground/80 hover:bg-sidebar-accent hover:text-destructive/70 focus-visible:opacity-100"
                          aria-label="Delete session"
                        >
                          <Trash2 className="h-4 w-4 text-current" />
                        </SidebarMenuAction>
                      </TooltipTrigger>
                      <TooltipContent side="right" sideOffset={8}>
                        <p>Delete session</p>
                      </TooltipContent>
                    </Tooltip>
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
              <Tooltip>
                <TooltipTrigger asChild>
                  <p className="text-xs text-muted-foreground truncate cursor-default">
                    {user.email}
                  </p>
                </TooltipTrigger>
                <TooltipContent side="top">
                  <p>{user.email}</p>
                </TooltipContent>
              </Tooltip>
            )}
          </div>
        </div>
        <SidebarMenu className="w-full group-data-[collapsible=icon]:[&_span]:hidden group-data-[collapsible=icon]:flex group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:items-center">
          <SidebarMenuItem>
            <Tooltip>
              <TooltipTrigger asChild>
                <SidebarMenuButton asChild>
                  <Link href="/profile">
                    <User className="h-4 w-4" />
                    <span>Profile</span>
                  </Link>
                </SidebarMenuButton>
              </TooltipTrigger>
              <TooltipContent side="right" sideOffset={8}>
                <p>Profile</p>
              </TooltipContent>
            </Tooltip>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <Tooltip>
              <TooltipTrigger asChild>
                <SidebarMenuButton asChild>
                  <Link href="/settings">
                    <Settings className="h-4 w-4" />
                    <span>Settings</span>
                  </Link>
                </SidebarMenuButton>
              </TooltipTrigger>
              <TooltipContent side="right" sideOffset={8}>
                <p>Settings</p>
              </TooltipContent>
            </Tooltip>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <Tooltip>
              <TooltipTrigger asChild>
                <SidebarMenuButton onClick={handleLogout}>
                  <LogOut className="h-4 w-4" />
                  <span>Log out</span>
                </SidebarMenuButton>
              </TooltipTrigger>
              <TooltipContent side="right" sideOffset={8}>
                <p>Log out</p>
              </TooltipContent>
            </Tooltip>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </>
  );
}
