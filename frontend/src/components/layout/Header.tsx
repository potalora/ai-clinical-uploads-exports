"use client";

import { useAuthStore } from "@/stores/useAuthStore";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export function Header() {
  const { isAuthenticated, clearTokens } = useAuthStore();
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch {
      // Logout even if server call fails
    }
    clearTokens();
    router.push("/login");
  };

  return (
    <header className="flex h-14 items-center justify-between border-b bg-card px-6">
      <div className="text-sm text-muted-foreground">
        Personal Health Records
      </div>
      <div className="flex items-center gap-4">
        {isAuthenticated && (
          <Button variant="ghost" size="sm" onClick={handleLogout}>
            Sign out
          </Button>
        )}
      </div>
    </header>
  );
}
