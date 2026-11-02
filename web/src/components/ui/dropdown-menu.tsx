"use client";

import * as React from "react";
import { Menu as MenuPrimitive } from "@base-ui/react/menu";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";
import { menuItemBase, popoverSurface, popupMotion } from "./_shared";

// Base UI accepts a state function for className; these wrappers merge it with
// cn(), so they take a plain string.
type WithClassName<P> = Omit<P, "className"> & { className?: string };

type PositionerProps = Pick<
  MenuPrimitive.Positioner.Props,
  "align" | "alignOffset" | "side" | "sideOffset"
>;

/** The menu panel: the lightest paper, at least 12rem wide, padded 0.25rem. */
const menuPanel = cn(
  popoverSurface,
  popupMotion,
  "min-w-48 max-h-(--available-height) overflow-y-auto p-1",
);

/** Cream editorial DropdownMenu root: a list of actions behind one trigger. */
const DropdownMenu = MenuPrimitive.Root;

/** The control the menu opens from. */
const DropdownMenuTrigger = MenuPrimitive.Trigger;

/** Groups related rows, and gives a label something to name. */
const DropdownMenuGroup = MenuPrimitive.Group;

/** Moves a menu panel to the end of the document body. */
const DropdownMenuPortal = MenuPrimitive.Portal;

/** Wraps a nested menu: its sub-trigger and its sub-content. */
const DropdownMenuSub = MenuPrimitive.SubmenuRoot;

/** Holds a set of radio rows where only one can be chosen. */
const DropdownMenuRadioGroup = MenuPrimitive.RadioGroup;

/**
 * Cream editorial menu panel: pale paper with a 0.75rem corner and a warm
 * hairline inside its soft shadow. It settles from the trigger as it fades in.
 */
function DropdownMenuContent({
  className,
  align = "start",
  alignOffset,
  side,
  sideOffset = 6,
  ...props
}: WithClassName<MenuPrimitive.Popup.Props> & PositionerProps) {
  return (
    <MenuPrimitive.Portal>
      <MenuPrimitive.Positioner
        className="isolate z-50 outline-none"
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
      >
        <MenuPrimitive.Popup
          data-slot="dropdown-menu-content"
          className={cn(menuPanel, className)}
          {...props}
        />
      </MenuPrimitive.Positioner>
    </MenuPrimitive.Portal>
  );
}
DropdownMenuContent.displayName = "DropdownMenuContent";

/** A nested menu panel. It opens beside its row, level with the row's top. */
function DropdownMenuSubContent({
  className,
  align = "start",
  alignOffset = -4,
  side = "right",
  sideOffset = 2,
  ...props
}: WithClassName<MenuPrimitive.Popup.Props> & PositionerProps) {
  return (
    <MenuPrimitive.Portal>
      <MenuPrimitive.Positioner
        className="isolate z-50 outline-none"
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
      >
        <MenuPrimitive.Popup
          data-slot="dropdown-menu-sub-content"
          className={cn(menuPanel, className)}
          {...props}
        />
      </MenuPrimitive.Positioner>
    </MenuPrimitive.Portal>
  );
}
DropdownMenuSubContent.displayName = "DropdownMenuSubContent";

/**
 * A menu row: 2rem tall with a 0.5rem corner and an oat wash under the
 * pointer or keyboard. The destructive variant sets the text in the
 * destructive ink and washes with its pale tint instead.
 */
function DropdownMenuItem({
  className,
  inset,
  variant = "default",
  ...props
}: WithClassName<MenuPrimitive.Item.Props> & {
  inset?: boolean;
  variant?: "default" | "destructive";
}) {
  return (
    <MenuPrimitive.Item
      data-slot="dropdown-menu-item"
      data-variant={variant}
      className={cn(
        menuItemBase,
        "[&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground",
        variant === "destructive" &&
          "text-(--destructive-text) data-[highlighted]:bg-(--destructive-tint) data-[highlighted]:text-(--destructive-text) [&_svg]:text-(--destructive-text)",
        inset && "ps-8",
        className,
      )}
      {...props}
    />
  );
}
DropdownMenuItem.displayName = "DropdownMenuItem";

