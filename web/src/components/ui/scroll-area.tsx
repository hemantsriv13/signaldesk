"use client";

import * as React from "react";
import { ScrollArea as ScrollAreaPrimitive } from "@base-ui/react/scroll-area";

import { cn } from "@/lib/utils";

type WithClassName<P> = Omit<P, "className"> & { className?: string };

/**
 * Cream editorial ScrollArea: content that scrolls inside its own box. The
 * scrollbar stays out of the way until the pointer is over it or the content
 * moves, then shows a slim warm thumb that darkens under the pointer.
 */
const ScrollArea = React.forwardRef<
  HTMLDivElement,
  WithClassName<ScrollAreaPrimitive.Root.Props>
>(({ className, children, ...props }, ref) => (
  <ScrollAreaPrimitive.Root
    data-slot="scroll-area"
    ref={ref}
    className={cn("relative overflow-hidden", className)}
    {...props}
  >
    <ScrollAreaPrimitive.Viewport
      data-slot="scroll-area-viewport"
      className="size-full rounded-[inherit] outline-none focus-visible:ring-3 focus-visible:ring-ring"
    >
      <ScrollAreaPrimitive.Content>{children}</ScrollAreaPrimitive.Content>
    </ScrollAreaPrimitive.Viewport>
    <ScrollBar />
    <ScrollAreaPrimitive.Corner data-slot="scroll-area-corner" />
  </ScrollAreaPrimitive.Root>
));
ScrollArea.displayName = "ScrollArea";

/** One scrollbar for a ScrollArea. Add `orientation="horizontal"` for a sideways one. */
const ScrollBar = React.forwardRef<
  HTMLDivElement,
  WithClassName<ScrollAreaPrimitive.Scrollbar.Props>
>(({ className, orientation = "vertical", ...props }, ref) => (
  <ScrollAreaPrimitive.Scrollbar
    data-slot="scroll-area-scrollbar"
    ref={ref}
    orientation={orientation}
    className={cn(
      "flex touch-none select-none p-0.5 opacity-0 transition-opacity duration-fast ease-out",
      "data-[hovering]:opacity-100 data-[scrolling]:opacity-100",
      "data-[orientation=vertical]:h-full data-[orientation=vertical]:w-2",
      "data-[orientation=horizontal]:h-2 data-[orientation=horizontal]:flex-col",
      className,
    )}
    {...props}
  >
    <ScrollAreaPrimitive.Thumb
      data-slot="scroll-area-thumb"
      className="relative flex-1 rounded-full bg-(--line-strong) transition-colors duration-fast ease-out hover:bg-(--control)"
    />
  </ScrollAreaPrimitive.Scrollbar>
));
ScrollBar.displayName = "ScrollBar";

export { ScrollArea, ScrollBar };
