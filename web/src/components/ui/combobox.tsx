"use client";

import * as React from "react";
import { Icon } from "@iconify/react";

import { cn } from "@/lib/utils";
import { formFieldBase, formFieldSingleLine } from "./_shared";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "./command";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

const formats = [
  { value: "field-notes", label: "Field notes" },
  { value: "long-form", label: "Long-form essay" },
  { value: "summary", label: "Summary" },
  { value: "outline", label: "Outline" },
  { value: "letter", label: "Letter" },
];

/**
 * Cream editorial combobox: a field that opens a searchable list. The
 * trigger is the paper box every text field uses, with an up-down caret at
 * the end. The list drops onto the floating paper panel, as wide as the
 * trigger, and the chosen row carries an ink tick.
 */
export function ComboboxDemo() {
  const [open, setOpen] = React.useState(false);
  const [value, setValue] = React.useState("");
  const selected = formats.find((format) => format.value === value);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        role="combobox"
        aria-expanded={open}
        data-slot="combobox-trigger"
        className={cn(
          formFieldBase,
          formFieldSingleLine,
          "w-56 cursor-default items-center justify-between gap-2 text-start",
          "data-[popup-open]:border-primary",
          !selected && "text-muted-foreground",
        )}
      >
        <span className="truncate">{selected ? selected.label : "Choose a format"}</span>
        <Icon
          icon="ph:caret-up-down"
          className="size-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-(--anchor-width) gap-0 p-0">
        <Command className="bg-transparent shadow-none">
          <CommandInput placeholder="Search formats" />
          <CommandList>
            <CommandEmpty>No format found.</CommandEmpty>
            <CommandGroup>
              {formats.map((format) => (
                <CommandItem
                  key={format.value}
                  value={format.value}
                  onSelect={(currentValue: string) => {
                    setValue(currentValue === value ? "" : currentValue);
                    setOpen(false);
                  }}
                >
                  {format.label}
                  <Icon
                    icon="ph:check"
                    className={cn(
                      "ms-auto size-4",
                      value === format.value ? "opacity-100" : "opacity-0",
                    )}
                    aria-hidden="true"
                  />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
