"use client";

import { cn } from "@/lib/utils";

interface TabsProps {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
}

export function Tabs({ tabs, active, onChange, className }: TabsProps) {
  return (
    <div className={cn("flex flex-wrap gap-1 border-b border-terminal-border", className)}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            "-mb-px border-b-2 px-3 py-2 font-mono text-xs uppercase tracking-wider transition-colors",
            active === tab.id
              ? "border-terminal-accent text-terminal-accent"
              : "border-transparent text-terminal-muted hover:text-terminal-text",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
