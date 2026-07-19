import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-terminal-accent text-terminal-bg hover:bg-terminal-accent/85",
        outline: "border border-terminal-border text-terminal-text hover:bg-terminal-border/40",
        ghost: "text-terminal-muted hover:bg-terminal-border/40 hover:text-terminal-text",
        danger: "bg-terminal-red text-terminal-bg hover:bg-terminal-red/85",
      },
      size: {
        default: "h-9 px-4 text-sm",
        sm: "h-7 px-2.5 text-xs",
        lg: "h-11 px-6 text-base",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
