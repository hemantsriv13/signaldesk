"use client";

import * as React from "react";
import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import {
  Controller,
  type ControllerProps,
  type FieldPath,
  type FieldValues,
  FormProvider,
  useFormContext,
} from "react-hook-form";

import { cn } from "@/lib/utils";
import { Label } from "./label";

/*
 * Cream editorial Form: react-hook-form fields set as a short column of
 * label, control, caption and error. A failing field turns its label and
 * error line to the destructive ink, and the control reports aria-invalid,
 * which gives the field its own red edge.
 */

const Form = FormProvider;

type FormFieldContextValue = { name: string };

const FormFieldContext = React.createContext<FormFieldContextValue | null>(
  null,
);

type FormItemContextValue = { id: string };

const FormItemContext = React.createContext<FormItemContextValue | null>(null);

/** Connects one react-hook-form field to the label, control and messages inside it. */
const FormField = <
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
>(
  props: ControllerProps<TFieldValues, TName>,
) => (
  <FormFieldContext.Provider value={{ name: props.name }}>
    <Controller {...props} />
  </FormFieldContext.Provider>
);

/** Reads the current field's ids and validation state. Call it inside a FormField and a FormItem. */
const useFormField = () => {
  const fieldContext = React.useContext(FormFieldContext);
  const itemContext = React.useContext(FormItemContext);
  const { getFieldState, formState } = useFormContext();

  if (!fieldContext) {
    throw new Error("useFormField must be used inside <FormField>");
  }
  if (!itemContext) {
    throw new Error("useFormField must be used inside <FormItem>");
  }

  const fieldState = getFieldState(fieldContext.name, formState);
  const { id } = itemContext;

  return {
    id,
    name: fieldContext.name,
    formItemId: `${id}-form-item`,
    formDescriptionId: `${id}-form-item-description`,
    formMessageId: `${id}-form-item-message`,
    ...fieldState,
  };
};

/** One field's column: label, control, caption and error, 0.5rem apart. */
const FormItem = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => {
  const id = React.useId();
  return (
    <FormItemContext.Provider value={{ id }}>
      <div
        ref={ref}
        data-slot="form-item"
        className={cn("flex flex-col gap-2", className)}
        {...props}
      />
    </FormItemContext.Provider>
  );
});
FormItem.displayName = "FormItem";

/** The field's label. It turns to the destructive ink while the field has an error. */
const FormLabel = React.forwardRef<
  HTMLLabelElement,
  React.ComponentPropsWithoutRef<"label">
>(({ className, ...props }, ref) => {
  const { error, formItemId } = useFormField();
  return (
    <Label
      ref={ref}
      data-slot="form-label"
      data-error={!!error}
      className={cn(error && "text-(--destructive-text)", className)}
      htmlFor={formItemId}
      {...props}
    />
  );
});
FormLabel.displayName = "FormLabel";

/**
 * Wires the control to its label, caption and error through id and aria
 * attributes. Pass the control as `render` (`<FormControl render={<Input />} />`)
 * or as the single child; a single child element becomes the render target.
 */
function FormControl({
  render,
  children,
  ref,
  ...props
}: useRender.ComponentProps<"div">) {
  const { error, formItemId, formDescriptionId, formMessageId } =
    useFormField();
  const childElement = React.isValidElement(children) ? children : undefined;

  const fieldProps: React.ComponentProps<"div"> & { "data-slot": string } = {
    "data-slot": "form-control",
    id: formItemId,
    "aria-describedby": error
      ? `${formDescriptionId} ${formMessageId}`
      : formDescriptionId,
    "aria-invalid": !!error,
    children: childElement ? undefined : children,
  };

  return useRender({
    defaultTagName: "div",
    ref,
    render: render ?? childElement,
    props: mergeProps<"div">(fieldProps, props),
  });
}
FormControl.displayName = "FormControl";

/** A muted caption under the control. */
const FormDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => {
  const { formDescriptionId } = useFormField();
  return (
    <p
      ref={ref}
      id={formDescriptionId}
      data-slot="form-description"
      className={cn("text-[0.8125rem] leading-relaxed text-muted-foreground", className)}
      {...props}
    />
  );
});
FormDescription.displayName = "FormDescription";

/** The field's error in destructive ink. It renders nothing while the field is valid and has no children. */
const FormMessage = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, children, ...props }, ref) => {
  const { error, formMessageId } = useFormField();
  const body = error ? String(error.message ?? "") : children;

  if (!body) return null;

  return (
    <p
      ref={ref}
      id={formMessageId}
      data-slot="form-message"
      className={cn("text-[0.8125rem] font-medium leading-relaxed text-(--destructive-text)", className)}
      {...props}
    >
      {body}
    </p>
  );
});
FormMessage.displayName = "FormMessage";

export {
  useFormField,
  Form,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
  FormField,
};
