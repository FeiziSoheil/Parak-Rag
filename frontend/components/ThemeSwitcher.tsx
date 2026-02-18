"use client";

import { useTheme } from "next-themes";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Palette, Sun, Moon, Monitor } from "lucide-react";
import { useAccentTheme } from "@/contexts/AccentThemeContext";
import { cn } from "@/lib/utils";

const modeOptions = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const;

type ThemeSwitcherProps = {
  /** When provided (e.g. SidebarMenuButton), used as dropdown trigger for sidebar usage */
  trigger?: React.ReactNode;
};

export function ThemeSwitcher({ trigger }: ThemeSwitcherProps) {
  const { theme, setTheme } = useTheme();
  const { accent, setAccent, options: accentOptions } = useAccentTheme();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {trigger ?? (
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0 size-9 rounded-md"
            aria-label="Theme & accent"
          >
            <Palette className="h-4 w-4" />
          </Button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuLabel>Mode</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={theme ?? "system"}
          onValueChange={(v) => setTheme(v)}
        >
          {modeOptions.map(({ value, label, icon: Icon }) => (
            <DropdownMenuRadioItem key={value} value={value}>
              <Icon className="mr-2 h-4 w-4" />
              {label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Accent</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={accent} onValueChange={(v) => setAccent(v as typeof accent)}>
          {accentOptions.map(({ value, label }) => (
            <DropdownMenuRadioItem key={value} value={value}>
              <span
                className={cn(
                  "mr-2 size-3 rounded-full border border-border",
                  value === "zinc" && "bg-zinc-500",
                  value === "blue" && "bg-blue-500",
                  value === "rose" && "bg-rose-500",
                  value === "emerald" && "bg-emerald-500",
                  value === "violet" && "bg-violet-500"
                )}
              />
              {label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
