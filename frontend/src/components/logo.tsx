import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" fill="none" className={className} aria-hidden="true">
      <circle
        cx="24"
        cy="24"
        r="14"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray="67.5 20.5"
        transform="rotate(-3 24 24)"
      />
      <circle cx="36.5" cy="11.5" r="6" className="fill-ponto" />
    </svg>
  );
}

export function Wordmark({ className, markClassName }: { className?: string; markClassName?: string }) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <LogoMark className={cn("h-7 w-7 shrink-0 text-primary", markClassName)} />
      <span className="font-display text-xl font-bold uppercase tracking-wide">
        Re<span className="text-primary">ponto</span>
      </span>
    </span>
  );
}
