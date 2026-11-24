# Clinick-style chat shell + user menu (Approach A)

**Date:** 2026-11-16  
**Status:** Draft for review  
**Reference:** `/home/soheil/My/Code1Sprint/projects/Clinick/FrontEnd` (`AppShell`, `shared/Sidebar`)  
**Scope choice:** Option 2 — floating shell appearance + working user footer menu (Clinick behavior), without migrating the whole UI kit to Base UI.

## Goal

Make the RAG chat dashboard shell feel like Clinick’s floating staff panel, and fix the sidebar footer user menu so it opens reliably (Profile / Settings / Log out).

## Non-goals

- Full migration of `dropdown-menu` / `sidebar` to Base UI (`render` prop API)
- Changing chat session list features (search, pin, delete, Alt+N)
- Porting Clinick brand colors / mint halos as a new brand system (reuse existing RAG tokens: `card`, `shadow-modern`, muted canvas)

## Current problems

1. User footer menu does not open. RAG uses Radix `DropdownMenuTrigger asChild` around `SidebarMenuButton`, but `SidebarMenuButton` does not `forwardRef`, so Radix cannot attach ref/focus correctly (Clinick avoids this via Base UI `render={<SidebarMenuButton />}`).
2. Shell composition differs from Clinick: padding/gap wrapping is custom; Clinick puts padding on `SidebarInset` and nests topbar + content as separate rounded cards.

## Design

### 1. Shell layout (Clinick-shaped, RAG tokens)

```
Viewport background (existing chat layout: muted + mesh/grain)
└─ TooltipProvider
   └─ SidebarProvider (transparent / full height)
      ├─ SessionSidebar (Sidebar variant="floating" collapsible="icon")
      └─ SidebarInset (flex column, p-2/p-3, bg-transparent)
         ├─ Header card (rounded-xl/2xl, bg-card, shadow, ring/border)
         │    SidebarTrigger + session title
         └─ Main card (rounded-xl/2xl, bg-card, shadow, flex-1 min-h-0)
              ChatPanel
```

Match Clinick’s separation of three surfaces (sidebar / topbar / content) with existing RAG visual tokens. Keep mobile Sheet drawer behavior from shadcn Sidebar.

### 2. User menu (Clinick UX on Radix)

- Footer trigger: avatar, name, secondary line (email), `ChevronsUpDown`
- `DropdownMenuContent`: `side="bottom"` (mobile/desktop as Clinick), `align="end"`, `sideOffset={4}`
- Optional label block with avatar + name (Clinick pattern), then Profile / Settings / Log out
- Keep `asChild` + `SidebarMenuButton`, but make `SidebarMenuButton` (and related menu primitives if needed) properly `forwardRef` so Radix composition works
- Do **not** put `tooltip` on the user menu trigger (breaks trigger composition)

### 3. Files to touch

| File | Change |
|------|--------|
| `frontend/components/ui/sidebar.tsx` | `forwardRef` on `SidebarMenuButton` (and other Slot children used as dropdown triggers if needed) |
| `frontend/components/chat/SessionSidebar.tsx` | Align footer menu with Clinick UX; ensure trigger works |
| `frontend/app/(dashboard)/chat/page.tsx` | Restructure to Clinick-like `SidebarInset` + floating cards |
| `frontend/app/(dashboard)/chat/layout.tsx` | Keep canvas background only (no structural conflict) |

### 4. Success criteria

- Clicking footer user button opens menu (`aria-expanded=true`); items navigate/logout as today
- Desktop: floating rounded sidebar + topbar + main; icon collapse still works
- Mobile: drawer sidebar; floating topbar + main with padding
- Session pin/delete menus still open

## Approach rejected

- **Full Base UI migration (option 3):** higher risk/scope for this fix
- **Raw button-only footer (C):** fixes menu but skips Clinick shell alignment
