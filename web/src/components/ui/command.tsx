"use client";

import * as React from "react";
import { Command as CommandPrimitive } from "cmdk";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";
import { formFieldBase, formFieldSingleLine, popoverSurface } from "./_shared";
import { Dialog, DialogContent, DialogTitle } from "./dialog";

/**
 * Cream editorial Command: a search field over a filtered list of actions,
 * set on the floating paper panel with a 0.75rem corner.
 */
const Command = React.forwardRef<
  React.ElementRef<typeof CommandPrimitive>,
  React.ComponentPropsWithoutRef<typeof CommandPrimitive>
>(({ className, ...props }, ref) => (
  <CommandPrimitive
    ref={ref}
    data-slot="command"
    className={cn(
      popoverSurface,
      "flex size-full flex-col overflow-hidden",
      className,
    )}
    {...props}
  />
));
Command.displayName = "Command";

// Dialog.Root accepts a render function as its child; Command takes nodes only.
type CommandDialogProps = Omit<
  React.ComponentProps<typeof Dialog>,
  "children"
> & {
  children?: React.ReactNode;
};

/**
 * The command palette: the command list inside a dialog window, with a
 * hidden title for screen readers. Escape or a click on the scrim closes it.
 */
const CommandDialog = ({ children, ...props }: CommandDialogProps) => (
  <Dialog {...props}>
    <DialogContent className="max-w-xl gap-0 overflow-hidden p-0 [&>[data-slot=dialog-close]]:hidden">
      <DialogTitle className="sr-only">Command menu</DialogTitle>
      <Command className="rounded-none bg-transparent shadow-none [&_[cmdk-list]]:max-h-96">
        {children}
      </Command>
    </DialogContent>
  </Dialog>
);

/**
 * The search field: the paper box every text field uses, with a muted
 * magnifying glass at the start. It sits inset from the panel's edges.
 */
const CommandInput = React.forwardRef<
  React.ElementRef<typeof CommandPrimitive.Input>,
  React.ComponentPropsWithoutRef<typeof CommandPrimitive.Input>
>(({ className, ...props }, ref) => (
  <div
    data-slot="command-input-wrapper"
    className="relative flex items-center p-1 pb-0.5"
    cmdk-input-wrapper=""
  >
    <Icon
      icon="ph:magnifying-glass"
      className="pointer-events-none absolute start-4 size-4 text-muted-foreground"
      aria-hidden="true"
    />
    <CommandPrimitive.Input
      ref={ref}
      data-slot="command-input"
      className={cn(formFieldBase, formFieldSingleLine, "ps-9", className)}
      {...props}
    />
  </div>
));
CommandInput.displayName = "CommandInput";

/** The scrolling list of results under the search field. */
const CommandList = React.forwardRef<
  React.ElementRef<typeof CommandPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof CommandPrimitive.List>
>(({ className, ...props }, ref) => (
  <CommandPrimitive.List
    ref={ref}
    data-slot="command-list"
    className={cn(
      "max-h-72 scroll-py-1 overflow-y-auto overflow-x-hidden p-1",
      className,
    )}
    {...props}
  />
));
CommandList.displayName = "CommandList";

/** The line shown when nothing matches the search, in muted type. */
const CommandEmpty = React.forwardRef<
  React.ElementRef<typeof CommandPrimitive.Empty>,
  React.ComponentPropsWithoutRef<typeof CommandPrimitive.Empty>
>(({ className, ...props }, ref) => (
  <CommandPrimitive.Empty
    ref={ref}
    data-slot="command-empty"
    className={cn("py-6 text-center text-sm text-muted-foreground", className)}
    {...props}
  />
));
CommandEmpty.displayName = "CommandEmpty";

/** A titled group of results. The heading is small muted type. */
const CommandGroup = React.forwardRef<
  React.ElementRef<typeof CommandPrimitive.Group>,
  React.ComponentPropsWithoutRef<typeof CommandPrimitive.Group>
>(({ className, ...props }, ref) => (
  <CommandPrimitive.Group
    ref={ref}
    data-slot="command-group"
    className={cn(
      "overflow-hidden text-foreground",
      "[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground",
      className,
    )}
    {...props}
  />
));
CommandGroup.displayName = "CommandGroup";

/** A hairline between groups that runs to the list's edges. */
const CommandSeparator = React.forwardRef<
  React.ElementRef<typeof CommandPrimitive.Separator>,
  React.ComponentPropsWithoutRef<typeof CommandPrimitive.Separator>
>(({ className, ...props }, ref) => (
  <CommandPrimitive.Separator
    ref={ref}
    data-slot="command-separator"
    className={cn("-mx-1 my-1 h-px bg-border", className)}
    {...props}
  />
));
CommandSeparator.displayName = "CommandSeparator";

/**
 * A result row with the same shape as a menu row: a 0.5rem corner that
 * fills with oat when selected. The search list marks its state with aria
 * attributes, so the row reads those.
 */
const CommandItem = React.forwardRef<
  React.ElementRef<typeof CommandPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof CommandPrimitive.Item>
>(({ className, ...props }, ref) => (
  <CommandPrimitive.Item
    ref={ref}
    data-slot="command-item"
    className={cn(
      "relative flex min-h-8 cursor-default select-none items-center gap-2 rounded-md px-2.5 py-1.5 text-sm outline-none",
      "transition-colors duration-fast",
      "aria-selected:bg-accent aria-selected:text-accent-foreground",
      "aria-disabled:pointer-events-none aria-disabled:text-(--foreground-disabled)",
      "[&_svg]:size-4 [&_svg]:shrink-0",
      className,
    )}
    {...props}
  />
));
CommandItem.displayName = "CommandItem";

/** The keyboard shortcut at the end of a row, in small muted type. */
const CommandShortcut = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) => (
  <span
    data-slot="command-shortcut"
    className={cn("ms-auto ps-4 text-xs tracking-wide text-muted-foreground", className)}
    {...props}
  />
);
CommandShortcut.displayName = "CommandShortcut";

export {
  Command,
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandShortcut,
  CommandSeparator,
};