/** A row that opens a nested menu, with a caret at the end. */
function DropdownMenuSubTrigger({
  className,
  inset,
  children,
  ...props
}: WithClassName<MenuPrimitive.SubmenuTrigger.Props> & {
  inset?: boolean;
}) {
  return (
    <MenuPrimitive.SubmenuTrigger
      data-slot="dropdown-menu-sub-trigger"
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
        className="ms-auto size-3.5 text-muted-foreground rtl:rotate-180"
        aria-hidden="true"
      />
    </MenuPrimitive.SubmenuTrigger>
  );
}
DropdownMenuSubTrigger.displayName = "DropdownMenuSubTrigger";

/** A row that toggles on and off. A terracotta tick sits at the end when on. */
function DropdownMenuCheckboxItem({
  className,
  children,
  ...props
}: WithClassName<MenuPrimitive.CheckboxItem.Props>) {
  return (
    <MenuPrimitive.CheckboxItem
      data-slot="dropdown-menu-checkbox-item"
      className={cn(menuItemBase, "pe-8", className)}
      {...props}
    >
      {children}
      <span className="pointer-events-none absolute end-2.5 flex size-4 items-center justify-center">
        <MenuPrimitive.CheckboxItemIndicator>
          <Icon icon="ph:check" className="size-4 text-(--primary-text)" aria-hidden="true" />
        </MenuPrimitive.CheckboxItemIndicator>
      </span>
    </MenuPrimitive.CheckboxItem>
  );
}
DropdownMenuCheckboxItem.displayName = "DropdownMenuCheckboxItem";

/** One choice in a radio group. A small terracotta dot sits at the end when chosen. */
function DropdownMenuRadioItem({
  className,
  children,
  ...props
}: WithClassName<MenuPrimitive.RadioItem.Props>) {
  return (
    <MenuPrimitive.RadioItem
      data-slot="dropdown-menu-radio-item"
      className={cn(menuItemBase, "pe-8", className)}
      {...props}
    >
      {children}
      <span className="pointer-events-none absolute end-2.5 flex size-4 items-center justify-center">
        <MenuPrimitive.RadioItemIndicator>
          <span className="block size-2 rounded-full bg-primary" />
        </MenuPrimitive.RadioItemIndicator>
      </span>
    </MenuPrimitive.RadioItem>
  );
}
DropdownMenuRadioItem.displayName = "DropdownMenuRadioItem";

/** A small muted caption over a group of rows. Use it inside a group. */
function DropdownMenuLabel({
  className,
  inset,
  ...props
}: WithClassName<MenuPrimitive.GroupLabel.Props> & {
  inset?: boolean;
}) {
  return (
    <MenuPrimitive.GroupLabel
      data-slot="dropdown-menu-label"
      className={cn(
        "px-2.5 py-1.5 text-xs font-medium text-muted-foreground",
        inset && "ps-8",
        className,
      )}
      {...props}
    />
  );
}
DropdownMenuLabel.displayName = "DropdownMenuLabel";

/** A warm hairline between groups that runs to the panel's edges. */
function DropdownMenuSeparator({
  className,
  ...props
}: WithClassName<MenuPrimitive.Separator.Props>) {
  return (
    <MenuPrimitive.Separator
      data-slot="dropdown-menu-separator"
      className={cn("-mx-1 my-1 h-px bg-border", className)}
      {...props}
    />
  );
}
DropdownMenuSeparator.displayName = "DropdownMenuSeparator";

/** The keyboard shortcut at the end of a row, in small muted mono type. */
function DropdownMenuShortcut({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      data-slot="dropdown-menu-shortcut"
      className={cn("ms-auto ps-4 font-mono text-xs text-muted-foreground", className)}
      {...props}
    />
  );
}
DropdownMenuShortcut.displayName = "DropdownMenuShortcut";

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuRadioItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuGroup,
  DropdownMenuPortal,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuRadioGroup,
};
