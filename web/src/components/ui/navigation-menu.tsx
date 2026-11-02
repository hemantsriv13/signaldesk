"use client";

import * as React from "react";
import { NavigationMenu as NavigationMenuPrimitive } from "@base-ui/react/navigation-menu";
import { cva } from "class-variance-authority";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";
import { popoverSurface, popupMotion } from "./_shared";

// Base UI accepts a state function for className; these wrappers merge it with
// cn(), so they take a plain string.
type WithClassName<P> = Omit<P, "className"> & { className?: string };

/**
 * Cream editorial NavigationMenu: a row of site sections whose panels open in
 * one shared paper viewport. The viewport is rendered for you after the list.
 */
function NavigationMenu({
  className,
  children,
  ...props
}: WithClassName<NavigationMenuPrimitive.Root.Props>) {
  return (
    <NavigationMenuPrimitive.Root
      data-slot="navigation-menu"
      className={cn(
        "relative z-10 flex max-w-max flex-1 items-center justify-center",
        className,
      )}
      {...props}
    >
      {children}
      <NavigationMenuViewport />
    </NavigationMenuPrimitive.Root>
  );
}
NavigationMenu.displayName = "NavigationMenu";

/** The row of top-level items, spaced 0.25rem apart. */
function NavigationMenuList({
  className,
  ...props
}: WithClassName<NavigationMenuPrimitive.List.Props>) {
  return (
    <NavigationMenuPrimitive.List
      data-slot="navigation-menu-list"
      className={cn(
        "flex flex-1 list-none items-center justify-center gap-1",
        className,
      )}
      {...props}
    />
  );
}
NavigationMenuList.displayName = "NavigationMenuList";

/** One top-level section: a trigger and its panel, or a single link. */
const NavigationMenuItem = NavigationMenuPrimitive.Item;

/**
 * The top-level tab: secondary ink at rest, an oat wash under the pointer,
 * and the deeper oat tab while its panel is open. Apply it to a plain
 * top-level link too, so links and triggers line up.
 */
const navigationMenuTriggerStyle = cva(
  [
    "group inline-flex h-9 w-max select-none items-center justify-center gap-1.5 rounded-md px-3.5 text-sm font-medium text-(--foreground-secondary)",
    "transition-colors duration-fast ease-out",
    "hover:bg-secondary hover:text-foreground",
    "outline-none focus-visible:ring-3 focus-visible:ring-ring",
    "data-[popup-open]:bg-muted data-[popup-open]:text-foreground",
    "data-[active]:text-foreground",
    "disabled:pointer-events-none disabled:text-(--foreground-disabled)",
  ].join(" "),
);

/** A top-level trigger with a caret that turns over while its panel is open. */
function NavigationMenuTrigger({
  className,
  children,
  ...props
}: WithClassName<NavigationMenuPrimitive.Trigger.Props>) {
  return (
    <NavigationMenuPrimitive.Trigger
      data-slot="navigation-menu-trigger"
      className={cn(navigationMenuTriggerStyle(), className)}
      {...props}
    >
      {children}
      <Icon
        icon="ph:caret-down"
        className="size-3.5 text-muted-foreground transition-transform duration-fast ease-out group-data-[popup-open]:rotate-180 motion-reduce:transition-none"
        aria-hidden="true"
      />
    </NavigationMenuPrimitive.Trigger>
  );
}
NavigationMenuTrigger.displayName = "NavigationMenuTrigger";

/**
 * One section's panel. Moving between sections slides the new panel in a
 * short way from the side the pointer came from while the old one fades out.
 */
function NavigationMenuContent({
  className,
  ...props
}: WithClassName<NavigationMenuPrimitive.Content.Props>) {
  return (
    <NavigationMenuPrimitive.Content
      data-slot="navigation-menu-content"
      className={cn(
        "w-full p-2 md:absolute md:start-0 md:top-0 md:w-auto",
        "transition-[opacity,translate] duration-fast ease-out motion-reduce:transition-none",
        "data-[starting-style]:opacity-0 data-[ending-style]:opacity-0",
        "data-[starting-style]:data-[activation-direction=left]:-translate-x-4",
        "data-[starting-style]:data-[activation-direction=right]:translate-x-4",
        "data-[ending-style]:data-[activation-direction=left]:translate-x-4",
        "data-[ending-style]:data-[activation-direction=right]:-translate-x-4",
        className,
      )}
      {...props}
    />
  );
}
NavigationMenuContent.displayName = "NavigationMenuContent";

/**
 * A link inside a panel: a block with a 0.5rem corner and an oat wash under
 * the pointer. Its first line reads in ink and the rest in the muted caption
 * colour; the current page reads in medium weight.
 */
function NavigationMenuLink({
  className,
  ...props
}: WithClassName<NavigationMenuPrimitive.Link.Props>) {
  return (
    <NavigationMenuPrimitive.Link
      data-slot="navigation-menu-link"
      className={cn(
        "flex flex-col gap-1 rounded-md p-3 text-sm leading-snug text-foreground outline-none",
        "transition-colors duration-fast ease-out",
        "hover:bg-accent focus-visible:bg-accent",
        "data-[active]:font-medium",
        className,
      )}
      {...props}
    />
  );
}
NavigationMenuLink.displayName = "NavigationMenuLink";

/**
 * The shared panel window: the lightest paper with a 0.75rem corner and a
 * warm hairline inside its soft shadow. It resizes to fit each section as
 * you move along the row, and settles from the trigger when it first opens.
 */
function NavigationMenuViewport({
  className,
  ...props
}: WithClassName<NavigationMenuPrimitive.Viewport.Props>) {
  return (
    <NavigationMenuPrimitive.Portal>
      <NavigationMenuPrimitive.Positioner
        sideOffset={8}
        collisionPadding={16}
        className="isolate z-50"
      >
        <NavigationMenuPrimitive.Popup
          data-slot="navigation-menu-popup"
          className={cn(
            popoverSurface,
            popupMotion,
            "relative h-(--popup-height) w-(--popup-width) max-w-(--available-width) overflow-hidden",
            "transition-[opacity,scale,width,height]",
          )}
        >
          <NavigationMenuPrimitive.Viewport
            data-slot="navigation-menu-viewport"
            className={cn("relative size-full overflow-hidden", className)}
            {...props}
          />
        </NavigationMenuPrimitive.Popup>
      </NavigationMenuPrimitive.Positioner>
    </NavigationMenuPrimitive.Portal>
  );
}
NavigationMenuViewport.displayName = "NavigationMenuViewport";

/**
 * Kept so existing imports still compile. The Base UI navigation menu has no
 * part that tracks the active trigger along the list, so this renders nothing.
 */
function NavigationMenuIndicator(props: React.ComponentPropsWithoutRef<"div">) {
  void props;
  return null;
}
NavigationMenuIndicator.displayName = "NavigationMenuIndicator";

export {
  navigationMenuTriggerStyle,
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuContent,
  NavigationMenuTrigger,
  NavigationMenuLink,
  NavigationMenuIndicator,
  NavigationMenuViewport,
};
