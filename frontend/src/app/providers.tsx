"use client";

import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { I18nProvider } from "@/lib/i18n";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false} disableTransitionOnChange>
      <I18nProvider>
        <TooltipProvider delayDuration={200}>
          {children}
          <Toaster
            position="top-center"
            richColors
            toastOptions={{ style: { borderRadius: "14px" } }}
          />
        </TooltipProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}