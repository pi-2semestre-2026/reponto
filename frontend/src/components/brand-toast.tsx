import { LogoMark } from "@/components/logo";
import { PontoDot } from "@/components/ponto-dot";

export const BRAND_TOAST_MS = 3500;

export function BrandToast({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="relative flex w-[356px] max-w-[calc(100vw-2rem)] items-center gap-4 overflow-hidden rounded-2xl border bg-card p-4 pb-5 shadow-[0_18px_40px_-18px_hsl(var(--primary)/0.45)]">
      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <LogoMark className="h-7 w-7" />
      </span>
      <div className="min-w-0">
        <p className="break-words font-display text-base font-bold leading-snug">{title}</p>
        <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
          <PontoDot className="h-2 w-2" />
          {subtitle}
        </p>
      </div>
      <span
        className="toast-progress absolute bottom-0 left-0 h-1 w-full origin-left bg-primary"
        style={{ animationDuration: `${BRAND_TOAST_MS}ms` }}
      />
    </div>
  );
}
