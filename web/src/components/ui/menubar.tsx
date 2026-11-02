"use client";

import * as React from "react";
import { Menubar as MenubarPrimitive } from "@base-ui/react/menubar";
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

/** One menu in the bar: its trigger and its panel. */
const MenubarMenu = MenuPrimitive.Root;

/** Groups related rows, and gives a label something to name. */
const MenubarGroup = MenuPrimitive.Group;

/** Moves a menu panel to the end of the document body. */
const MenubarPortal = MenuPrimitive.Portal;

/** Wraps a nested menu: its sub-trigger and its sub-content. */
const MenubarSub = MenuPrimitive.SubmenuRoot;

/** Holds a set of radio rows where only one can be chosen. */
const MenubarRadioGroup = MenuPrimitive.RadioGroup;

/**
 * Cream editorial menubar: a row of menu names on an oat tray with a 0.75rem
 * corner. The open menu's name sits on the deeper oat tab, the way a chosen
 * category reads.
 */
const Menubar = React.forwardRef<
  HTMLDivElement,
  WithClassName<MenubarPrimitive.Props>
>(({ className, ...props }, ref) => (
  <MenubarPrimitive
    ref={ref}
    data-slot="menubar"
    className={cn(
      "inline-flex h-10 items-center gap-0.5 rounded-lg bg-secondary p-1 text-secondary-foreground",
      className,
    )}
    {...props}
  />
));
Menubar.displayName = "Menubar";

/** A menu name in the bar: secondary ink at rest, ink on the oat tab while its menu is open. */
const MenubarTrigger = React.forwardRef<
  HTMLButtonElement,
  WithClassName<MenuPrimitive.Trigger.Props>
>(({ className, ...props }, ref) => (
  <MenuPrimitive.Trigger
    ref={ref}
    data-slot="menubar-trigger"
    className={cn(
      "inline-flex h-8 cursor-default select-none items-center rounded-md px-3 text-sm font-medium text-(--foreground-secondary)",
      "transition-colors duration-fast ease-out",
      "hover:text-foreground",
      "outline-none focus-visible:ring-3 focus-visible:ring-ring",
      "data-[popup-open]:bg-muted data-[popup-open]:text-foreground",
      "data-[disabled]:pointer-events-none data-[disabled]:text-(--foreground-disabled)",
      className,
    )}
    {...props}
  />
));
MenubarTrigger.displayName = "MenubarTrigger";

/**
 * Cream editorial menubar panel: pale paper with a 0.75rem corner and a warm
 * hairline inside its soft shadow. It drops from the start edge of its trigger.
 */
const MenubarContent = React.forwardRef<
  HTMLDivElement,
  WithClassName<MenuPrimitive.Popup.Props> & PositionerProps
>(
  (
    {
      className,
      align = "start",
      alignOffset = -4,
      side,
      sideOffset = 8,
      ...props
    },
    ref,
  ) => (
    <MenuPrimitive.Portal>
      <MenuPrimitive.Positioner
        className="isolate z-50 outline-none"
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
      >
        <MenuPrimitive.Popup
          ref={ref}
          data-slot="menubar-content"
          className={cn(menuPanel, className)}
          {...props}
        />
      </MenuPrimitive.Positioner>
    </MenuPrimitive.Portal>
  ),
);
MenubarContent.displayName = "MenubarContent";

/** A nested menu panel. It opens beside its row, level with the row's top. */
const MenubarSubContent = React.forwardRef<
  HTMLDivElement,
  WithClassName<MenuPrimitive.Popup.Props> & PositionerProps
>(
  (
    {
      className,
      align = "start",
      alignOffset = -4,
      side = "right",
      sideOffset = 2,
      ...props
    },
    ref,
  ) => (
    <MenuPrimitive.Portal>
      <MenuPrimitive.Positioner
        className="isolate z-50 outline-none"
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
      >
        <MenuPrimitive.Popup
          ref={ref}
          data-slot="menubar-sub-content"
          className={cn(menuPanel, className)}
          {...props}
        />
      </MenuPrimitive.Positioner>
    </MenuPrimitive.Portal>
  ),
);
MenubarSubContent.displayName = "MenubarSubContent";

