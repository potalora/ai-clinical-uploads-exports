"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Sun, Moon, Upload, Sparkles, Clock, Shield } from "lucide-react";
import { useAuthStore } from "@/stores/useAuthStore";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon?: LucideIcon;
  separator?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Home", href: "/", separator: false },
  { label: "Timeline", href: "/timeline", icon: Clock, separator: true },
  { label: "Summarize", href: "/summaries", icon: Sparkles },
  { label: "Upload", href: "/upload", icon: Upload },
  { label: "Admin", href: "/admin", separator: true },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export function RetroNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { accessToken, clearTokens } = useAuthStore();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const handleLogout = async () => {
    try {
      await api.post("/auth/logout", undefined, accessToken ?? undefined);
    } catch {
      // Logout even if server call fails
    }
    clearTokens();
    router.push("/login");
  };

  return (
    <nav
      className="flex h-14 items-center justify-between border-b px-4"
      style={{
        backgroundColor: "var(--theme-bg-surface)",
        borderColor: "var(--theme-border)",
      }}
    >
      {/* Logo */}
      <Link
        href="/"
        className="flex items-center gap-2 shrink-0"
        style={{ fontFamily: "var(--font-body)" }}
      >
        <span
          className="text-sm font-semibold"
          style={{ color: "var(--theme-amber)" }}
        >
          MedTimeline
        </span>
      </Link>

      {/* Nav tabs */}
      <div className="flex items-center gap-1">
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "relative px-3 py-2 text-sm font-medium transition-colors duration-200",
              )}
              style={{
                color: active ? "var(--theme-amber)" : "var(--theme-text-dim)",
                fontFamily: "var(--font-body)",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.25rem",
                ...(item.separator
                  ? {
                      borderLeft: "1px solid var(--theme-border)",
                      marginLeft: "0.25rem",
                      paddingLeft: "0.75rem",
                    }
                  : {}),
              }}
              onMouseEnter={(e) => {
                if (!active) e.currentTarget.style.color = "var(--theme-text)";
              }}
              onMouseLeave={(e) => {
                if (!active) e.currentTarget.style.color = "var(--theme-text-dim)";
              }}
            >
              {Icon && <Icon size={16} />}
              {item.label}
              {active && (
                <span
                  className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full"
                  style={{ backgroundColor: "var(--theme-amber)" }}
                />
              )}
            </Link>
          );
        })}
      </div>

      {/* User area */}
      <div className="flex items-center gap-3 shrink-0">
        {mounted && (
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="p-1.5 transition-colors duration-200 cursor-pointer rounded-md"
            style={{ color: "var(--theme-text-dim)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--theme-amber)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--theme-text-dim)")}
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        )}
        <button
          onClick={handleLogout}
          className="text-xs font-medium transition-colors duration-200 cursor-pointer"
          style={{
            color: "var(--theme-text-dim)",
            fontFamily: "var(--font-body)",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "var(--theme-terracotta)")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "var(--theme-text-dim)")}
        >
          Sign out
        </button>
      </div>
    </nav>
  );
}
