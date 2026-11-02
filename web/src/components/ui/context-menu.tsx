"use client";

import * as React from "react";
import { ContextMenu as ContextMenuPrimitive } from "@base-ui/react/context-menu";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";
import { menuItemBase, popoverSurface, popupMotion } from "./_shared";

// Base UI accepts a state function for className; these wrappers merge it with
// cn(), so they take a plain string.
type WithClassName<P> = Omit<P, "className"> & { className?: string };

/** The menu panel: the floating paper surface, at least 12rem wide, padded 0.25rem. */
const menuPanel = cn(
  popoverSurface,
  popupMotion,
  "min-w-48 max-h-(--available-height) overflow-y-auto p-1",
);

/** Cream editorial ContextMenu root: the actions a right click or long press offers. */
const ContextMenu = ContextMenuPrimitive.Root;

/** The area that opens the menu on right click or long press. */
const ContextMenuTrigger = ContextMenuPrimitive.Trigger;

/** Groups related rows, and gives a label something to name. */
const ContextMenuGroup = ContextMenuPrimitive.Group;

/** Moves a menu panel to the end of the document body. */
const ContextMenuPortal = ContextMenuPrimitive.Portal;

/** Wraps a nested menu: its sub-trigger and its sub-content. */
const ContextMenuSub = ContextMenuPrimitive.SubmenuRoot;

/** Holds a set of radio rows where only one can be chosen. */
const ContextMenuRadioGroup = ContextMenuPrimitive.RadioGroup;

/**
 * Cream editorial context menu: the lightest paper with a 0.75rem corner,
 * edged by a hairline ring in a soft shadow. It opens at the pointer and
 * settles from that point.
 */
function ContextMenuContent({
  className,
  ...props
}: WithClassName<ContextMenuPrimitive.Popup.Props>) {
  return (
    <ContextMenuPrimitive.Portal>
      <ContextMenuPrimitive.Positioner className="isolate z-50 outline-none">
        <ContextMenuPrimitive.Popup
          data-slot="context-menu-content"
          className={cn(menuPanel, className)}
          {...props}
        />
      </ContextMenuPrimitive.Positioner>
    </ContextMenuPrimitive.Portal>
  );
}
ContextMenuContent.displayName = "ContextMenuContent";

/** A nested menu panel. It opens beside its row, level with the row's top. */
function ContextMenuSubContent({
  className,
  align = "start",
  alignOffset = -4,
  side = "right",
  sideOffset = 2,
  ...props
}: WithClassName<ContextMenuPrimitive.Popup.Props> &
  Pick<
    ContextMenuPrimitive.Positioner.Props,
    "align" | "alignOffset" | "side" | "sideOffset"
  >) {
  return (
    <ContextMenuPrimitive.Portal>
      <ContextMenuPrimitive.Positioner
        className="isolate z-50 outline-none"
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
      >
        <ContextMenuPrimitive.Popup
          data-slot="context-menu-sub-content"
          className={cn(menuPanel, className)}
          {...props}
        />
      </ContextMenuPrimitive.Positioner>
    </ContextMenuPrimitive.Portal>
  );
}
ContextMenuSubContent.displayName = "ContextMenuSubContent";

/**
 * A menu row with a 0.5rem corner. An oat wash fills it under the pointer
 * or keyboard. The destructive variant sets the text in the warning red and
 * fills with a pale red tint instead.
 */
function ContextMenuItem({
  className,
  inset,
  variant = "default",
  ...props
}: WithClassName<ContextMenuPrimitive.Item.Props> & {
  inset?: boolean;
  variant?: "default" | "destructive";
}) {
  return (
    <ContextMenuPrimitive.Item
      data-slot="context-menu-item"
      data-variant={variant}
      className={cn(
        menuItemBase,
        "[&_svg]:size-4 [&_svg]:shrink-0",
        variant === "destructive" &&
          "text-(--destructive-text) data-[highlighted]:bg-(--destructive-tint) data-[highlighted]:text-(--destructive-text)",
        inset && "ps-8",
        className,
      )}
      {...props}
    />
  );
}
ContextMenuItem.displayName = "ContextMenuItem";

