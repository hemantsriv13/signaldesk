"use client";

import * as React from "react";
import { Toast as ToastPrimitive } from "@base-ui/react/toast";
import { cva, type VariantProps } from "class-variance-authority";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import { popoverSurface } from "./_shared";

// Base UI accepts a state function for className; these wrappers merge it with
// cn(), so they take a plain string.
type WithClassName<P> = Omit<P, "className"> & { className?: string };

/** Holds the toast queue. The Toaster passes it the shared toast manager. */
const ToastProvider = ToastPrimitive.Provider;

/**
 * Where toasts appear: the bottom of the screen on a phone, and the bottom
 * end corner from the small breakpoint, 24rem wide at most.
 */
const ToastViewport = React.forwardRef<
  HTMLDivElement,
  WithClassName<ToastPrimitive.Viewport.Props>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Portal>
    <ToastPrimitive.Viewport
      ref={ref}
      data-slot="toast-viewport"
      className={cn(
        "fixed inset-x-0 bottom-0 z-100 flex flex-col gap-2 p-4 outline-none",
        "sm:start-auto sm:w-full sm:max-w-sm",
        className,
      )}
      {...props}
    />
  </ToastPrimitive.Portal>
));
ToastViewport.displayName = "ToastViewport";

/**
 * A toast is the floating paper panel shared by menus and popovers. It rises
 * a little as it fades in and follows the finger when swiped away. The
 * destructive toast takes the pale red tint with red text.
 */
const toastVariants = cva(
  [
    popoverSurface,
    "group pointer-events-auto relative flex w-full items-center justify-between gap-3 p-4 pe-11",
    "transition-[opacity,translate] duration-fast ease-out motion-reduce:transition-none",
    "data-[starting-style]:translate-y-2 data-[starting-style]:opacity-0",
    "data-[ending-style]:opacity-0 data-[ending-style]:duration-fast",
    "data-[ending-style]:data-[swipe-direction=right]:translate-x-full",
    "data-[swiping]:translate-x-(--toast-swipe-movement-x) data-[swiping]:transition-none",
  ].join(" "),
  {
    variants: {
      variant: {
        default: "",
        destructive: "bg-(--destructive-tint) text-(--destructive-text)",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

/** Cream editorial toast: a short notice that floats over the page and leaves on its own. */
const Toast = React.forwardRef<
  HTMLDivElement,
  WithClassName<ToastPrimitive.Root.Props> & VariantProps<typeof toastVariants>
>(({ className, variant, swipeDirection = "right", ...props }, ref) => (
  <ToastPrimitive.Root
    ref={ref}
    data-slot="toast"
    data-variant={variant ?? "default"}
    swipeDirection={swipeDirection}
    className={cn(toastVariants({ variant }), className)}
    {...props}
  />
));
Toast.displayName = "Toast";

/** The toast's one follow-up action: a small hairline button at the end. */
const ToastAction = React.forwardRef<
  HTMLButtonElement,
  WithClassName<ToastPrimitive.Action.Props>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Action
    ref={ref}
    data-slot="toast-action"
    className={cn(buttonVariants({ variant: "outline", size: "sm" }), className)}
    {...props}
  />
));
ToastAction.displayName = "ToastAction";

/** A small close button in the top corner of the toast. */
const ToastClose = React.forwardRef<
  HTMLButtonElement,
  WithClassName<ToastPrimitive.Close.Props>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Close
    ref={ref}
    data-slot="toast-close"
    aria-label="Close"
    className={cn(
      "absolute end-2 top-2 inline-flex size-7 items-center justify-center rounded-md text-muted-foreground",
      "transition-colors duration-fast ease-out hover:bg-secondary hover:text-foreground",
      "outline-none focus-visible:ring-3 focus-visible:ring-ring",
      "group-data-[variant=destructive]:text-(--destructive-text) group-data-[variant=destructive]:hover:bg-background/60",
      className,
    )}
    {...props}
  >
    <Icon icon="ph:x" className="size-4" aria-hidden="true" />
  </ToastPrimitive.Close>
));
ToastClose.displayName = "ToastClose";

/** The toast headline: small sans type in the toast's own ink. */
const ToastTitle = React.forwardRef<
  HTMLHeadingElement,
  WithClassName<ToastPrimitive.Title.Props>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Title
    ref={ref}
    data-slot="toast-title"
    className={cn("text-sm font-medium leading-snug", className)}
    {...props}
  />
));
ToastTitle.displayName = "ToastTitle";

/** The detail line under the headline, in the secondary ink. */
const ToastDescription = React.forwardRef<
  HTMLParagraphElement,
  WithClassName<ToastPrimitive.Description.Props>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Description
    ref={ref}
    data-slot="toast-description"
    className={cn(
      "text-sm text-(--foreground-secondary) group-data-[variant=destructive]:text-(--destructive-text)",
      className,
    )}
    {...props}
  />
));
ToastDescription.displayName = "ToastDescription";

/** Props for one toast, as the toast hook stores them. */
type ToastProps = React.ComponentPropsWithoutRef<typeof Toast>;

/** The element type the toast hook accepts as a toast's action. */
type ToastActionElement = React.ReactElement<typeof ToastAction>;

export {
  type ToastProps,
  type ToastActionElement,
  ToastProvider,
  ToastViewport,
  Toast,
  ToastTitle,
  ToastDescription,
  ToastClose,
  ToastAction,
};
