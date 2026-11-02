"use client";

import * as React from "react";
import { Tabs as TabsPrimitive } from "@base-ui/react/tabs";

import { cn } from "@/lib/utils";

type WithClassName<P> = Omit<P, "className"> & { className?: string };

const Tabs = TabsPrimitive.Root;

/**
 * Cream editorial TabsList: a row of category tabs set straight on the
 * paper, with no tray behind them.
 */
const TabsList = React.forwardRef<
  HTMLDivElement,
  WithClassName<TabsPrimitive.List.Props>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    data-slot="tabs-list"
    className={cn(
      "inline-flex items-center gap-1 text-muted-foreground",
      className,
    )}
    {...props}
  />
));
TabsList.displayName = "TabsList";

/**
 * Cream editorial TabsTrigger: caption ink that darkens on hover. The active
 * tab sits on an oat block with ink type, the way a category filter reads.
 */
const TabsTrigger = React.forwardRef<
  HTMLButtonElement,
  WithClassName<TabsPrimitive.Tab.Props>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Tab
    ref={ref}
    data-slot="tabs-trigger"
    className={cn(
      "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md px-3.5 py-1.5",
      "text-sm font-medium text-muted-foreground",
      "transition-colors duration-fast ease-out hover:text-foreground",
      "data-[active]:bg-muted data-[active]:text-foreground",
      "outline-none focus-visible:ring-3 focus-visible:ring-ring",
      "data-[disabled]:cursor-not-allowed data-[disabled]:text-(--foreground-disabled)",
      "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = "TabsTrigger";

/** Cream editorial TabsContent: the active panel, set a little below the tabs. */
const TabsContent = React.forwardRef<
  HTMLDivElement,
  WithClassName<TabsPrimitive.Panel.Props>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Panel
    ref={ref}
    data-slot="tabs-content"
    className={cn(
      "mt-4 rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring",
      className,
    )}
    {...props}
  />
));
TabsContent.displayName = "TabsContent";

export { Tabs, TabsList, TabsTrigger, TabsContent };
