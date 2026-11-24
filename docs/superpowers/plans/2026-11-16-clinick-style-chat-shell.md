# Clinick-style Chat Shell + User Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the RAG chat shell match Clinick’s floating three-surface layout and fix the sidebar footer user menu so it opens.

**Architecture:** Keep Radix dropdowns. Add `forwardRef` to sidebar menu primitives used as `DropdownMenuTrigger asChild` children. Restructure `chat/page.tsx` so `SidebarInset` is a padded transparent column containing separate topbar and main cards (Clinick `AppShell` shape). Align footer menu UX with Clinick’s `Sidebar` footer.

**Tech Stack:** Next.js App Router, React, shadcn Sidebar (Radix), Radix Dropdown Menu, existing RAG design tokens (`card`, `shadow-modern`, muted canvas).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-11-16-clinick-style-chat-shell-design.md`
- No Base UI migration
- Do not change session search / pin / delete / Alt+N behavior
- Do not commit unless the user explicitly asks
- Reuse RAG tokens; do not import Clinick mint brand palette

---

### Task 1: forwardRef on sidebar menu trigger primitives

**Files:**
- Modify: `frontend/components/ui/sidebar.tsx` (`SidebarMenuButton`, `SidebarMenuAction`)

**Interfaces:**
- Consumes: existing `sidebarMenuButtonVariants`, `Slot`, `Tooltip` wrappers
- Produces: `SidebarMenuButton` and `SidebarMenuAction` that forward refs to the underlying DOM/`Slot` element so Radix `asChild` works

- [x] **Step 1: Convert `SidebarMenuButton` to `React.forwardRef`**

Replace the current function with a `forwardRef` that passes `ref` to `Comp`:

```tsx
const SidebarMenuButton = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<"button"> & {
    asChild?: boolean
    isActive?: boolean
    tooltip?: string | React.ComponentProps<typeof TooltipContent>
  } & VariantProps<typeof sidebarMenuButtonVariants>
>(function SidebarMenuButton(
  {
    asChild = false,
    isActive = false,
    variant = "default",
    size = "default",
    tooltip,
    className,
    ...props
  },
  ref
) {
  const Comp = asChild ? Slot : "button"
  const { isMobile, state } = useSidebar()

  const button = (
    <Comp
      ref={ref}
      data-slot="sidebar-menu-button"
      data-sidebar="menu-button"
      data-size={size}
      data-active={isActive}
      className={cn(sidebarMenuButtonVariants({ variant, size }), className)}
      {...props}
    />
  )

  if (!tooltip) {
    return button
  }

  if (typeof tooltip === "string") {
    tooltip = { children: tooltip }
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent
        side="right"
        align="center"
        hidden={state !== "collapsed" || isMobile}
        {...tooltip}
      />
    </Tooltip>
  )
})
SidebarMenuButton.displayName = "SidebarMenuButton"
```

- [x] **Step 2: Convert `SidebarMenuAction` to `React.forwardRef`**

Same pattern: `forwardRef` + `ref={ref}` on `Comp` (needed for session `⋯` dropdown triggers).

- [x] **Step 3: Verify TypeScript still exports these symbols**

Run: `cd frontend && npx tsc --noEmit -p . 2>&1 | head -40`  
Expected: no new errors on `sidebar.tsx` (existing unrelated errors OK).

---

### Task 2: Clinick-style footer user menu

**Files:**
- Modify: `frontend/components/chat/SessionSidebar.tsx` (footer block ~387–447)

**Interfaces:**
- Consumes: `SidebarMenuButton` with working ref forwarding; Radix `DropdownMenu*`
- Produces: Footer menu that opens on click with Profile / Settings / Log out

- [x] **Step 1: Update imports**

Replace `ChevronDown` with `ChevronsUpDown`. Import `DropdownMenuLabel`, `DropdownMenuSeparator` if not already imported.

- [x] **Step 2: Replace footer `DropdownMenu` with Clinick-shaped Radix menu**

Keep `DropdownMenuTrigger asChild` → `SidebarMenuButton` **without** `tooltip`. Use:

```tsx
<DropdownMenuContent
  className="min-w-56 rounded-lg"
  side="bottom"
  align="end"
  sideOffset={4}
>
  <DropdownMenuLabel className="p-0 font-normal">
    {/* avatar + name + email row, same as trigger content */}
  </DropdownMenuLabel>
  <DropdownMenuSeparator />
  <DropdownMenuItem asChild>
    <Link href="/profile">… Profile</Link>
  </DropdownMenuItem>
  <DropdownMenuItem asChild>
    <Link href="/settings">… Settings</Link>
  </DropdownMenuItem>
  <DropdownMenuItem
    onSelect={handleLogout}
    className="cursor-pointer text-destructive focus:text-destructive"
  >
    <LogOut />
    Log out
  </DropdownMenuItem>
</DropdownMenuContent>
```

Remove invalid `variant="destructive"` (not supported by RAG’s `DropdownMenuItem`).

- [ ] **Step 3: Manual verify** (needs logged-in session)

Open `/chat`, click footer user button → menu opens with three items; pin `⋯` menus still open.

---

### Task 3: Clinick-shaped shell in chat page

**Files:**
- Modify: `frontend/app/(dashboard)/chat/page.tsx`
- Modify: `frontend/components/ui/sidebar.tsx` (`SidebarInset` floating styles)
- Touch only if needed: `frontend/app/(dashboard)/chat/layout.tsx` (keep canvas; no structural change)

**Interfaces:**
- Consumes: `SessionSidebar`, `SidebarProvider`, `SidebarInset`, `SidebarTrigger`, `ChatPanel`
- Produces: Three floating surfaces — sidebar / topbar card / main card

- [x] **Step 1: Neutralize `SidebarInset` auto-card for floating**

In `SidebarInset`, remove the `md:peer-data-[variant=floating]:…` card chrome classes so inset stays a transparent flex column (Clinick pattern). Keep inset styling for `variant=inset` only.

- [x] **Step 2: Restructure `page.tsx`**

```tsx
<TooltipProvider delayDuration={300}>
  <SidebarProvider className="h-full min-h-0 overflow-hidden bg-transparent">
    <SessionSidebar … />
    <SidebarInset className="min-h-0 overflow-hidden bg-transparent p-2 sm:p-3">
      <div className="flex min-h-0 flex-1 flex-col gap-2 sm:gap-3">
        <header className="flex h-12 shrink-0 items-center … rounded-xl border … bg-card shadow-modern">
          <SidebarTrigger … />
          <span>{currentSession?.title || "New Chat"}</span>
        </header>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border … bg-card shadow-modern">
          <ChatPanel sessionId={currentSession?.id ?? null} />
        </div>
      </div>
    </SidebarInset>
  </SidebarProvider>
</TooltipProvider>
```

Remove the extra outer `flex … gap` wrapper that previously padded beside the sidebar; let shadcn gap + inset padding own spacing (like Clinick).

- [ ] **Step 3: Visual verify**

Desktop: background visible around three rounded surfaces; collapse icon mode works.  
Mobile: drawer + floating topbar/main.  
User menu + session menus still open.

---

## Spec coverage

| Spec item | Task |
|-----------|------|
| Floating shell like Clinick | Task 3 |
| Working user footer menu | Tasks 1–2 |
| No Base UI migration | All |
| Keep session features | Task 2/3 do not touch list logic |
| RAG tokens only | Task 3 classes |
