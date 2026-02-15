"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/useAuthStore";
import type { TokenResponse } from "@/types/api";
import { GlowText } from "@/components/retro/GlowText";
import { RetroInput } from "@/components/retro/RetroInput";
import { RetroButton } from "@/components/retro/RetroButton";

export default function LoginPage() {
  const router = useRouter();
  const { setTokens } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const data = await api.post<TokenResponse>("/auth/login", {
        email,
        password,
      });
      setTokens(data.access_token, data.refresh_token);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="flex min-h-screen items-center justify-center"
      style={{ backgroundColor: "var(--theme-bg-deep)" }}
    >
      <div
        className="w-full max-w-sm border p-8 space-y-6 rounded-lg"
        style={{
          backgroundColor: "var(--theme-bg-card)",
          borderColor: "var(--theme-border)",
        }}
      >
        {/* Header */}
        <div className="text-center space-y-2">
          <GlowText as="h1" className="text-xl">
            MedTimeline
          </GlowText>
          <p
            className="text-sm"
            style={{
              color: "var(--theme-text-dim)",
              fontFamily: "var(--font-body)",
            }}
          >
            Sign in to your account
          </p>
          <div
            className="mx-auto w-32 h-px"
            style={{ backgroundColor: "var(--theme-amber-dim)" }}
          />
        </div>

        {/* Error */}
        {error && (
          <div
            className="p-3 border text-xs"
            style={{
              backgroundColor: "var(--record-allergy-bg)",
              borderColor: "var(--theme-terracotta)",
              color: "var(--theme-terracotta)",
              borderRadius: "4px",
            }}
          >
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <RetroInput
            id="email"
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
          <RetroInput
            id="password"
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
          <RetroButton
            type="submit"
            className="w-full"
            disabled={loading}
          >
            {loading ? "Signing in..." : "Sign in"}
          </RetroButton>
        </form>

        <p
          className="text-center text-xs"
          style={{ color: "var(--theme-text-muted)" }}
        >
          No account?{" "}
          <Link
            href="/register"
            className="underline transition-colors"
            style={{ color: "var(--theme-amber-dim)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--theme-amber)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--theme-amber-dim)")}
          >
            Register
          </Link>
        </p>
      </div>
    </div>
  );
}
