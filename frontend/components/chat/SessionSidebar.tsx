"use client";

import { toast } from "sonner";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInput,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
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
import { SquarePen, Trash2, Settings, User, LogOut, Search, Pin, PinOff, MoreHorizontal, ChevronsUpDown } from "lucide-react";

export type SessionItem = SessionListItem;

type Props = {
  currentSessionId: number | null;
  onNewSession: (session: SessionItem) => void;
  onSelectSession: (session: SessionItem) => void;
  onSessionDeleted?: (sessionId: number) => void;
};

export function SessionSidebar({ currentSessionId, onNewSession, onSelectSession, onSessionDeleted }: Props) {
  const router = useRouter();
  const { setOpen, isMobile, setOpenMobile } = useSidebar();
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

  function selectSession(session: SessionItem) {
    onSelectSession(session);
    if (isMobile) setOpenMobile(false);
  }

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
      selectSession(session);
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
    selectSession(session);
    setSearchQuery("");
  }

  const showSearchResults = searchQuery.trim().length > 0;

  return (
    <Sidebar collapsible="icon" variant="floating">
      <SidebarHeader className="border-b border-sidebar-border">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild tooltip="PARAK (پَرَک) — دستیار هوشمند">
              <Link href="/chat" aria-label="PARAK - دستیار هوشمند">
                <Image
                  src="/favicon.ico"
                  alt=""
                  width={28}
                  height={28}
                  className="shrink-0 rounded-md"
                />
                <span className="font-semibold text-sm truncate">PARAK</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip={{
                children: (
                  <>
                    <p>New Chat</p>
                    <p className="text-xs text-muted-foreground">Alt+N</p>
                  </>
                ),
              }}
              onClick={handleNewChat}
              disabled={loading}
            >
              <SquarePen />
              <span>New Chat</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem className="hidden group-data-[collapsible=icon]:block">
            <SidebarMenuButton
              tooltip="Search in sessions"
              onClick={() => setOpen(true)}
              aria-label="Search in sessions"
            >
              <Search />
              <span>Search</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent className="group-data-[collapsible=icon]:hidden">
        <SidebarGroup className="sticky top-0 z-10 bg-sidebar border-b border-sidebar-border py-2">
          <SidebarGroupContent>
            <form
              onSubmit={(e) => e.preventDefault()}
              className="relative"
            >
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <SidebarInput
                type="search"
                placeholder="Search…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 h-9 bg-sidebar-accent/50"
                aria-label="Search in sessions"
              />
            </form>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>
            {showSearchResults ? "Search results" : "Chats"}
          </SidebarGroupLabel>
          <SidebarGroupContent>
            {showSearchResults ? (
              <>
                {searchLoading ? (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground px-2 py-3">
                    <div className="size-1.5 bg-muted-foreground rounded-full animate-pulse" />
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
                          className="h-auto min-h-[4.25rem] flex flex-col items-stretch gap-1 py-2.5 text-left [&>span:last-child]:line-clamp-2 [&>span:last-child]:whitespace-normal [&>span:last-child]:break-words"
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
                <div className="size-1.5 bg-muted-foreground rounded-full animate-pulse" />
                Loading…
              </div>
            ) : (
              <SidebarMenu>
                {sessions.map((s) => {
                  const isActive = currentSessionId === s.id;
                  return (
                    <SidebarMenuItem key={s.id}>
                      <SidebarMenuButton
                        isActive={isActive}
                        onClick={() => selectSession(s)}
                        tooltip={s.title || "Untitled"}
                      >
                        {(s.pinned ?? false) && (
                          <Pin className="text-muted-foreground" aria-hidden />
                        )}
                        <span className="min-w-0 truncate" title={s.title || "Untitled"}>
                          {s.title || "Untitled"}
                        </span>
                      </SidebarMenuButton>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <SidebarMenuAction
                            showOnHover
                            aria-label="گزینه‌های جلسه"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <MoreHorizontal />
                            <span className="sr-only">More</span>
                          </SidebarMenuAction>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent
                          side="right"
                          align="start"
                          className="min-w-36 bg-sidebar text-sidebar-foreground ring-sidebar-border"
                        >
                          <DropdownMenuItem
                            onSelect={() => {
                              handleTogglePin({ stopPropagation: () => {} } as React.MouseEvent, s.id);
                            }}
                            disabled={pinningId === s.id}
                            className="focus:bg-sidebar-accent focus:text-sidebar-accent-foreground"
                          >
                            {(s.pinned ?? false) ? (
                              <>
                                <PinOff />
                                <span>Unpin</span>
                              </>
                            ) : (
                              <>
                                <Pin />
                                <span>Pin</span>
                              </>
                            )}
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={() => {
                              handleDeleteSession({ stopPropagation: () => {} } as React.MouseEvent, s.id);
                            }}
                            disabled={deletingId === s.id}
                            className="text-destructive focus:bg-sidebar-accent focus:text-destructive"
                          >
                            <Trash2 />
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

      {/* Spacer: when collapsed to icons, push footer to bottom */}
      <div className="hidden min-h-0 flex-1 group-data-[collapsible=icon]:block" aria-hidden />

      <SidebarFooter className="border-t border-sidebar-border">
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              {/* No tooltip: TooltipTrigger wrapping breaks DropdownMenuTrigger asChild. */}
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                >
                  <div className="size-8 shrink-0 rounded-lg overflow-hidden bg-sidebar-accent text-sidebar-accent-foreground flex items-center justify-center text-sm font-medium">
                    {user?.avatar_url ? (
                      <img src={getAvatarUrl(user.avatar_url) ?? ""} alt="" className="size-full object-cover" />
                    ) : (
                      (user?.username ?? "?").charAt(0).toUpperCase()
                    )}
                  </div>
                  <div className="min-w-0 flex-1 text-left grid leading-tight">
                    <span className="truncate text-sm font-semibold">
                      {[user?.first_name, user?.last_name].filter(Boolean).join(" ") || (user?.username ?? "…")}
                    </span>
                    {user?.email && (
                      <span className="truncate text-xs text-muted-foreground">
                        {user.email}
                      </span>
                    )}
                  </div>
                  <ChevronsUpDown className="ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="min-w-56 rounded-lg"
                side="bottom"
                align="end"
                sideOffset={4}
              >
                <DropdownMenuLabel className="p-0 font-normal">
                  <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                    <div className="size-8 shrink-0 rounded-lg overflow-hidden bg-muted text-foreground flex items-center justify-center text-sm font-medium">
                      {user?.avatar_url ? (
                        <img src={getAvatarUrl(user.avatar_url) ?? ""} alt="" className="size-full object-cover" />
                      ) : (
                        (user?.username ?? "?").charAt(0).toUpperCase()
                      )}
                    </div>
                    <div className="grid flex-1 text-sm leading-tight">
                      <span className="truncate font-semibold">
                        {[user?.first_name, user?.last_name].filter(Boolean).join(" ") || (user?.username ?? "…")}
                      </span>
                      {user?.email && (
                        <span className="truncate text-xs text-muted-foreground">
                          {user.email}
                        </span>
                      )}
                    </div>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <Link href="/profile" className="flex items-center gap-2">
                    <User />
                    Profile
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href="/settings" className="flex items-center gap-2">
                    <Settings />
                    Settings
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={handleLogout}
                  className="cursor-pointer text-destructive focus:text-destructive"
                >
                  <LogOut />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
