import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef } from "react";
import { cn } from "@/lib/utils";

const alertVariants = cva("relative w-full rounded-[6px] border p-3 text-sm", {
  variants: {
    variant: {
      default: "bg-canvas text-body border-hairline",
      danger: "border-[#fecaca] bg-[#fef2f2] text-[#991b1b]",
    },
  },
  defaultVariants: { variant: "default" },
});

const Alert = forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>
>(({ className, variant, ...props }, ref) => (
  <div
    ref={ref}
    role="alert"
    className={cn(alertVariants({ variant }), className)}
    {...props}
  />
));
Alert.displayName = "Alert";

export { Alert, alertVariants };
