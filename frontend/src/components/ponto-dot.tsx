import { cn } from "@/lib/utils";

export function PontoDot({ className }: { className?: string }) {
  return (
    <span
      className={cn("relative inline-flex h-2.5 w-2.5 shrink-0", className)}
      aria-hidden="true"
    >
      <span className="absolute inline-flex h-full w-full rounded-full bg-ponto animate-ponto-ping" />
      <span className="relative inline-flex h-full w-full rounded-full bg-ponto" />
    </span>
  );
}
