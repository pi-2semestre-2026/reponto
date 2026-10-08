"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Header } from "@/components/header";
import { SimulatorGame } from "@/components/simulator/game";
import { getToken } from "@/lib/token";

export default function SimulatorPage() {
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  return (
    <div className="min-h-screen">
      <Header />
      <main className="relative">
        <div className="bg-dots pointer-events-none absolute inset-0 [mask-image:radial-gradient(50%_40%_at_50%_0%,black,transparent)]" />
        <div className="relative">
          <SimulatorGame />
        </div>
      </main>
    </div>
  );
}