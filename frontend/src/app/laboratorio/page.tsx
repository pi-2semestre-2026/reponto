"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Header } from "@/components/header";
import { LabDemo } from "@/components/lab/lab-demo";
import { getToken } from "@/lib/token";

export default function LabPage() {
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  return (
    <div className="min-h-screen">
      <Header active="/laboratorio" />
      <main className="container space-y-6 py-8">
        <LabDemo />
      </main>
    </div>
  );
}
