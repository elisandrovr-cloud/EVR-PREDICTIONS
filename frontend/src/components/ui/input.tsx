import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-md border border-terminal-border bg-terminal-bg px-3 text-sm text-terminal-text",
        "placeholder:text-terminal-muted/60 focus:border-terminal-accent focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}
