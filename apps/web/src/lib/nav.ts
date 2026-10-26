import {
  ActivityIcon,
  BellRingIcon,
  BotIcon,
  CoinsIcon,
  KeyRoundIcon,
  LayoutDashboardIcon,
  LightbulbIcon,
  ScrollTextIcon,
  ServerIcon,
  SettingsIcon,
  UsersIcon,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Hidden from viewers when the API only serves admins and owners. */
  adminOnly?: boolean;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  {
    label: "Monitor",
    items: [
      { href: "/", label: "Overview", icon: LayoutDashboardIcon },
      { href: "/live", label: "Live", icon: ActivityIcon },
      { href: "/hosts", label: "Hosts", icon: ServerIcon },
      { href: "/inference", label: "Inference", icon: BotIcon },
    ],
  },
  {
    label: "Optimize",
    items: [
      { href: "/insights", label: "Insights", icon: LightbulbIcon },
      { href: "/costs", label: "Costs", icon: CoinsIcon },
      { href: "/alerts", label: "Alerts", icon: BellRingIcon },
    ],
  },
  {
    label: "Organisation",
    items: [
      { href: "/keys", label: "API keys", icon: KeyRoundIcon, adminOnly: true },
      { href: "/users", label: "Users", icon: UsersIcon, adminOnly: true },
      { href: "/audit", label: "Audit log", icon: ScrollTextIcon, adminOnly: true },
      { href: "/settings", label: "Settings", icon: SettingsIcon },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV.flatMap((g) => g.items);

/** The nav item a path belongs to: exact match for "/", prefix match otherwise. GPU pages
 * belong to Live. */
export function activeNavItem(pathname: string): NavItem | undefined {
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/") return NAV_ITEMS.find((i) => i.href === "/");
  if (path.startsWith("/gpus")) return NAV_ITEMS.find((i) => i.href === "/live");
  return NAV_ITEMS.filter((i) => i.href !== "/" && (path === i.href || path.startsWith(`${i.href}/`))).sort(
    (a, b) => b.href.length - a.href.length,
  )[0];
}

export function isActive(item: NavItem, pathname: string): boolean {
  return activeNavItem(pathname)?.href === item.href;
}
