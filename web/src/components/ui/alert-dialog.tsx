"use client";

import * as React from "react";
import { AlertDialog as AlertDialogPrimitive } from "@base-ui/react/alert-dialog";

import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

// Base UI accepts a state function for className; these wrappers merge it with
// cn(), so they take a plain string.
type WithClassName<P> = Omit<P, "className"> & { className?: string };

/** Cream editorial AlertDialog root: a modal that waits for a decision. */
const AlertDialog = AlertDialogPrimitive.Root;

/** The control that opens the alert dialog. */
const AlertDialogTrigger = AlertDialogPrimitive.Trigger;

/** Moves the alert dialog to the end of the document body. */
const AlertDialogPortal = AlertDialogPrimitive.Portal;

/**
 * The scrim: a warm ink veil that fades in behind the alert. A click on it
 * does not dismiss the alert.
 */
const AlertDialogOverlay = React.forwardRef<
  HTMLDivElement,
  WithClassName<AlertDialogPrimitive.Backdrop.Props>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Backdrop
    ref={ref}
    data-slot="alert-dialog-overlay"
    className={cn(
      "fixed inset-0 z-50 bg-(--scrim)",
      "transition-opacity duration-fast ease-out",
      "data-[starting-style]:opacity-0 data-[ending-style]:opacity-0",
      className,
    )}
    {...props}
  />
));
AlertDialogOverlay.displayName = "AlertDialogOverlay";

/**
 * Cream editorial alert window: a sheet of cream paper with a 1.5rem corner
 * and the overlay shadow. It has no close button, so the reader answers
 * with one of the two footer buttons.
 */
const AlertDialogContent = React.forwardRef<
  HTMLDivElement,
  WithClassName<AlertDialogPrimitive.Popup.Props>
>(({ className, ...props }, ref) => (
  <AlertDialogPortal>
    <AlertDialogOverlay />
    <AlertDialogPrimitive.Popup
      ref={ref}
      data-slot="alert-dialog-content"
      className={cn(
        "fixed top-1/2 left-1/2 z-50 grid w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 gap-5",
        "rounded-2xl bg-background p-7 text-foreground shadow-(--shadow-overlay) outline-none",
        "transition-[opacity,scale] duration-fast ease-out",
        "data-[starting-style]:scale-98 data-[starting-style]:opacity-0",
        "data-[ending-style]:scale-98 data-[ending-style]:opacity-0",
        className,
      )}
      {...props}
    />
  </AlertDialogPortal>
));
AlertDialogContent.displayName = "AlertDialogContent";

/** The question block at the top of the alert. */
const AlertDialogHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    data-slot="alert-dialog-header"
    className={cn("flex flex-col gap-2 text-start", className)}
    {...props}
  />
);
AlertDialogHeader.displayName = "AlertDialogHeader";

/**
 * The answer row. On a phone the confirm button sits on top of Cancel; from
 * the small breakpoint both sit in a row at the end.
 */
const AlertDialogFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    data-slot="alert-dialog-footer"
    className={cn(
      "flex flex-col-reverse gap-2 sm:flex-row sm:justify-end",
      className,
    )}
    {...props}
  />
);
AlertDialogFooter.displayName = "AlertDialogFooter";

/** The alert question, set in the serif at medium weight. */
const AlertDialogTitle = React.forwardRef<
  HTMLHeadingElement,
  WithClassName<AlertDialogPrimitive.Title.Props>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Title
    ref={ref}
    data-slot="alert-dialog-title"
    className={cn(
      "font-serif text-2xl font-medium leading-snug tracking-tight text-foreground",
      className,
    )}
    {...props}
  />
));
AlertDialogTitle.displayName = "AlertDialogTitle";

/** What happens if the reader confirms, in the softer secondary ink. */
const AlertDialogDescription = React.forwardRef<
  HTMLParagraphElement,
  WithClassName<AlertDialogPrimitive.Description.Props>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Description
    ref={ref}
    data-slot="alert-dialog-description"
    className={cn("text-sm leading-relaxed text-(--foreground-secondary)", className)}
    {...props}
  />
));
AlertDialogDescription.displayName = "AlertDialogDescription";

/** The confirm button: the terracotta action, the one coloured thing in the alert. */
const AlertDialogAction = React.forwardRef<
  HTMLButtonElement,
  WithClassName<AlertDialogPrimitive.Close.Props>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Close
    ref={ref}
    data-slot="alert-dialog-action"
    className={cn(buttonVariants(), className)}
    {...props}
  />
));
AlertDialogAction.displayName = "AlertDialogAction";

/** The way out: a cream outline block beside the terracotta confirm. */
const AlertDialogCancel = React.forwardRef<
  HTMLButtonElement,
  WithClassName<AlertDialogPrimitive.Close.Props>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Close
    ref={ref}
    data-slot="alert-dialog-cancel"
    className={cn(buttonVariants({ variant: "outline" }), className)}
    {...props}
  />
));
AlertDialogCancel.displayName = "AlertDialogCancel";

export {
  AlertDialog,
  AlertDialogPortal,
  AlertDialogOverlay,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
};
