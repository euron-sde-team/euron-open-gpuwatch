"use client";

import { PanelLeftCloseIcon, PanelLeftOpenIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { WatchLogo } from "@/components/logo";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { usePermissions } from "@/features/auth/api";
import { cn } from "@/lib/cn";
import { isActive, NAV } from "@/lib/nav";
import { useUiPrefs } from "@/lib/store";

export function SidebarNav({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const { canWrite } = usePermissions();
  return (
    <nav aria-label="Main" className="flex flex-col gap-5">
      {NAV.map((group) => (
        <div key={group.label} className="flex flex-col gap-0.5">
          {collapsed ? (
            <div className="mx-auto mb-1 h-px w-5 bg-hairline first:hidden" aria-hidden />
          ) : (
            <div className="px-2.5 pb-1 text-[10.5px] font-semibold tracking-[0.08em] text-faint uppercase">{group.label}</div>
          )}
          {group.items.filter((item) => canWrite || !item.adminOnly).map((item) => {
            const active = isActive(item, pathname);
            const link = (
              <Link
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-[13px] font-medium text-muted-foreground transition-colors outline-none hover:bg-accent/70 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring",
                  active && "bg-card text-foreground shadow-[var(--elev-1)] hover:bg-card dark:bg-accent dark:hover:bg-accent",
                  collapsed && "justify-center px-0",
                )}
              >
                <item.icon className={cn("size-4 shrink-0", active ? "text-primary" : "text-subtle group-hover:text-foreground")} />
                {!collapsed && <span className="truncate">{item.label}</span>}
                {collapsed && <span className="sr-only">{item.label}</span>}
              </Link>
            );
            return collapsed ? (
              <Tooltip key={item.href}>
                <TooltipTrigger render={link} />
                <TooltipContent side="right">{item.label}</TooltipContent>
              </Tooltip>
            ) : (
              <div key={item.href}>{link}</div>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

export function Sidebar() {
  const collapsed = useUiPrefs((s) => s.sidebarCollapsed);
  const toggle = useUiPrefs((s) => s.toggleSidebar);
  return (
    <div className={cn("hidden shrink-0 bg-sidebar transition-[width] duration-200 lg:block", collapsed ? "w-[60px]" : "w-[232px]")}>
    <aside className="sticky top-0 flex h-dvh flex-col">
      <div className={cn("flex h-14 items-center", collapsed ? "justify-center" : "px-4")}>
        <Link href="/" className="rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="GPUWatch home">
          <WatchLogo collapsed={collapsed} />
        </Link>
      </div>
      <div className={cn("no-scrollbar flex-1 overflow-y-auto pt-2 pb-4", collapsed ? "px-2" : "px-3")}>
        <SidebarNav collapsed={collapsed} />
      </div>
      <div className={cn("pb-3", collapsed ? "px-2" : "px-3")}>
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "flex h-8 w-full items-center gap-2.5 rounded-lg px-2.5 text-[12.5px] text-subtle transition-colors hover:bg-accent/70 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring",
            collapsed && "justify-center px-0",
          )}
        >
          {collapsed ? <PanelLeftOpenIcon className="size-4" /> : <PanelLeftCloseIcon className="size-4" />}
          {!collapsed && "Collapse"}
        </button>
      </div>
    </aside>
    </div>
  );
}
