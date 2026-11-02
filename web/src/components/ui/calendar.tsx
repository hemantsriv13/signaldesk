"use client";

import * as React from "react";
import { DayButton, DayPicker } from "react-day-picker";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";
import { buttonVariants } from "./button";

export type CalendarProps = React.ComponentProps<typeof DayPicker>;

const navButton = cn(
  buttonVariants({ variant: "ghost", size: "icon-sm" }),
  "text-muted-foreground aria-disabled:pointer-events-none aria-disabled:text-(--foreground-disabled)",
);

const caretIcons = {
  left: "ph:caret-left",
  right: "ph:caret-right",
  up: "ph:caret-up",
  down: "ph:caret-down",
} as const;

function CalendarChevron({
  orientation = "left",
  className,
}: {
  orientation?: keyof typeof caretIcons;
  className?: string;
}) {
  return (
    <Icon
      icon={caretIcons[orientation]}
      aria-hidden="true"
      className={cn("size-4", className)}
    />
  );
}

/**
 * One day of the grid. A chosen day, and each end of a chosen range, is a
 * flat terracotta square with white figures; the days between the ends sit
 * on the oat band the cells draw. Today carries an oat well until chosen.
 */
function CalendarDayButton({
  className,
  modifiers,
  ...props
}: React.ComponentProps<typeof DayButton>) {
  const chosen = modifiers.selected && !modifiers.range_middle;

  return (
    <DayButton
      modifiers={modifiers}
      data-slot="calendar-day"
      className={cn(
        className,
        modifiers.outside && "text-muted-foreground",
        modifiers.today && !modifiers.selected && "bg-muted font-medium",
        modifiers.range_middle && "rounded-none hover:bg-transparent",
        chosen &&
          "bg-primary font-medium text-primary-foreground hover:bg-(--primary-hover)",
        modifiers.disabled && "text-(--foreground-disabled)",
      )}
      {...props}
    />
  );
}

/**
 * Cream editorial Calendar: a month of 2.25rem days with 0.5rem corners on
 * cream paper. The month name sits in the serif between two ghost carets.
 * A chosen day turns terracotta like the primary button; a range runs as an
 * oat band between two terracotta ends.
 */
function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  components,
  ...props
}: CalendarProps) {
  return (
    <DayPicker
      data-slot="calendar"
      showOutsideDays={showOutsideDays}
      className={cn("p-3", className)}
      classNames={{
        months: "relative flex flex-col gap-4 sm:flex-row",
        month: "flex flex-col gap-3",
        month_caption: "flex h-8 items-center justify-center",
        caption_label:
          "inline-flex items-center gap-1 font-serif text-base font-medium text-foreground [&_svg]:size-3.5 [&_svg]:text-muted-foreground",
        dropdowns: "flex items-center gap-2",
        dropdown_root:
          "relative inline-flex items-center rounded-md px-1.5 hover:bg-secondary has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring",
        dropdown: "absolute inset-0 cursor-pointer opacity-0",
        nav: "absolute inset-x-0 top-0 flex h-8 items-center justify-between",
        button_previous: navButton,
        button_next: navButton,
        month_grid: "w-full border-collapse",
        weekdays: "flex",
        weekday: "w-9 text-center text-xs font-medium text-muted-foreground",
        week: "mt-1 flex w-full",
        day: "relative size-9 p-0 text-center",
        day_button: cn(
          "inline-flex size-9 items-center justify-center rounded-md text-sm tabular-nums text-foreground",
          "transition-[background-color,color] duration-fast ease-out hover:bg-secondary",
          "outline-none focus-visible:ring-3 focus-visible:ring-ring",
          "disabled:pointer-events-none",
        ),
        range_start: "rounded-s-md bg-muted",
        range_middle: "bg-muted first:rounded-s-md last:rounded-e-md",
        range_end: "rounded-e-md bg-muted",
        outside: "text-muted-foreground",
        disabled: "text-(--foreground-disabled)",
        hidden: "invisible",
        week_number: "w-9 text-xs text-muted-foreground",
        footer: "pt-3 text-sm text-muted-foreground",
        ...classNames,
      }}
      components={{
        Chevron: CalendarChevron,
        DayButton: CalendarDayButton,
        ...components,
      }}
      {...props}
    />
  );
}
Calendar.displayName = "Calendar";

export { Calendar };