/** A row that opens a nested menu, with a caret at the end. */
function ContextMenuSubTrigger({
  className,
  inset,
  children,
  ...props
}: WithClassName<ContextMenuPrimitive.SubmenuTrigger.Props> & {
  inset?: boolean;
}) {
  return (
    <ContextMenuPrimitive.SubmenuTrigger
      data-slot="context-menu-sub-trigger"
      className={cn(
        menuItemBase,
        "data-[popup-open]:bg-accent data-[popup-open]:text-accent-foreground",
        inset && "ps-8",
        className,
      )}
      {...props}
    >
      {children}
      <Icon
        icon="ph:caret-right"
        className="ms-auto size-4 text-muted-foreground rtl:rotate-180"
        aria-hidden="true"
      />
    </ContextMenuPrimitive.SubmenuTrigger>
  );
}
ContextMenuSubTrigger.displayName = "ContextMenuSubTrigger";

/** A row that toggles on and off. An ink tick sits at the end when on. */
function ContextMenuCheckboxItem({
  className,
  children,
  ...props
}: WithClassName<ContextMenuPrimitive.CheckboxItem.Props>) {
  return (
    <ContextMenuPrimitive.CheckboxItem
      data-slot="context-menu-checkbox-item"
      className={cn(menuItemBase, "pe-8", className)}
      {...props}
    >
      {children}
      <span className="pointer-events-none absolute end-2 flex size-4 items-center justify-center">
        <ContextMenuPrimitive.CheckboxItemIndicator>
          <Icon icon="ph:check" className="size-4" aria-hidden="true" />
        </ContextMenuPrimitive.CheckboxItemIndicator>
      </span>
    </ContextMenuPrimitive.CheckboxItem>
  );
}
ContextMenuCheckboxItem.displayName = "ContextMenuCheckboxItem";

/** One choice in a radio group. A small ink dot sits at the end when chosen. */
function ContextMenuRadioItem({
  className,
  children,
  ...props
}: WithClassName<ContextMenuPrimitive.RadioItem.Props>) {
  return (
    <ContextMenuPrimitive.RadioItem
      data-slot="context-menu-radio-item"
      className={cn(menuItemBase, "pe-8", className)}
      {...props}
    >
      {children}
      <span className="pointer-events-none absolute end-2 flex size-4 items-center justify-center">
        <ContextMenuPrimitive.RadioItemIndicator>
          <span className="block size-1.5 rounded-full bg-foreground" />
        </ContextMenuPrimitive.RadioItemIndicator>
      </span>
    </ContextMenuPrimitive.RadioItem>
  );
}
ContextMenuRadioItem.displayName = "ContextMenuRadioItem";

/** A small muted heading over a group of rows. Use it inside a group. */
function ContextMenuLabel({
  className,
  inset,
  ...props
}: WithClassName<ContextMenuPrimitive.GroupLabel.Props> & {
  inset?: boolean;
}) {
  return (
    <ContextMenuPrimitive.GroupLabel
      data-slot="context-menu-label"
      className={cn(
        "px-2.5 py-1.5 text-xs font-medium text-muted-foreground",
        inset && "ps-8",
        className,
      )}
      {...props}
    />
  );
}
ContextMenuLabel.displayName = "ContextMenuLabel";

/** A hairline between groups that runs to the panel's edges. */
function ContextMenuSeparator({
  className,
  ...props
}: WithClassName<ContextMenuPrimitive.Separator.Props>) {
  return (
    <ContextMenuPrimitive.Separator
      data-slot="context-menu-separator"
      className={cn("-mx-1 my-1 h-px bg-border", className)}
      {...props}
    />
  );
}
ContextMenuSeparator.displayName = "ContextMenuSeparator";

/** The keyboard shortcut at the end of a row, in small muted type. */
function ContextMenuShortcut({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      data-slot="context-menu-shortcut"
      className={cn("ms-auto ps-4 text-xs tracking-wide text-muted-foreground", className)}
      {...props}
    />
  );
}
ContextMenuShortcut.displayName = "ContextMenuShortcut";

export {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuCheckboxItem,
  ContextMenuRadioItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuShortcut,
  ContextMenuGroup,
  ContextMenuPortal,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuRadioGroup,
};
