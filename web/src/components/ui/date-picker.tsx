"use client";

import * as React from "react";
import { format } from "date-fns";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";
import { formFieldBase, formFieldSingleLine } from "./_shared";
import { Calendar } from "./calendar";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

/** Props for the DatePicker. It is controlled: pass `value` and `onValueChange`. */
export interface DatePickerProps {
  value?: Date;
  onValueChange?: (date: Date | undefined) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

/**
 * Cream editorial DatePicker: a paper field with a calendar glyph that opens
 * the calendar in the floating panel. Picking a day fills the field and
 * closes the panel.
 */
const DatePicker = React.forwardRef<HTMLButtonElement, DatePickerProps>(
  (
    { value, onValueChange, placeholder = "Pick a date", className, disabled },
    ref,
  ) => {
    const [open, setOpen] = React.useState(false);

    return (
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          ref={ref}
          disabled={disabled}
          data-slot="date-picker"
          className={cn(
            formFieldBase,
            formFieldSingleLine,
            "items-center gap-2 text-start data-[popup-open]:border-primary",
            !value && "text-muted-foreground",
            className,
          )}
        >
          <Icon
            icon="ph:calendar-blank"
            aria-hidden="true"
            className="size-4 shrink-0 text-muted-foreground"
          />
          <span className="truncate">
            {value ? format(value, "d MMMM yyyy") : placeholder}
          </span>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="single"
            selected={value}
            defaultMonth={value}
            onSelect={(date: Date | undefined) => {
              onValueChange?.(date);
              setOpen(false);
            }}
            autoFocus
          />
        </PopoverContent>
      </Popover>
    );
  },
);
DatePicker.displayName = "DatePicker";

export { DatePicker };
