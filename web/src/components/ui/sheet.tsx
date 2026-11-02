"use client";

import * as React from "react";
import { Dialog as SheetPrimitive } from "@base-ui/react/dialog";
import { cva, type VariantProps } from "class-variance-authority";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

// Base UI accepts a state function for className; these wrappers merge it with
// cn(), so they take a plain string.
type WithClassName<P> = Omit<P, "className"> & { className?: string };

/** Cream editorial Sheet root: a page of paper that slides in from one edge. */
const Sheet = SheetPrimitive.Root;

/** The control that opens the sheet. */
const SheetTrigger = SheetPrimitive.Trigger;

/** Closes the sheet. Use it to wrap a Cancel or Done button. */
const SheetClose = SheetPrimitive.Close;

/** Moves the sheet to the end of the document body. */
const SheetPortal = SheetPrimitive.Portal;

/** The warm scrim behind the sheet. It fades in and out with the panel. */
const SheetOverlay = React.forwardRef<
  HTMLDivElement,
  WithClassName<SheetPrimitive.Backdrop.Props>
>(({ className, ...props }, ref) => (
  <SheetPrimitive.Backdrop
    ref={ref}
    data-slot="sheet-overlay"
    className={cn(
      "fixed inset-0 z-50 bg-(--scrim)",
      "transition-opacity duration-base ease-out motion-reduce:transition-none",
      "data-[starting-style]:opacity-0 data-[ending-style]:opacity-0",
      className,
    )}
    {...props}
  />
));
SheetOverlay.displayName = "SheetOverlay";

/**
 * Each sheet runs flush to its edge and rounds only the inner edge with a
 * 1.5rem corner. It slides in on a short ease-out.
 */
const sheetVariants = cva(
  [
    "fixed z-50 flex flex-col gap-4 bg-background p-6 text-foreground shadow-(--shadow-overlay) outline-none",
    "transition-[translate,opacity] duration-base ease-out motion-reduce:transition-none",
    "data-[starting-style]:opacity-0 data-[ending-style]:opacity-0",
  ].join(" "),
  {
    variants: {
      side: {
        top: "inset-x-0 top-0 max-h-[85vh] rounded-b-2xl data-[starting-style]:-translate-y-full data-[ending-style]:-translate-y-full",
        bottom:
          "inset-x-0 bottom-0 max-h-[85vh] rounded-t-2xl data-[starting-style]:translate-y-full data-[ending-style]:translate-y-full",
        left: "inset-y-0 left-0 h-full w-3/4 max-w-sm rounded-e-2xl data-[starting-style]:-translate-x-full data-[ending-style]:-translate-x-full",
        right:
          "inset-y-0 right-0 h-full w-3/4 max-w-sm rounded-s-2xl data-[starting-style]:translate-x-full data-[ending-style]:translate-x-full",
      },
    },
    defaultVariants: {
      side: "right",
    },
  },
);

interface SheetContentProps
  extends WithClassName<SheetPrimitive.Popup.Props>,
    VariantProps<typeof sheetVariants> {}

/**
 * Cream editorial sheet panel: cream paper on the overlay shadow. A ghost
 * icon button in the top corner closes it.
 */
const SheetContent = React.forwardRef<HTMLDivElement, SheetContentProps>(
  ({ side = "right", className, children, ...props }, ref) => (
    <SheetPortal>
      <SheetOverlay />
      <SheetPrimitive.Popup
        ref={ref}
        data-slot="sheet-content"
        data-side={side}
        className={cn(sheetVariants({ side }), className)}
        {...props}
      >
        {children}
        <SheetPrimitive.Close
          data-slot="sheet-close"
          className={cn(
            buttonVariants({ variant: "ghost", size: "icon-sm" }),
            "absolute end-4 top-4 text-muted-foreground hover:text-foreground",
          )}
        >
          <Icon icon="ph:x" className="size-4" aria-hidden="true" />
          <span className="sr-only">Close</span>
        </SheetPrimitive.Close>
      </SheetPrimitive.Popup>
    </SheetPortal>
  ),
);
SheetContent.displayName = "SheetContent";

/** The title block at the top of a sheet. It leaves room for the close button. */
const SheetHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    data-slot="sheet-header"
    className={cn("flex flex-col gap-1.5 pe-8 text-start", className)}
    {...props}
  />
);
SheetHeader.displayName = "SheetHeader";

/** The action row, pinned to the foot of the sheet. */
const SheetFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    data-slot="sheet-footer"
    className={cn(
      "mt-auto flex flex-col-reverse gap-2 sm:flex-row sm:justify-end",
      className,
    )}
    {...props}
  />
);
SheetFooter.displayName = "SheetFooter";

/** The sheet title, set in the serif at a reading size. */
const SheetTitle = React.forwardRef<
  HTMLHeadingElement,
  WithClassName<SheetPrimitive.Title.Props>
>(({ className, ...props }, ref) => (
  <SheetPrimitive.Title
    ref={ref}
    data-slot="sheet-title"
    className={cn(
      "font-serif text-2xl font-medium leading-tight tracking-tight text-foreground",
      className,
    )}
    {...props}
  />
));
SheetTitle.displayName = "SheetTitle";

/** The supporting line under the title, in the caption ink. */
const SheetDescription = React.forwardRef<
  HTMLParagraphElement,
  WithClassName<SheetPrimitive.Description.Props>
>(({ className, ...props }, ref) => (
  <SheetPrimitive.Description
    ref={ref}
    data-slot="sheet-description"
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
));
SheetDescription.displayName = "SheetDescription";

export {
  Sheet,
  SheetPortal,
  SheetOverlay,
  SheetTrigger,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
};
