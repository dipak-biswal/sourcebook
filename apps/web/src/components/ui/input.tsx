import { forwardRef } from "react";
import { cn } from "@/lib/utils";

const Input = forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-[6px] border border-hairline bg-canvas px-3 py-2 text-sm text-ink shadow-[0_1px_2px_#00000005] placeholder:text-mute transition-shadow",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/20 focus-visible:border-ink/30",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      ref={ref}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
