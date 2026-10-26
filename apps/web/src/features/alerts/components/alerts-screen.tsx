"use client";

import { PlusIcon } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePermissions } from "@/features/auth/api";
import type { AlertRule, Channel } from "@/lib/api/types";

import { useAlertEvents } from "../api";

import { isAlertTab, type AlertTab } from "./alert-utils";
import { ChannelDialog } from "./channel-dialog";
import { ChannelsPanel } from "./channels-panel";
import { DeliveriesPanel } from "./deliveries-panel";
import { EventsPanel } from "./events-panel";
import { RuleDialog } from "./rule-dialog";
import { RulesPanel } from "./rules-panel";

export function AlertsScreen() {
  const { canWrite } = usePermissions();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get("tab");
  const tab: AlertTab = isAlertTab(raw) ? raw : "events";
  const events = useAlertEvents(false);
  const firing = (events.data ?? []).filter((e) => !e.resolved_at).length;

  const [ruleOpen, setRuleOpen] = React.useState(false);
  const [editingRule, setEditingRule] = React.useState<AlertRule | null>(null);
  const [channelOpen, setChannelOpen] = React.useState(false);
  const [editingChannel, setEditingChannel] = React.useState<Channel | null>(null);

  const setTab = React.useCallback(
    (next: AlertTab) => {
      const sp = new URLSearchParams(params.toString());
      if (next === "events") sp.delete("tab");
      else sp.set("tab", next);
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  const newRule = () => {
    setEditingRule(null);
    setRuleOpen(true);
  };
  const newChannel = () => {
    setEditingChannel(null);
    setChannelOpen(true);
  };
  const goToChannels = () => setTab("channels");

  return (
    <>
      <PageHeader
        title="Alerts"
        description="Rules watch every GPU and host. When one fires, GPUWatch notifies your channels once, and again when it resolves."
        actions={
          canWrite &&
          (tab === "rules" ? (
            <Button onClick={newRule}>
              <PlusIcon />
              New rule
            </Button>
          ) : tab === "channels" ? (
            <Button onClick={newChannel}>
              <PlusIcon />
              New channel
            </Button>
          ) : null)
        }
      />
      <Tabs value={tab} onValueChange={(v) => isAlertTab(v) && setTab(v)}>
        <TabsList aria-label="Alerts sections">
          <TabsTrigger value="events">
            Events
            {firing > 0 && (
              <span className="rounded-full bg-danger-soft px-1.5 text-[11px] leading-[18px] font-semibold text-danger tabular" aria-label={`${firing} firing`}>
                {firing}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="rules">Rules</TabsTrigger>
          <TabsTrigger value="channels">Channels</TabsTrigger>
          <TabsTrigger value="deliveries">Deliveries</TabsTrigger>
        </TabsList>
        <TabsContent value="events">
          <EventsPanel onAddChannel={goToChannels} onOpenRules={() => setTab("rules")} />
        </TabsContent>
        <TabsContent value="rules">
          <RulesPanel
            canWrite={canWrite}
            onCreate={newRule}
            onEdit={(r) => {
              setEditingRule(r);
              setRuleOpen(true);
            }}
          />
        </TabsContent>
        <TabsContent value="channels">
          <ChannelsPanel
            canWrite={canWrite}
            onCreate={newChannel}
            onEdit={(c) => {
              setEditingChannel(c);
              setChannelOpen(true);
            }}
          />
        </TabsContent>
        <TabsContent value="deliveries">
          <DeliveriesPanel onAddChannel={goToChannels} />
        </TabsContent>
      </Tabs>
      {!canWrite && <p className="mt-3 text-xs text-muted-foreground">Viewers can read alerts. Ask an admin to change rules or channels.</p>}
      <RuleDialog
        open={ruleOpen}
        onOpenChange={setRuleOpen}
        editing={editingRule}
        onAddChannel={() => {
          setTab("channels");
          newChannel();
        }}
      />
      <ChannelDialog open={channelOpen} onOpenChange={setChannelOpen} editing={editingChannel} />
    </>
  );
}
