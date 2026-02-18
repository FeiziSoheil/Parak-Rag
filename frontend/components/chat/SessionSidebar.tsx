"use client";

import { toast } from "sonner";
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
  useSidebar,
} from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  listSessions,
  createSession,
  deleteSession,
  updateSession,
  getCurrentUser,
  getAvatarUrl,
  searchSessionMessages,
  type UserProfile,
  type MessageSearchResult,
  type SessionListItem,
} from "@/lib/api";
import { clearToken } from "@/lib/auth";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useState, useRef } from "react";
import { SquarePen, Trash2, Settings, User, LogOut, Search, Pin, PinOff, MoreHorizontal, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export type SessionItem = SessionListItem;

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
  const [pinningId, setPinningId] = useState<number | null>(null);
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
      setSessions((prev) => {
        const pinned = prev.filter((s) => s.pinned === true);
        const unpinned = prev.filter((s) => !s.pinned);
        return [...pinned, { ...session, pinned: false }, ...unpinned];
      });
      onNewSession(session);
      onSelectSession(session);
      toast.success("New chat created");
    } catch {
      toast.error("Session expired. Please log in again.");
      router.replace("/login");
    }
  }

  handleNewChatRef.current = handleNewChat;
  useEffect(() => {
    const handler = () => handleNewChatRef.current();
    window.addEventListener("rag:new-chat", handler);
    return () => window.removeEventListener("rag:new-chat", handler);
  }, []);

  async function handleTogglePin(e: React.MouseEvent, sessionId: number) {
    e.stopPropagation();
    if (pinningId !== null) return;
    let nextPinned = false;
    setSessions((prev) => {
      const session = prev.find((s) => s.id === sessionId);
      if (!session) return prev;
      nextPinned = !(session.pinned ?? false);
      const updated = prev.map((s, i) =>
        s.id === sessionId ? { ...s, pinned: nextPinned, _idx: i } : { ...s, _idx: i }
      );
      updated.sort((a, b) => {
        const pa = a.pinned ?? false;
        const pb = b.pinned ?? false;
        if (pa !== pb) return pa ? -1 : 1;
        return (a as { _idx: number })._idx - (b as { _idx: number })._idx;
      });
      return updated.map(({ _idx, ...s }) => s);
    });
    setPinningId(sessionId);
    try {
      await updateSession(sessionId, { pinned: nextPinned });
      toast.success(nextPinned ? "جلسه پین شد" : "جلسه از پین خارج شد");
    } catch {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId ? { ...s, pinned: !nextPinned } : { ...s }
        )
      );
      toast.error("خطا در به‌روزرسانی. دوباره تلاش کنید.");
    } finally {
      setPinningId(null);
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
      toast.success("Chat deleted");
    } catch {
      toast.error("Could not delete. Please log in again.");
      router.replace("/login");
    } finally {
      setDeletingId(null);
    }
  }

  function handleLogout() {
    clearToken();
    toast.success("You have been logged out");
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
                          <span className="min-w-0 truncate text-xs font-medium text-sidebar-foreground" title={r.session_title || "Untitled"}>
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
                      className={cn(
                        isActive ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium rounded-md" : undefined,
                        "group-has-data-[sidebar=menu-action]/menu-item:pr-12 md:group-has-data-[sidebar=menu-action]/menu-item:pr-8 pr-10"
                      )}
                    >
                      <span className="min-w-0 truncate flex items-center gap-1.5" title={s.title || "Untitled"}>
                        {(s.pinned ?? false) && <Pin className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />}
                        {s.title || "Untitled"}
                      </span>
                    </SidebarMenuButton>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button
                          type="button"
                          className={cn(
                            "absolute top-1.5 right-1 aspect-square w-5 rounded-md p-0 flex items-center justify-center outline-none transition-transform border-0 shadow-none",
                            "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                            "group-focus-within/menu-item:opacity-100 group-hover/menu-item:opacity-100 aria-expanded:opacity-100 md:opacity-0",
                            "group-data-[collapsible=icon]:hidden",
                            "[&>svg]:size-4 [&>svg]:shrink-0"
                          )}
                          aria-label="گزینه‌های جلسه"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <MoreHorizontal />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent side="right" align="start" className="min-w-36 bg-sidebar text-sidebar-foreground ring-sidebar-border">
                        <DropdownMenuItem
                          onSelect={() => {
                            handleTogglePin({ stopPropagation: () => {} } as React.MouseEvent, s.id);
                          }}
                          disabled={pinningId === s.id}
                          className="focus:bg-sidebar-accent focus:text-sidebar-accent-foreground"
                        >
                          {(s.pinned ?? false) ? (
                            <>
                              <PinOff className="h-4 w-4" />
                              <span>Unpin</span>
                            </>
                          ) : (
                            <>
                              <Pin className="h-4 w-4" />
                              <span>Pin</span>
                            </>
                          )}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          variant="destructive"
                          onSelect={() => {
                            handleDeleteSession({ stopPropagation: () => {} } as React.MouseEvent, s.id);
                          }}
                          disabled={deletingId === s.id}
                          className="focus:bg-sidebar-accent"
                        >
                          <Trash2 className="h-4 w-4" />
                          <span>Delete</span>
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
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
      <SidebarFooter className="border-t border-sidebar-border shrink-0 p-0">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className={cn(
                "w-full p-2 flex items-center gap-3 min-w-0 outline-none",
                "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground transition-colors",
                "group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-2"
              )}
              aria-label="User menu"
            >
              <div className="size-9 shrink-0 rounded-full overflow-hidden bg-sidebar-accent text-sidebar-accent-foreground flex items-center justify-center text-sm font-medium">
                {user?.avatar_url ? (
                  <img src={getAvatarUrl(user.avatar_url) ?? ""} alt="" className="size-full object-cover" />
                ) : (
                  (user?.username ?? "?").charAt(0).toUpperCase()
                )}
              </div>
              <div className="min-w-0 flex-1 text-left group-data-[collapsible=icon]:hidden">
                <p className="text-sm font-medium truncate">
                  {[user?.first_name, user?.last_name].filter(Boolean).join(" ") || (user?.username ?? "…")}
                </p>
                {user?.email && (
                  <p className="text-xs text-muted-foreground truncate">
                    {user.email}
                  </p>
                )}
              </div>
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground group-data-[collapsible=icon]:hidden" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="top" className="w-[var(--radix-dropdown-menu-trigger-width)] min-w-0 bg-background text-foreground border border-muted-foreground/20 shadow-md ring-0">
            <DropdownMenuItem asChild className="focus:bg-muted focus:text-foreground">
              <Link href="/profile" className="flex items-center gap-2">
                <User className="h-4 w-4" />
                Profile
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild className="focus:bg-muted focus:text-foreground">
              <Link href="/settings" className="flex items-center gap-2">
                <Settings className="h-4 w-4" />
                Settings
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem
              variant="destructive"
              onSelect={handleLogout}
              className="cursor-pointer focus:bg-muted focus:text-destructive"
            >
              <LogOut className="h-4 w-4" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarFooter>
    </>
  );
}
