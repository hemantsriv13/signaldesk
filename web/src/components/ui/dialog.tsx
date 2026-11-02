"use client";

import * as React from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

// Base UI accepts a state function for className; these wrappers merge it with
// cn(), so they take a plain string.
type WithClassName<P> = Omit<P, "className"> & { className?: string };

/** Cream editorial Dialog root: owns the open state of one modal window. */
const Dialog = DialogPrimitive.Root;

/** The control that opens the dialog. */
const DialogTrigger = DialogPrimitive.Trigger;

/** Moves the dialog to the end of the document body. */
const DialogPortal = DialogPrimitive.Portal;

/** Closes the dialog. Use it to wrap a Cancel or Done button. */
const DialogClose = DialogPrimitive.Close;

/** The scrim: warm ink at low strength, so the page dims but stays legible behind the sheet. */
const DialogOverlay = React.forwardRef<
  HTMLDivElement,
  WithClassName<DialogPrimitive.Backdrop.Props>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Backdrop
    ref={ref}
    data-slot="dialog-overlay"
    className={cn(
      "fixed inset-0 z-50 bg-(--scrim)",
      "transition-opacity duration-base ease-out",
      "data-[starting-style]:opacity-0 data-[ending-style]:opacity-0",
      className,
    )}
    {...props}
  />
));
DialogOverlay.displayName = "DialogOverlay";

/**
 * Cream editorial dialog window: a sheet of cream paper with a 1.5rem corner
 * and the overlay shadow. It fades in place; nothing scales or lifts. A quiet
 * ghost button in the top corner closes it.
 */
const DialogContent = React.forwardRef<
  HTMLDivElement,
  WithClassName<DialogPrimitive.Popup.Props>
>(({ className, children, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Popup
      ref={ref}
      data-slot="dialog-content"
      className={cn(
        "fixed top-1/2 left-1/2 z-50 grid w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 gap-5",
        "rounded-2xl bg-background p-7 text-foreground shadow-(--shadow-overlay) outline-none",
        "transition-opacity duration-base ease-out",
        "data-[starting-style]:opacity-0 data-[ending-style]:opacity-0",
        className,
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close
        data-slot="dialog-close"
        className={cn(
          buttonVariants({ variant: "ghost", size: "icon-sm" }),
          "absolute end-4 top-4 text-muted-foreground hover:text-foreground",
        )}
      >
        <Icon icon="ph:x" className="size-4" aria-hidden="true" />
        <span className="sr-only">Close</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Popup>
  </DialogPortal>
));
DialogContent.displayName = "DialogContent";

/** The heading block at the top of a dialog. It leaves room for the close button. */
const DialogHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    data-slot="dialog-header"
    className={cn("flex flex-col gap-2 pe-8 text-start", className)}
    {...props}
  />
);
DialogHeader.displayName = "DialogHeader";

/**
 * The action row at the foot of a dialog. Buttons stack on a phone with the
 * main action on top, and sit in a row at the end from the small breakpoint.
 */
const DialogFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    data-slot="dialog-footer"
    className={cn(
      "flex flex-col-reverse gap-2 pt-1 sm:flex-row sm:justify-end",
      className,
    )}
    {...props}
  />
);
DialogFooter.displayName = "DialogFooter";

/** The dialog title, set in the serif at a reading size and never bolder than medium. */
const DialogTitle = React.forwardRef<
  HTMLHeadingElement,
  WithClassName<DialogPrimitive.Title.Props>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    data-slot="dialog-title"
    className={cn(
      "font-serif text-2xl font-medium leading-snug tracking-tight text-foreground",
      className,
    )}
    {...props}
  />
));
DialogTitle.displayName = "DialogTitle";

/** The supporting line under the title, in the secondary ink. */
const DialogDescription = React.forwardRef<
  HTMLParagraphElement,
  WithClassName<DialogPrimitive.Description.Props>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    data-slot="dialog-description"
    className={cn("text-sm leading-relaxed text-(--foreground-secondary)", className)}
    {...props}
  />
));
DialogDescription.displayName = "DialogDescription";

export {
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogClose,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
};
