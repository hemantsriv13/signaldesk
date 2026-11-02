"use client";

import * as React from "react";
import { format } from "date-fns";
import type { DateRange } from "react-day-picker";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";
import { formFieldBase, formFieldSingleLine } from "./_shared";
import { Calendar } from "./calendar";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

/** Writes a range as "4 Oct to 12 Oct 2026", or one date while only the start is set. */
function rangeLabel(range: DateRange | undefined) {
  if (!range?.from) return undefined;
  if (!range.to) return format(range.from, "d MMM yyyy");
  return `${format(range.from, "d MMM")} to ${format(range.to, "d MMM yyyy")}`;
}

/**
 * Cream editorial DataRangePicker: a paper field that opens two months side
 * by side in the floating panel. The two ends of the range turn terracotta,
 * and the days between them sit on an oat band.
 */
export function DataRangePicker() {
  const [range, setRange] = React.useState<DateRange>();
  const label = rangeLabel(range);

  return (
    <Popover>
      <PopoverTrigger
        data-slot="data-range-picker"
        className={cn(
          formFieldBase,
          formFieldSingleLine,
          "w-72 items-center gap-2 text-start data-[popup-open]:border-primary",
          !label && "text-muted-foreground",
        )}
      >
        <Icon
          icon="ph:calendar-blank"
          aria-hidden="true"
          className="size-4 shrink-0 text-muted-foreground"
        />
        <span className="truncate">{label ?? "Pick a date range"}</span>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="range"
          selected={range}
          onSelect={setRange}
          defaultMonth={range?.from}
          numberOfMonths={2}
          autoFocus
        />
      </PopoverContent>
    </Popover>
  );
}
