"use client";

import { Select as SelectPrimitive } from "@base-ui/react/select";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";
import {
  formFieldBase,
  formFieldSingleLine,
  menuItemBase,
  popoverSurface,
  popupMotion,
} from "./_shared";

// Base UI accepts a state function for className; these wrappers merge it with
// cn(), so they take a plain string.
type WithClassName<P> = Omit<P, "className"> & { className?: string };

/** Cream editorial Select root: one choice from a short list. */
const Select = SelectPrimitive.Root;

/** Groups related options, and gives a label something to name. */
const SelectGroup = SelectPrimitive.Group;

/** Shows the chosen option inside the trigger, or the placeholder. */
const SelectValue = SelectPrimitive.Value;

/**
 * Cream editorial select trigger: the same pale paper box as every text
 * field, 2.5rem tall with a 0.5rem corner and a muted up-down caret at the
 * end. The edge turns terracotta while the list is open.
 */
function SelectTrigger({
  className,
  children,
  ...props
}: WithClassName<SelectPrimitive.Trigger.Props>) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      className={cn(
        formFieldBase,
        formFieldSingleLine,
        "cursor-default items-center justify-between gap-2 whitespace-nowrap text-start",
        "data-[placeholder]:text-muted-foreground data-[popup-open]:border-primary",
        "[&>span]:line-clamp-1",
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon className="flex shrink-0 text-muted-foreground">
        <Icon icon="ph:caret-up-down" className="size-4" aria-hidden="true" />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}
SelectTrigger.displayName = "SelectTrigger";

/**
 * Cream editorial select list: the lightest paper panel with a 0.75rem
 * corner and a warm hairline inside its soft shadow, at least as wide as its
 * trigger. It settles from the trigger as it fades in.
 */
function SelectContent({
  className,
  children,
  side,
  sideOffset = 6,
  align = "start",
  alignOffset,
  alignItemWithTrigger = false,
  ...props
}: WithClassName<SelectPrimitive.Popup.Props> &
  Pick<
    SelectPrimitive.Positioner.Props,
    "side" | "sideOffset" | "align" | "alignOffset" | "alignItemWithTrigger"
  >) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Positioner
        className="isolate z-50 outline-none"
        side={side}
        sideOffset={sideOffset}
        align={align}
        alignOffset={alignOffset}
        alignItemWithTrigger={alignItemWithTrigger}
      >
        <SelectPrimitive.Popup
          data-slot="select-content"
          className={cn(
            popoverSurface,
            popupMotion,
            "relative min-w-(--anchor-width) overflow-hidden",
            className,
          )}
          {...props}
        >
          <SelectPrimitive.ScrollUpArrow className="absolute inset-x-0 top-0 z-10 flex h-6 cursor-default items-center justify-center rounded-t-lg bg-popover text-muted-foreground">
            <Icon icon="ph:caret-up" className="size-3.5" aria-hidden="true" />
          </SelectPrimitive.ScrollUpArrow>
          <SelectPrimitive.List
            data-slot="select-list"
            className={cn(
              "p-1",
              !alignItemWithTrigger &&
                "max-h-(--available-height) overflow-y-auto scroll-py-1",
            )}
          >
            {children}
          </SelectPrimitive.List>
          <SelectPrimitive.ScrollDownArrow className="absolute inset-x-0 bottom-0 z-10 flex h-6 cursor-default items-center justify-center rounded-b-lg bg-popover text-muted-foreground">
            <Icon icon="ph:caret-down" className="size-3.5" aria-hidden="true" />
          </SelectPrimitive.ScrollDownArrow>
        </SelectPrimitive.Popup>
      </SelectPrimitive.Positioner>
    </SelectPrimitive.Portal>
  );
}
SelectContent.displayName = "SelectContent";

/** A small muted caption over a group of options. Use it inside a group. */
function SelectLabel({
  className,
  ...props
}: WithClassName<SelectPrimitive.GroupLabel.Props>) {
  return (
    <SelectPrimitive.GroupLabel
      data-slot="select-label"
      className={cn(
        "px-2.5 py-1.5 text-xs font-medium text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}
SelectLabel.displayName = "SelectLabel";

/**
 * An option row: 2rem tall with a 0.5rem corner and an oat wash when
 * highlighted. The chosen option reads in medium weight with a terracotta
 * tick at the end.
 */
function SelectItem({
  className,
  children,
  ...props
}: WithClassName<SelectPrimitive.Item.Props>) {
  return (
    <SelectPrimitive.Item
      data-slot="select-item"
      className={cn(menuItemBase, "w-full pe-8 data-[selected]:font-medium", className)}
      {...props}
    >
      <SelectPrimitive.ItemText className="line-clamp-1">
        {children}
      </SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator className="pointer-events-none absolute end-2.5 flex size-4 items-center justify-center text-(--primary-text)">
        <Icon icon="ph:check" className="size-4" aria-hidden="true" />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  );
}
SelectItem.displayName = "SelectItem";

/** A warm hairline between option groups that runs to the panel's edges. */
function SelectSeparator({
  className,
  ...props
}: WithClassName<SelectPrimitive.Separator.Props>) {
  return (
    <SelectPrimitive.Separator
      data-slot="select-separator"
      className={cn("-mx-1 my-1 h-px bg-border", className)}
      {...props}
    />
  );
}
SelectSeparator.displayName = "SelectSeparator";

export {
  Select,
  SelectGroup,
  SelectValue,
  SelectTrigger,
  SelectContent,
  SelectLabel,
  SelectItem,
  SelectSeparator,
};