/** A row that opens a nested menu, with a caret at the end. */
const MenubarSubTrigger = React.forwardRef<
  HTMLElement,
  WithClassName<MenuPrimitive.SubmenuTrigger.Props> & {
    inset?: boolean;
  }
>(({ className, inset, children, ...props }, ref) => (
  <MenuPrimitive.SubmenuTrigger
    ref={ref}
    data-slot="menubar-sub-trigger"
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
));
MenubarSubTrigger.displayName = "MenubarSubTrigger";

/**
 * A menu row: 2rem tall with a 0.5rem corner and an oat wash under the
 * pointer or keyboard. The destructive variant sets the text in the
 * destructive ink and washes with its pale tint instead.
 */
const MenubarItem = React.forwardRef<
  HTMLElement,
  WithClassName<MenuPrimitive.Item.Props> & {
    inset?: boolean;
    variant?: "default" | "destructive";
  }
>(({ className, inset, variant = "default", ...props }, ref) => (
  <MenuPrimitive.Item
    ref={ref}
    data-slot="menubar-item"
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
));
MenubarItem.displayName = "MenubarItem";

/** A row that toggles on and off. A terracotta tick sits at the end when on. */
const MenubarCheckboxItem = React.forwardRef<
  HTMLElement,
  WithClassName<MenuPrimitive.CheckboxItem.Props>
>(({ className, children, ...props }, ref) => (
  <MenuPrimitive.CheckboxItem
    ref={ref}
    data-slot="menubar-checkbox-item"
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
));
MenubarCheckboxItem.displayName = "MenubarCheckboxItem";

/** One choice in a radio group. A small terracotta dot sits at the end when chosen. */
const MenubarRadioItem = React.forwardRef<
  HTMLElement,
  WithClassName<MenuPrimitive.RadioItem.Props>
>(({ className, children, ...props }, ref) => (
  <MenuPrimitive.RadioItem
    ref={ref}
    data-slot="menubar-radio-item"
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
));
MenubarRadioItem.displayName = "MenubarRadioItem";

/** A small muted caption over a group of rows. Use it inside a group. */
const MenubarLabel = React.forwardRef<
  HTMLDivElement,
  WithClassName<MenuPrimitive.GroupLabel.Props> & {
    inset?: boolean;
  }
>(({ className, inset, ...props }, ref) => (
  <MenuPrimitive.GroupLabel
    ref={ref}
    data-slot="menubar-label"
    className={cn(
      "px-2.5 py-1.5 text-xs font-medium text-muted-foreground",
      inset && "ps-8",
      className,
    )}
    {...props}
  />
));
MenubarLabel.displayName = "MenubarLabel";

/** A warm hairline between groups that runs to the panel's edges. */
const MenubarSeparator = React.forwardRef<
  HTMLDivElement,
  WithClassName<MenuPrimitive.Separator.Props>
>(({ className, ...props }, ref) => (
  <MenuPrimitive.Separator
    ref={ref}
    data-slot="menubar-separator"
    className={cn("-mx-1 my-1 h-px bg-border", className)}
    {...props}
  />
));
MenubarSeparator.displayName = "MenubarSeparator";

/** The keyboard shortcut at the end of a row, in small muted mono type. */
const MenubarShortcut = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) => (
  <span
    data-slot="menubar-shortcut"
    className={cn("ms-auto ps-4 font-mono text-xs text-muted-foreground", className)}
    {...props}
  />
);
MenubarShortcut.displayName = "MenubarShortcut";

export {
  Menubar,
  MenubarMenu,
  MenubarTrigger,
  MenubarContent,
  MenubarItem,
  MenubarSeparator,
  MenubarLabel,
  MenubarCheckboxItem,
  MenubarRadioGroup,
  MenubarRadioItem,
  MenubarPortal,
  MenubarSubContent,
  MenubarSubTrigger,
  MenubarGroup,
  MenubarSub,
  MenubarShortcut,
};
