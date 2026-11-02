"use client";

import * as React from "react";
import { Accordion as AccordionPrimitive } from "@base-ui/react/accordion";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";

type WithClassName<P> = Omit<P, "className"> & { className?: string };

const Accordion = AccordionPrimitive.Root;

/** Cream editorial AccordionItem: one entry, ruled off by a warm hairline, with none under the last. */
const AccordionItem = React.forwardRef<
  HTMLDivElement,
  WithClassName<AccordionPrimitive.Item.Props>
>(({ className, ...props }, ref) => (
  <AccordionPrimitive.Item
    ref={ref}
    data-slot="accordion-item"
    className={cn("border-b border-border last:border-b-0", className)}
    {...props}
  />
));
AccordionItem.displayName = "AccordionItem";

/**
 * Cream editorial AccordionTrigger: the question in ink at the body size.
 * A muted caret at the end turns over as the answer opens. Hover only
 * darkens the caret, so the row stays calm.
 */
const AccordionTrigger = React.forwardRef<
  HTMLButtonElement,
  WithClassName<AccordionPrimitive.Trigger.Props>
>(({ className, children, ...props }, ref) => (
  <AccordionPrimitive.Header data-slot="accordion-header" className="flex">
    <AccordionPrimitive.Trigger
      ref={ref}
      data-slot="accordion-trigger"
      className={cn(
        "group/trigger flex flex-1 items-center justify-between gap-3 rounded-md py-4 text-start",
        "text-[0.9375rem] font-medium text-foreground",
        "outline-none focus-visible:ring-3 focus-visible:ring-ring",
        "data-[disabled]:cursor-not-allowed data-[disabled]:text-(--foreground-disabled)",
        className,
      )}
      {...props}
    >
      {children}
      <Icon
        icon="ph:caret-down"
        aria-hidden="true"
        className="size-4 shrink-0 text-muted-foreground transition-[rotate,color] duration-fast ease-out group-hover/trigger:text-foreground group-data-[panel-open]/trigger:rotate-180 motion-reduce:transition-none"
      />
    </AccordionPrimitive.Trigger>
  </AccordionPrimitive.Header>
));
AccordionTrigger.displayName = "AccordionTrigger";

/**
 * Cream editorial AccordionContent: the answer in secondary ink. The panel
 * grows to its measured height as it opens and folds back as it closes.
 */
const AccordionContent = React.forwardRef<
  HTMLDivElement,
  WithClassName<AccordionPrimitive.Panel.Props>
>(({ className, children, ...props }, ref) => (
  <AccordionPrimitive.Panel
    ref={ref}
    data-slot="accordion-content"
    className={cn(
      "h-(--accordion-panel-height) overflow-hidden text-sm leading-relaxed text-(--foreground-secondary)",
      "transition-[height] duration-fast ease-out motion-reduce:transition-none",
      "data-[starting-style]:h-0 data-[ending-style]:h-0",
    )}
    {...props}
  >
    <div className={cn("pb-4", className)}>{children}</div>
  </AccordionPrimitive.Panel>
));
AccordionContent.displayName = "AccordionContent";

export { Accordion, AccordionItem, AccordionTrigger, AccordionContent };
