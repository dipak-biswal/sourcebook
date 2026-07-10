import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-ink text-[var(--canvas)]",
        secondary: "border-transparent bg-canvas-soft-2 text-body",
        outline: "border-hairline text-body bg-canvas",
        success: "border-transparent bg-[#d1fae5] text-[#065f46]",
        warning: "border-transparent bg-[#fef3c7] text-[#92400e]",
        danger: "border-transparent bg-[#fee2e2] text-[#991b1b]",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

type BadgeProps = React.HTMLAttributes<HTMLDivElement> &
  VariantProps<typeof badgeVariants>;

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
export type { BadgeProps };
