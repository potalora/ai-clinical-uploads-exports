"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { RetroNav } from "@/components/retro/RetroNav";
import { useAuthStore, useHasHydrated } from "@/stores/useAuthStore";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const hydrated = useHasHydrated();

  useEffect(() => {
    if (hydrated && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthenticated, hydrated, router]);

  if (!hydrated || !isAuthenticated) {
    return null;
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <RetroNav />
      <main className="flex-1 overflow-auto p-6">{children}</main>
    </div>
  );
}
