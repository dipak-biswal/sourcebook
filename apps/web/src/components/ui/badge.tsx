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
        success:
          "border-success-border/60 bg-success-soft text-success-text",
        warning:
          "border-warning-border/60 bg-warning-soft text-warning-text",
        danger: "border-danger-border/60 bg-danger-soft text-danger-text",
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
