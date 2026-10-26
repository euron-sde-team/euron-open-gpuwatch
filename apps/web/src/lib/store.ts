"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export const DAY_OPTIONS = [1, 7, 30] as const;
export type Days = (typeof DAY_OPTIONS)[number];

function isDays(value: unknown): value is Days {
  return typeof value === "number" && (DAY_OPTIONS as readonly number[]).includes(value);
}

/**
 * Persisted UI preferences only (never server data). Rehydrated after mount so the
 * first client render matches the server render. The theme itself is persisted by
 * next-themes.
 */
interface UiPrefs {
  days: Days;
  sidebarCollapsed: boolean;
  setDays: (days: Days) => void;
  toggleSidebar: () => void;
}

export const useUiPrefs = create<UiPrefs>()(
  persist(
    (set) => ({
      days: 30,
      sidebarCollapsed: false,
      setDays: (days) => set({ days }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
    }),
    {
      name: "gpuwatch.ui",
      version: 1,
      skipHydration: true,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ days: s.days, sidebarCollapsed: s.sidebarCollapsed }),
      merge: (persisted, current) => {
        const p = (persisted ?? {}) as Partial<UiPrefs>;
        return {
          ...current,
          days: isDays(p.days) ? p.days : current.days,
          sidebarCollapsed: typeof p.sidebarCollapsed === "boolean" ? p.sidebarCollapsed : current.sidebarCollapsed,
        };
      },
    },
  ),
);
