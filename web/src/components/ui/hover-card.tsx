"use client";

import * as React from "react";
import { PreviewCard as PreviewCardPrimitive } from "@base-ui/react/preview-card";

import { cn } from "@/lib/utils";
import { popoverSurface, popupMotion } from "./_shared";

// Base UI accepts a state function for className; these wrappers merge it with
// cn(), so they take a plain string.
type WithClassName<P> = Omit<P, "className"> & { className?: string };

/** Cream editorial HoverCard root: a preview that opens while the pointer rests on a link. */
const HoverCard = PreviewCardPrimitive.Root;

/** The link or element that shows the preview on hover and focus. */
const HoverCardTrigger = PreviewCardPrimitive.Trigger;

/**
 * Cream editorial hover card: the lightest paper panel, 18rem wide, with a
 * warm hairline folded into its soft shadow. It settles from the link it
 * previews, so it reads as a margin note rather than a new page.
 */
const HoverCardContent = React.forwardRef<
  HTMLDivElement,
  WithClassName<PreviewCardPrimitive.Popup.Props> &
    Pick<
      PreviewCardPrimitive.Positioner.Props,
      "align" | "alignOffset" | "side" | "sideOffset"
    >
>(
  (
    {
      className,
      align = "center",
      alignOffset,
      side,
      sideOffset = 8,
      ...props
    },
    ref,
  ) => (
    <PreviewCardPrimitive.Portal>
      <PreviewCardPrimitive.Positioner
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
        className="isolate z-50 outline-none"
      >
        <PreviewCardPrimitive.Popup
          ref={ref}
          data-slot="hover-card-content"
          className={cn(
            popoverSurface,
            popupMotion,
            "flex w-72 max-w-(--available-width) flex-col gap-2 p-4 text-sm leading-relaxed text-(--foreground-secondary)",
            className,
          )}
          {...props}
        />
      </PreviewCardPrimitive.Positioner>
    </PreviewCardPrimitive.Portal>
  ),
);
HoverCardContent.displayName = "HoverCardContent";

export { HoverCard, HoverCardTrigger, HoverCardContent };
