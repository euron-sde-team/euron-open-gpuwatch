"use client";

import { MonitorIcon, MoonIcon, SunIcon } from "lucide-react";
import { useTheme } from "next-themes";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

/** Light / dark flip for the top bar. */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted();
  const dark = mounted && resolvedTheme === "dark";
  return (
    <Button
      variant="subtle"
      size="icon"
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => setTheme(dark ? "light" : "dark")}
    >
      {dark ? <SunIcon /> : <MoonIcon />}
    </Button>
  );
}

/** Three-way picker for Settings. */
export function ThemeSelector() {
  const { theme, setTheme } = useTheme();
  const mounted = useMounted();
  const options = [
    { id: "light", label: "Light", icon: SunIcon },
    { id: "dark", label: "Dark", icon: MoonIcon },
    { id: "system", label: "System", icon: MonitorIcon },
  ];
  return (
    <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-2 sm:max-w-md">
      {options.map((o) => {
        const active = mounted && theme === o.id;
        return (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setTheme(o.id)}
            className={cn(
              "flex flex-col items-center gap-1.5 rounded-xl bg-muted px-3 py-3 text-[13px] font-medium text-muted-foreground transition-[color,background-color,box-shadow] hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring",
              active && "bg-primary-soft text-primary ring-2 ring-primary/40",
            )}
          >
            <o.icon className="size-4" />
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function useMounted() {
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  return mounted;
}
