"use client";

import * as React from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface OptionCardProps {
  selected: boolean;
  onClick: () => void;
  icon?: React.ReactNode;
  title: string;
  subtitle?: string;
  disabled?: boolean;
}

export function OptionCard({ selected, onClick, icon, title, subtitle, disabled }: OptionCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "press-3d group relative flex w-full flex-col items-center gap-2 rounded-lg border-2 bg-card p-6 text-center transition-all",
        selected
          ? "border-primary bg-accent/40 text-accent-foreground"
          : "border-input hover:border-primary/50 hover:bg-accent/20",
        disabled && "opacity-50"
      )}
    >
      <span
        className={cn(
          "absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full border-2 transition-all",
          selected ? "animate-check-pop border-primary bg-primary text-primary-foreground" : "border-input bg-background"
        )}
      >
        {selected && <Check className="h-4 w-4" strokeWidth={3} />}
      </span>
      {icon && (
        <span
          className={cn(
            "flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary transition-transform",
            selected && "scale-110 bg-primary text-primary-foreground"
          )}
        >
          {icon}
        </span>
      )}
      <span className="font-display text-lg font-bold">{title}</span>
      {subtitle && <span className="text-sm text-muted-foreground">{subtitle}</span>}
    </button>
  );
}