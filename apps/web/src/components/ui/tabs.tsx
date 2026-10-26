"use client";

import { Tabs as TabsPrimitive } from "@base-ui/react/tabs";

import { cn } from "@/lib/cn";

function Tabs({ className, ...props }: TabsPrimitive.Root.Props) {
  return <TabsPrimitive.Root data-slot="tabs" className={cn("flex flex-col gap-5", className)} {...props} />;
}

/** Segmented control: a recessed track with the active segment raised. */
function TabsList({ className, ...props }: TabsPrimitive.List.Props) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn("inline-flex w-fit max-w-full flex-wrap items-center gap-0.5 rounded-lg bg-muted p-0.5", className)}
      {...props}
    />
  );
}

function TabsTrigger({ className, ...props }: TabsPrimitive.Tab.Props) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      className={cn(
        "inline-flex h-7 items-center justify-center gap-1.5 rounded-md px-3 text-[13px] font-medium whitespace-nowrap text-muted-foreground transition-[color,background-color,box-shadow] duration-150 outline-none select-none",
        "hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40",
        "data-active:bg-card data-active:text-foreground data-active:shadow-[var(--elev-1)] dark:data-active:bg-accent",
        "[&_svg]:size-3.5 [&_svg]:shrink-0",
        className,
      )}
      {...props}
    />
  );
}

function TabsContent({ className, ...props }: TabsPrimitive.Panel.Props) {
  return <TabsPrimitive.Panel data-slot="tabs-content" className={cn("outline-none", className)} {...props} />;
}

export { Tabs, TabsList, TabsTrigger, TabsContent };
