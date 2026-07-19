import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider",
  {
    variants: {
      variant: {
        default: "bg-terminal-border text-terminal-text",
        green: "bg-terminal-green/15 text-terminal-green",
        red: "bg-terminal-red/15 text-terminal-red",
        amber: "bg-terminal-amber/15 text-terminal-amber",
        accent: "bg-terminal-accent/15 text-terminal-accent",
        violet: "bg-terminal-violet/15 text-terminal-violet",
        outline: "border border-terminal-border text-terminal-muted",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export function riskBadgeVariant(risk: string): BadgeProps["variant"] {
  switch (risk) {
    case "low":
      return "green";
    case "medium":
      return "amber";
    case "high":
      return "red";
    case "extreme":
      return "violet";
    default:
      return "outline";
  }
}
