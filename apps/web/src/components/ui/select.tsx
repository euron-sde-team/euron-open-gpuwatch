"use client";

import * as React from "react";
import { Select as SelectPrimitive } from "@base-ui/react/select";
import { CheckIcon, ChevronDownIcon } from "lucide-react";

import { cn } from "@/lib/cn";

const Select = SelectPrimitive.Root;

function SelectValue({ className, ...props }: SelectPrimitive.Value.Props) {
  return <SelectPrimitive.Value data-slot="select-value" className={cn("flex-1 truncate text-left", className)} {...props} />;
}

function SelectTrigger({
  className,
  children,
  size = "default",
  ...props
}: SelectPrimitive.Trigger.Props & { size?: "default" | "sm" }) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      data-size={size}
      className={cn(
        "flex w-full min-w-0 items-center justify-between gap-2 rounded-lg bg-card text-left text-sm text-foreground shadow-[var(--elev-1)] ring-1 ring-input ring-inset whitespace-nowrap select-none",
        "transition-[box-shadow] duration-150 outline-none hover:ring-[color-mix(in_srgb,var(--primary)_35%,var(--input))]",
        "focus-visible:ring-2 focus-visible:ring-ring data-popup-open:ring-2 data-popup-open:ring-ring",
        "data-disabled:cursor-not-allowed data-disabled:opacity-60 data-placeholder:text-faint",
        "data-[size=default]:h-9 data-[size=default]:pr-2.5 data-[size=default]:pl-3",
        "data-[size=sm]:h-8 data-[size=sm]:pr-2 data-[size=sm]:pl-2.5 data-[size=sm]:text-[13px]",
        "dark:bg-muted/60 [&_svg]:pointer-events-none [&_svg]:shrink-0",
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon render={<ChevronDownIcon className="size-4 text-muted-foreground" />} />
    </SelectPrimitive.Trigger>
  );
}

function SelectContent({
  className,
  children,
  side = "bottom",
  sideOffset = 4,
  align = "start",
  ...props
}: SelectPrimitive.Popup.Props & Pick<SelectPrimitive.Positioner.Props, "align" | "side" | "sideOffset">) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Positioner
        side={side}
        sideOffset={sideOffset}
        align={align}
        alignItemWithTrigger={false}
        className="isolate z-[60]"
      >
        <SelectPrimitive.Popup
          data-slot="select-content"
          className={cn(
            "relative isolate z-50 max-h-(--available-height) w-max min-w-(--anchor-width) max-w-[min(26rem,var(--available-width))] origin-(--transform-origin) overflow-x-hidden overflow-y-auto rounded-xl bg-popover p-1 text-popover-foreground shadow-[var(--elev-4)] ring-1 ring-black/5 duration-100 dark:ring-white/8 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0",
            className,
          )}
          {...props}
        >
          <SelectPrimitive.List>{children}</SelectPrimitive.List>
        </SelectPrimitive.Popup>
      </SelectPrimitive.Positioner>
    </SelectPrimitive.Portal>
  );
}

function SelectItem({ className, children, ...props }: SelectPrimitive.Item.Props) {
  return (
    <SelectPrimitive.Item
      data-slot="select-item"
      className={cn(
        "relative flex min-h-8 w-full cursor-default items-center gap-2 rounded-md py-1.5 pr-8 pl-2.5 text-[13px] outline-hidden select-none data-highlighted:bg-muted data-disabled:pointer-events-none data-disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <SelectPrimitive.ItemText className="flex flex-1 items-center gap-2 whitespace-nowrap">{children}</SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator render={<span className="pointer-events-none absolute right-2 flex size-4 items-center justify-center text-primary" />}>
        <CheckIcon className="size-3.5" strokeWidth={2.5} />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  );
}

function SelectGroupLabel({ className, ...props }: SelectPrimitive.GroupLabel.Props) {
  return (
    <SelectPrimitive.GroupLabel
      className={cn("px-2.5 pt-2 pb-1 text-[11px] font-semibold tracking-wide text-faint uppercase", className)}
      {...props}
    />
  );
}

export interface SelectOption {
  value: string;
  label: React.ReactNode;
  disabled?: boolean;
}

/**
 * The common case: a single value from a flat option list. The trigger shows the
 * option's label (not its raw value), and `""` means "nothing selected".
 */
function SimpleSelect({
  value,
  onValueChange,
  options,
  placeholder = "Select",
  id,
  size,
  className,
  disabled,
  "aria-label": ariaLabel,
}: {
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  id?: string;
  size?: "default" | "sm";
  className?: string;
  disabled?: boolean;
  "aria-label"?: string;
}) {
  const items = React.useMemo(() => options.map((o) => ({ value: o.value, label: o.label })), [options]);
  return (
    <Select
      items={items}
      value={value === "" ? null : value}
      onValueChange={(v) => onValueChange(typeof v === "string" ? v : "")}
      disabled={disabled}
    >
      <SelectTrigger id={id} size={size} className={className} aria-label={ariaLabel}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value} disabled={o.disabled}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export { Select, SelectTrigger, SelectValue, SelectContent, SelectItem, SelectGroupLabel, SimpleSelect };
