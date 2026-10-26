"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { PageHeader } from "@/components/page-header";
import { Segmented } from "@/components/segmented";
import { SimpleSelect } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePermissions } from "@/features/auth/api";
import type { GroupBy } from "@/lib/api/types";

import { BreakdownTab } from "./breakdown-tab";
import { GROUP_OPTIONS, isCostRange, isGroupBy, RANGE_OPTIONS, type CostRange } from "./costs-shared";
import { RatesTab } from "./rates-tab";
import { ReportsTab } from "./reports-tab";
import { RulesTab } from "./rules-tab";

const TABS = [
  { value: "breakdown", label: "Breakdown" },
  { value: "rates", label: "Rates" },
  { value: "rules", label: "Workload rules" },
  { value: "reports", label: "Reports" },
] as const;
type Tab = (typeof TABS)[number]["value"];

function isTab(v: unknown): v is Tab {
  return typeof v === "string" && TABS.some((t) => t.value === v);
}

const DEFAULTS = { tab: "breakdown", range: "7d", group: "workload" } as const;

/** The Costs page. Tab, range and grouping live in the URL so a link reopens the same view. */
export function CostsScreen() {
  const { canWrite } = usePermissions();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const tabParam = params.get("tab");
  const rangeParam = params.get("range");
  const groupParam = params.get("group");
  const tab: Tab = isTab(tabParam) ? tabParam : DEFAULTS.tab;
  const range: CostRange = isCostRange(rangeParam) ? rangeParam : DEFAULTS.range;
  const groupBy: GroupBy = isGroupBy(groupParam) ? groupParam : DEFAULTS.group;

  const setParam = React.useCallback(
    (key: keyof typeof DEFAULTS, value: string) => {
      const next = new URLSearchParams(params.toString());
      if (value === DEFAULTS[key]) next.delete(key);
      else next.set(key, value);
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  return (
    <>
      <PageHeader
        title="Costs"
        description="What GPU time cost, by workload, team, host, GPU or model, and how much of it bought nothing. Figures are estimates from your own hourly rates."
        actions={
          tab === "breakdown" && (
            <>
              <SimpleSelect
                aria-label="Group costs by"
                size="sm"
                className="w-32"
                value={groupBy}
                onValueChange={(v) => v && setParam("group", v)}
                options={GROUP_OPTIONS.map((o) => ({ value: o.value, label: `By ${o.label.toLowerCase()}` }))}
              />
              <Segmented ariaLabel="Time range" value={range} onChange={(v) => setParam("range", v)} options={RANGE_OPTIONS} className="w-40" />
            </>
          )
        }
      />
      <Tabs value={tab} onValueChange={(v) => isTab(v) && setParam("tab", v)}>
        <div className="-mx-4 overflow-x-auto px-4 no-scrollbar sm:mx-0 sm:px-0">
          <TabsList className="flex-nowrap">
            {TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value="breakdown">
          <BreakdownTab groupBy={groupBy} range={range} onSetRate={() => setParam("tab", "rates")} />
        </TabsContent>
        <TabsContent value="rates">
          <RatesTab canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="rules">
          <RulesTab canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="reports">
          <ReportsTab canWrite={canWrite} defaultGroup={groupBy} defaultRange={range} />
        </TabsContent>
      </Tabs>
    </>
  );
}
