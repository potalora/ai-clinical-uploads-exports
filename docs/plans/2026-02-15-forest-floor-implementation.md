# Forest Floor Theme Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the frontend from "Nostromo Earth Terminal" (heavy CRT sci-fi) to "Forest Floor" — warm, approachable earth tones with only subtle monospace-for-data as a sci-fi nod.

**Architecture:** CSS custom properties drive the entire theme. We update `globals.css` values + remove CRT effect classes, then update each component to remove glow/uppercase/CRT references, then update pages for sentence-case text. Variable rename `--retro-*` → `--theme-*` happens last as a bulk find-and-replace.

**Tech Stack:** Next.js 15, Tailwind CSS 4, next-themes, CSS custom properties

---

### Task 1: Update globals.css — New Forest Floor Palette

**Files:**
- Modify: `frontend/src/app/globals.css`

**Step 1: Replace light mode retro palette tokens (lines 58–74)**

Replace the `:root` retro palette block with:

```css
  /* Theme palette tokens — light mode */
  --retro-bg-deep: #f7f4ef;
  --retro-bg-surface: #efe9df;
  --retro-bg-card: #ffffff;
  --retro-bg-card-hover: #faf6f0;
  --retro-text: #2a2f26;
  --retro-text-dim: #5c6358;
  --retro-text-muted: #6b7265;
  --retro-amber: #4a7c59;
  --retro-amber-dim: #3d6649;
  --retro-terracotta: #b54834;
  --retro-sage: #5a7a50;
  --retro-ochre: #b8860b;
  --retro-sienna: #8b6914;
  --retro-border: #d4cdc0;
  --retro-border-active: #b8b0a0;
  --retro-glow-rgb: 74, 124, 89;
```

**Step 2: Replace light mode shadcn semantic tokens (lines 77–107)**

```css
  /* shadcn semantic tokens — light mode */
  --background: #f7f4ef;
  --foreground: #2a2f26;
  --card: #ffffff;
  --card-foreground: #2a2f26;
  --popover: #ffffff;
  --popover-foreground: #2a2f26;
  --primary: #4a7c59;
  --primary-foreground: #ffffff;
  --secondary: #efe9df;
  --secondary-foreground: #2a2f26;
  --muted: #efe9df;
  --muted-foreground: #5c6358;
  --accent: #faf6f0;
  --accent-foreground: #2a2f26;
  --destructive: #b54834;
  --border: #d4cdc0;
  --input: #d4cdc0;
  --ring: #4a7c59;
  --chart-1: #4a7c59;
  --chart-2: #b8860b;
  --chart-3: #5a7a50;
  --chart-4: #b54834;
  --chart-5: #8b6914;
  --sidebar: #efe9df;
  --sidebar-foreground: #2a2f26;
  --sidebar-primary: #4a7c59;
  --sidebar-primary-foreground: #ffffff;
  --sidebar-accent: #faf6f0;
  --sidebar-accent-foreground: #2a2f26;
  --sidebar-border: #d4cdc0;
  --sidebar-ring: #4a7c59;
```

**Step 3: Replace light mode record type colors (lines 109–154)**

```css
  /* Record type colors — light mode */
  --record-condition-bg: #fdf6e3;
  --record-condition-text: #7a6200;
  --record-condition-dot: #b8860b;
  --record-observation-bg: #eef5eb;
  --record-observation-text: #3d6632;
  --record-observation-dot: #4a7c59;
  --record-medication-bg: #fde8e2;
  --record-medication-text: #8a4030;
  --record-medication-dot: #c47a5a;
  --record-encounter-bg: #e6f0ee;
  --record-encounter-text: #3a6a5a;
  --record-encounter-dot: #5a8c7a;
  --record-immunization-bg: #fdf6e3;
  --record-immunization-text: #7a6200;
  --record-immunization-dot: #b8960b;
  --record-procedure-bg: #e8eef4;
  --record-procedure-text: #3a5a6e;
  --record-procedure-dot: #5a7a8c;
  --record-document-bg: #f0ece6;
  --record-document-text: #5a5040;
  --record-document-dot: #8a7a6a;
  --record-allergy-bg: #fce4e0;
  --record-allergy-text: #8a3020;
  --record-allergy-dot: #b54834;
  --record-imaging-bg: #f0e8f4;
  --record-imaging-text: #5a3a6a;
  --record-imaging-dot: #8a5a7a;
  --record-diagnostic_report-bg: #fdf6e3;
  --record-diagnostic_report-text: #6a5800;
  --record-diagnostic_report-dot: #b8960b;
  --record-service_request-bg: #fdf6e3;
  --record-service_request-text: #7a6200;
  --record-service_request-dot: #b8960b;
  --record-communication-bg: #f0ece6;
  --record-communication-text: #5a5040;
  --record-communication-dot: #8a7a6a;
  --record-appointment-bg: #e8eef4;
  --record-appointment-text: #3a5a6e;
  --record-appointment-dot: #5a7a8c;
  --record-care_plan-bg: #eef5eb;
  --record-care_plan-text: #3d6632;
  --record-care_plan-dot: #5a7a50;
  --record-default-bg: #f0ece6;
  --record-default-text: #5a5040;
  --record-default-dot: #8a7a6a;
```

**Step 4: Replace dark mode retro palette tokens (lines 158–174)**

```css
  /* Theme palette tokens — dark mode */
  --retro-bg-deep: #1c2118;
  --retro-bg-surface: #262f22;
  --retro-bg-card: #2f3a2a;
  --retro-bg-card-hover: #384432;
  --retro-text: #e4dfd4;
  --retro-text-dim: #a0a896;
  --retro-text-muted: #8a9182;
  --retro-amber: #6aa67a;
  --retro-amber-dim: #558a62;
  --retro-terracotta: #d06040;
  --retro-sage: #7a9c60;
  --retro-ochre: #d4a843;
  --retro-sienna: #c4a020;
  --retro-border: #3a4436;
  --retro-border-active: #4a5a42;
  --retro-glow-rgb: 106, 166, 122;
```

**Step 5: Replace dark mode shadcn semantic tokens (lines 177–207)**

```css
  /* shadcn semantic tokens — dark mode */
  --background: #1c2118;
  --foreground: #e4dfd4;
  --card: #2f3a2a;
  --card-foreground: #e4dfd4;
  --popover: #262f22;
  --popover-foreground: #e4dfd4;
  --primary: #6aa67a;
  --primary-foreground: #1c2118;
  --secondary: #384432;
  --secondary-foreground: #e4dfd4;
  --muted: #262f22;
  --muted-foreground: #a0a896;
  --accent: #384432;
  --accent-foreground: #e4dfd4;
  --destructive: #d06040;
  --border: #3a4436;
  --input: #3a4436;
  --ring: #6aa67a;
  --chart-1: #6aa67a;
  --chart-2: #d4a843;
  --chart-3: #7a9c60;
  --chart-4: #d06040;
  --chart-5: #c4a020;
  --sidebar: #262f22;
  --sidebar-foreground: #e4dfd4;
  --sidebar-primary: #6aa67a;
  --sidebar-primary-foreground: #1c2118;
  --sidebar-accent: #384432;
  --sidebar-accent-foreground: #e4dfd4;
  --sidebar-border: #3a4436;
  --sidebar-ring: #6aa67a;
```

**Step 6: Replace dark mode record type colors (lines 209–254)**

```css
  /* Record type colors — dark mode */
  --record-condition-bg: #3d2e14;
  --record-condition-text: #d4a843;
  --record-condition-dot: #d4a843;
  --record-observation-bg: #1e2e1a;
  --record-observation-text: #7a9c60;
  --record-observation-dot: #7a9c60;
  --record-medication-bg: #2e1a14;
  --record-medication-text: #c47a5a;
  --record-medication-dot: #c47a5a;
  --record-encounter-bg: #1a2e28;
  --record-encounter-text: #5a8c7a;
  --record-encounter-dot: #5a8c7a;
  --record-immunization-bg: #2e2214;
  --record-immunization-text: #d49a40;
  --record-immunization-dot: #d49a40;
  --record-procedure-bg: #1a2230;
  --record-procedure-text: #5a7a8c;
  --record-procedure-dot: #5a7a8c;
  --record-document-bg: #252018;
  --record-document-text: #8a7a6a;
  --record-document-dot: #8a7a6a;
  --record-allergy-bg: #301414;
  --record-allergy-text: #c45a3c;
  --record-allergy-dot: #c45a3c;
  --record-imaging-bg: #28182e;
  --record-imaging-text: #8a5a7a;
  --record-imaging-dot: #8a5a7a;
  --record-diagnostic_report-bg: #2e2a14;
  --record-diagnostic_report-text: #c4a040;
  --record-diagnostic_report-dot: #c4a040;
  --record-service_request-bg: #2e2214;
  --record-service_request-text: #d49a40;
  --record-service_request-dot: #d49a40;
  --record-communication-bg: #252018;
  --record-communication-text: #8a7a6a;
  --record-communication-dot: #8a7a6a;
  --record-appointment-bg: #1a2230;
  --record-appointment-text: #5a7a8c;
  --record-appointment-dot: #5a7a8c;
  --record-care_plan-bg: #1e2e1a;
  --record-care_plan-text: #7a9c60;
  --record-care_plan-dot: #7a9c60;
  --record-default-bg: #252018;
  --record-default-text: #8a7a6a;
  --record-default-dot: #8a7a6a;
```

**Step 7: Run the dev server to verify colors load**

Run: `cd frontend && npm run dev`
Expected: Site loads with new Forest Floor colors, no CSS errors in console.

**Step 8: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "feat: update color palette to Forest Floor earth tones"
```

---

### Task 2: Remove CRT Effects from globals.css

**Files:**
- Modify: `frontend/src/app/globals.css`

**Step 1: Replace the entire CRT EFFECTS section (lines 267–341) with warm utility classes**

Delete everything from `/* ============================================ CRT EFFECTS` through `.retro-border-active` and replace with:

```css
/* ============================================
   WARM UTILITY CLASSES
   ============================================ */

/* Soft card shadow */
.theme-shadow {
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04);
}

.theme-shadow-hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1), 0 2px 4px rgba(0, 0, 0, 0.06);
}

/* Focus ring */
.theme-focus-ring {
  box-shadow: 0 0 0 2px var(--retro-bg-deep), 0 0 0 4px var(--retro-amber);
}

/* Border variants */
.theme-border {
  border-color: var(--retro-border);
}

.theme-border-active {
  border-color: var(--retro-border-active);
}
```

**Step 2: Replace the entire ANIMATIONS section (lines 343–401) — keep only fade-in-up and stagger**

Delete everything from `/* ============================================ ANIMATIONS` through `.blink-cursor::after` and replace with:

```css
/* ============================================
   ANIMATIONS
   ============================================ */

@keyframes fade-in-up {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes pulse-fade {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

/* Staggered children animation */
.retro-stagger > * {
  animation: fade-in-up 0.3s ease-out both;
}
.retro-stagger > *:nth-child(1) { animation-delay: 0ms; }
.retro-stagger > *:nth-child(2) { animation-delay: 50ms; }
.retro-stagger > *:nth-child(3) { animation-delay: 100ms; }
.retro-stagger > *:nth-child(4) { animation-delay: 150ms; }
.retro-stagger > *:nth-child(5) { animation-delay: 200ms; }
.retro-stagger > *:nth-child(6) { animation-delay: 250ms; }
.retro-stagger > *:nth-child(7) { animation-delay: 300ms; }
.retro-stagger > *:nth-child(8) { animation-delay: 350ms; }
```

**Step 3: Verify dev server shows no CRT effects**

Run: `cd frontend && npm run dev`
Expected: No scanlines, no vignette, no glow text-shadows. Page still renders.

**Step 4: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "feat: remove CRT effects, add warm utility classes"
```

---

### Task 3: Remove CRTOverlay + Update Layouts

**Files:**
- Delete: `frontend/src/components/retro/CRTOverlay.tsx`
- Modify: `frontend/src/app/(dashboard)/layout.tsx`
- Modify: `frontend/src/app/(auth)/login/page.tsx`
- Modify: `frontend/src/app/(auth)/register/page.tsx`

**Step 1: Delete CRTOverlay.tsx**

Delete the file `frontend/src/components/retro/CRTOverlay.tsx`.

**Step 2: Update dashboard layout — remove CRTOverlay import and usage, remove separator comment**

Replace full contents of `frontend/src/app/(dashboard)/layout.tsx`:

```tsx
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
```

**Step 3: Update login page — remove CRTOverlay import/usage, update text casing**

In `frontend/src/app/(auth)/login/page.tsx`:
- Remove the `import { CRTOverlay }` line
- Remove `<CRTOverlay />` from the JSX
- Change `MEDTIMELINE` → `MedTimeline`
- Change `ACCESS TERMINAL` → `Sign in to your account`
- Change `AUTHENTICATING...` → `Signing in...`
- Change `AUTHENTICATE` → `Sign in`

**Step 4: Update register page — remove CRTOverlay import/usage, update text casing**

In `frontend/src/app/(auth)/register/page.tsx`:
- Remove the `import { CRTOverlay }` line
- Remove `<CRTOverlay />` from the JSX
- Change `MEDTIMELINE` → `MedTimeline`
- Change `CREATE NEW ACCESS CREDENTIALS` → `Create your account`
- Change `CREATING ACCOUNT...` → `Creating account...`
- Change `CREATE ACCOUNT` → `Create account`

**Step 5: Verify auth pages and dashboard render without CRT overlay**

Run: `cd frontend && npm run dev`
Expected: Login, register, and dashboard pages load clean — no scanlines/vignette overlay.

**Step 6: Commit**

```bash
git add -A
git commit -m "feat: remove CRTOverlay from layouts and auth pages"
```

---

### Task 4: Update GlowText Component

**Files:**
- Modify: `frontend/src/components/retro/GlowText.tsx`

**Step 1: Rewrite GlowText to remove glow, keep as DisplayText**

Replace full contents of `frontend/src/components/retro/GlowText.tsx`:

```tsx
"use client";

import { cn } from "@/lib/utils";

interface GlowTextProps {
  as?: "h1" | "h2" | "h3" | "h4" | "h5" | "h6" | "span" | "p";
  glow?: boolean;
  className?: string;
  children: React.ReactNode;
}

const sizeMap: Record<string, string> = {
  h1: "text-2xl font-bold tracking-tight",
  h2: "text-xl font-semibold tracking-tight",
  h3: "text-lg font-semibold",
  h4: "text-base font-semibold",
  h5: "text-sm font-semibold",
  h6: "text-xs font-semibold",
  span: "",
  p: "",
};

export function GlowText({
  as: Tag = "h1",
  className,
  children,
}: GlowTextProps) {
  return (
    <Tag
      className={cn(sizeMap[Tag], className)}
      style={{
        fontFamily: "var(--font-display)",
        color: "var(--retro-text)",
      }}
    >
      {children}
    </Tag>
  );
}
```

Note: the `glow` prop is accepted but ignored (for backwards compat with existing callers).

**Step 2: Commit**

```bash
git add frontend/src/components/retro/GlowText.tsx
git commit -m "feat: simplify GlowText — remove glow effect"
```

---

### Task 5: Update RetroButton Component

**Files:**
- Modify: `frontend/src/components/retro/RetroButton.tsx`

**Step 1: Rewrite RetroButton — remove uppercase, glow, pulse animation**

Replace full contents of `frontend/src/components/retro/RetroButton.tsx`:

```tsx
"use client";

import { cn } from "@/lib/utils";

interface RetroButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost" | "destructive" | "large";
  children: React.ReactNode;
}

const variantStyles: Record<string, React.CSSProperties> = {
  primary: {
    backgroundColor: "var(--retro-amber)",
    color: "#ffffff",
  },
  ghost: {
    backgroundColor: "transparent",
    color: "var(--retro-amber)",
    border: "1px solid var(--retro-border)",
  },
  destructive: {
    backgroundColor: "var(--retro-terracotta)",
    color: "#ffffff",
  },
  large: {
    backgroundColor: "var(--retro-amber)",
    color: "#ffffff",
  },
};

export function RetroButton({
  variant = "primary",
  className,
  children,
  disabled,
  ...props
}: RetroButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center font-medium transition-all duration-200 cursor-pointer rounded-md",
        variant === "large"
          ? "px-8 py-3 text-sm"
          : "px-4 py-2 text-xs",
        disabled && "opacity-50 cursor-not-allowed",
        className,
      )}
      style={{
        ...variantStyles[variant],
        fontFamily: "var(--font-body)",
      }}
      disabled={disabled}
      onMouseEnter={(e) => {
        if (disabled) return;
        if (variant === "ghost") {
          e.currentTarget.style.backgroundColor = "var(--retro-bg-card-hover)";
          e.currentTarget.style.borderColor = "var(--retro-border-active)";
        } else {
          e.currentTarget.style.filter = "brightness(1.1)";
        }
      }}
      onMouseLeave={(e) => {
        if (disabled) return;
        if (variant === "ghost") {
          e.currentTarget.style.backgroundColor = "transparent";
          e.currentTarget.style.borderColor = "var(--retro-border)";
        } else {
          e.currentTarget.style.filter = "none";
        }
      }}
      {...props}
    >
      {children}
    </button>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/retro/RetroButton.tsx
git commit -m "feat: naturalize RetroButton — remove glow, uppercase, pulse"
```

---

### Task 6: Update RetroCard Component

**Files:**
- Modify: `frontend/src/components/retro/RetroCard.tsx`

**Step 1: Rewrite RetroCard — add shadow, remove amber accent, round corners**

Replace full contents of `frontend/src/components/retro/RetroCard.tsx`:

```tsx
"use client";

import { cn } from "@/lib/utils";

interface RetroCardProps {
  className?: string;
  accentTop?: boolean;
  children: React.ReactNode;
}

export function RetroCard({ className, accentTop, children }: RetroCardProps) {
  return (
    <div
      className={cn(
        "border rounded-lg transition-shadow duration-200 theme-shadow",
        className,
      )}
      style={{
        backgroundColor: "var(--retro-bg-card)",
        borderColor: "var(--retro-border)",
        borderTop: accentTop ? "2px solid var(--retro-amber)" : undefined,
      }}
    >
      {children}
    </div>
  );
}

export function RetroCardHeader({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn("px-4 py-3 border-b", className)}
      style={{ borderColor: "var(--retro-border)" }}
    >
      {children}
    </div>
  );
}

export function RetroCardContent({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return <div className={cn("px-4 py-4", className)}>{children}</div>;
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/retro/RetroCard.tsx
git commit -m "feat: soften RetroCard — add shadow, rounded corners"
```

---

### Task 7: Update RetroNav Component

**Files:**
- Modify: `frontend/src/components/retro/RetroNav.tsx`

**Step 1: Rewrite RetroNav — remove F-key labels, glow, uppercase**

Replace full contents of `frontend/src/components/retro/RetroNav.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Sun, Moon } from "lucide-react";
import { useAuthStore } from "@/stores/useAuthStore";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { label: "Home", href: "/" },
  { label: "Timeline", href: "/timeline" },
  { label: "Summaries", href: "/summaries" },
  { label: "Admin", href: "/admin" },
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
        backgroundColor: "var(--retro-bg-surface)",
        borderColor: "var(--retro-border)",
      }}
    >
      {/* Logo */}
      <Link
        href="/"
        className="flex items-center gap-2 shrink-0"
        style={{ fontFamily: "var(--font-display)" }}
      >
        <span
          className="text-sm font-semibold"
          style={{ color: "var(--retro-amber)" }}
        >
          MedTimeline
        </span>
      </Link>

      {/* Nav tabs */}
      <div className="flex items-center gap-1">
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "relative px-3 py-2 text-sm font-medium transition-colors duration-200",
              )}
              style={{
                color: active ? "var(--retro-amber)" : "var(--retro-text-dim)",
                fontFamily: "var(--font-body)",
              }}
              onMouseEnter={(e) => {
                if (!active) e.currentTarget.style.color = "var(--retro-text)";
              }}
              onMouseLeave={(e) => {
                if (!active) e.currentTarget.style.color = "var(--retro-text-dim)";
              }}
            >
              {item.label}
              {active && (
                <span
                  className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full"
                  style={{ backgroundColor: "var(--retro-amber)" }}
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
            style={{ color: "var(--retro-text-dim)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--retro-amber)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--retro-text-dim)")}
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        )}
        <button
          onClick={handleLogout}
          className="text-xs font-medium transition-colors duration-200 cursor-pointer"
          style={{
            color: "var(--retro-text-dim)",
            fontFamily: "var(--font-body)",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "var(--retro-terracotta)")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "var(--retro-text-dim)")}
        >
          Sign out
        </button>
      </div>
    </nav>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/retro/RetroNav.tsx
git commit -m "feat: clean up RetroNav — remove F-keys, glow, uppercase"
```

---

### Task 8: Update RetroTabs, RetroInput, RetroLoadingState

**Files:**
- Modify: `frontend/src/components/retro/RetroTabs.tsx`
- Modify: `frontend/src/components/retro/RetroInput.tsx`
- Modify: `frontend/src/components/retro/RetroLoadingState.tsx`

**Step 1: Rewrite RetroTabs — remove separators, glow, uppercase**

Replace full contents of `frontend/src/components/retro/RetroTabs.tsx`:

```tsx
"use client";

import { cn } from "@/lib/utils";

interface RetroTab {
  key: string;
  label: string;
  separator?: boolean;
}

interface RetroTabsProps {
  tabs: RetroTab[];
  active: string;
  onChange: (key: string) => void;
}

export function RetroTabs({ tabs, active, onChange }: RetroTabsProps) {
  return (
    <div
      className="flex items-center gap-0.5 overflow-x-auto border-b pb-px"
      style={{ borderColor: "var(--retro-border)" }}
    >
      {tabs.map((tab) => {
        if (tab.separator) return null;
        const isActive = active === tab.key;
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={cn(
              "relative px-3 py-2 text-xs font-medium transition-colors duration-200 whitespace-nowrap cursor-pointer",
            )}
            style={{
              color: isActive ? "var(--retro-amber)" : "var(--retro-text-dim)",
              fontFamily: "var(--font-body)",
            }}
            onMouseEnter={(e) => {
              if (!isActive) e.currentTarget.style.color = "var(--retro-text)";
            }}
            onMouseLeave={(e) => {
              if (!isActive) e.currentTarget.style.color = "var(--retro-text-dim)";
            }}
          >
            {tab.label}
            {isActive && (
              <span
                className="absolute bottom-0 left-1 right-1 h-0.5 rounded-full"
                style={{ backgroundColor: "var(--retro-amber)" }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
```

**Step 2: Rewrite RetroInput — remove glow focus, use standard focus ring**

Replace full contents of `frontend/src/components/retro/RetroInput.tsx`:

```tsx
"use client";

import { cn } from "@/lib/utils";

interface RetroInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function RetroInput({ label, className, id, ...props }: RetroInputProps) {
  return (
    <div className="space-y-1.5">
      {label && (
        <label
          htmlFor={id}
          className="text-xs font-medium"
          style={{ color: "var(--retro-text-dim)" }}
        >
          {label}
        </label>
      )}
      <input
        id={id}
        className={cn(
          "w-full px-3 py-2 text-sm border rounded-md outline-none transition-colors duration-200",
          className,
        )}
        style={{
          backgroundColor: "var(--retro-bg-deep)",
          color: "var(--retro-text)",
          borderColor: "var(--retro-border)",
        }}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = "var(--retro-amber)";
          e.currentTarget.style.boxShadow = "0 0 0 2px var(--retro-bg-deep), 0 0 0 4px var(--retro-amber)";
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = "var(--retro-border)";
          e.currentTarget.style.boxShadow = "none";
        }}
        {...props}
      />
    </div>
  );
}
```

**Step 3: Rewrite RetroLoadingState — remove blinking cursor, use pulse-fade**

Replace full contents of `frontend/src/components/retro/RetroLoadingState.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";

interface RetroLoadingStateProps {
  text?: string;
}

export function RetroLoadingState({ text = "Loading" }: RetroLoadingStateProps) {
  const [dots, setDots] = useState("");

  useEffect(() => {
    const interval = setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? "" : prev + "."));
    }, 400);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex items-center justify-center py-16">
      <span
        className="text-sm"
        style={{
          color: "var(--retro-text-dim)",
          fontFamily: "var(--font-body)",
        }}
      >
        {text}
        <span className="inline-block w-6 text-left">{dots}</span>
      </span>
    </div>
  );
}
```

**Step 4: Commit**

```bash
git add frontend/src/components/retro/RetroTabs.tsx frontend/src/components/retro/RetroInput.tsx frontend/src/components/retro/RetroLoadingState.tsx
git commit -m "feat: simplify RetroTabs, RetroInput, RetroLoadingState"
```

---

### Task 9: Update RetroBadge, RetroTable, StatusReadout, TerminalLog

**Files:**
- Modify: `frontend/src/components/retro/RetroBadge.tsx`
- Modify: `frontend/src/components/retro/RetroTable.tsx`
- Modify: `frontend/src/components/retro/StatusReadout.tsx`
- Modify: `frontend/src/components/retro/TerminalLog.tsx`

**Step 1: Update RetroBadge — remove uppercase tracking-wider, round corners**

Replace full contents of `frontend/src/components/retro/RetroBadge.tsx`:

```tsx
"use client";

import { RECORD_TYPE_COLORS, RECORD_TYPE_SHORT, DEFAULT_RECORD_COLOR } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface RetroBadgeProps {
  recordType: string;
  short?: boolean;
  className?: string;
}

export function RetroBadge({ recordType, short = false, className }: RetroBadgeProps) {
  const colors = RECORD_TYPE_COLORS[recordType] || DEFAULT_RECORD_COLOR;
  const label = short
    ? (RECORD_TYPE_SHORT[recordType] || recordType.toUpperCase().slice(0, 4))
    : recordType;

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-md",
        className,
      )}
      style={{
        backgroundColor: colors.bg,
        color: colors.text,
      }}
    >
      {label}
    </span>
  );
}
```

**Step 2: Update RetroTable — remove amber header, clean styling**

Replace full contents of `frontend/src/components/retro/RetroTable.tsx`:

```tsx
"use client";

import { cn } from "@/lib/utils";

export function RetroTable({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-auto">
      <table className={cn("w-full text-sm", className)}>{children}</table>
    </div>
  );
}

export function RetroTableHeader({ children }: { children: React.ReactNode }) {
  return (
    <thead>
      <tr
        className="border-b text-xs font-medium"
        style={{
          borderColor: "var(--retro-border)",
          color: "var(--retro-text-dim)",
        }}
      >
        {children}
      </tr>
    </thead>
  );
}

export function RetroTableHead({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <th className={cn("px-3 py-2 text-left font-medium", className)}>
      {children}
    </th>
  );
}

export function RetroTableBody({ children }: { children: React.ReactNode }) {
  return <tbody>{children}</tbody>;
}

export function RetroTableRow({
  className,
  onClick,
  children,
}: {
  className?: string;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  return (
    <tr
      className={cn(
        "border-b transition-colors duration-150",
        onClick && "cursor-pointer",
        className,
      )}
      style={{ borderColor: "var(--retro-border)" }}
      onClick={onClick}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = "var(--retro-bg-card-hover)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = "transparent";
      }}
    >
      {children}
    </tr>
  );
}

export function RetroTableCell({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <td
      className={cn("px-3 py-2", className)}
      style={{ color: "var(--retro-text)" }}
    >
      {children}
    </td>
  );
}
```

**Step 3: Update StatusReadout — remove separators and uppercase**

Replace full contents of `frontend/src/components/retro/StatusReadout.tsx`:

```tsx
"use client";

interface StatusItem {
  label: string;
  value: string | number;
}

interface StatusReadoutProps {
  items: StatusItem[];
}

export function StatusReadout({ items }: StatusReadoutProps) {
  return (
    <div
      className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 border rounded-lg text-sm"
      style={{
        backgroundColor: "var(--retro-bg-surface)",
        borderColor: "var(--retro-border)",
      }}
    >
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-2">
          <span
            className="text-xs font-medium"
            style={{ color: "var(--retro-text-dim)" }}
          >
            {item.label}:
          </span>
          <span
            className="font-medium"
            style={{ color: "var(--retro-text)" }}
          >
            {item.value}
          </span>
        </span>
      ))}
    </div>
  );
}
```

**Step 4: Update TerminalLog — remove terminal aesthetic**

Replace full contents of `frontend/src/components/retro/TerminalLog.tsx`:

```tsx
"use client";

import { RECORD_TYPE_SHORT, RECORD_TYPE_COLORS, DEFAULT_RECORD_COLOR } from "@/lib/constants";

interface LogEntry {
  id: string;
  timestamp: string | null;
  recordType: string;
  text: string;
}

interface TerminalLogProps {
  entries: LogEntry[];
  onClickEntry?: (id: string) => void;
}

function formatTimestamp(dateStr: string | null): string {
  if (!dateStr) return "--";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function TerminalLog({ entries, onClickEntry }: TerminalLogProps) {
  if (entries.length === 0) {
    return (
      <div className="py-8 text-center">
        <span
          className="text-sm"
          style={{ color: "var(--retro-text-muted)" }}
        >
          No entries yet
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-0">
      {entries.map((entry) => {
        const colors = RECORD_TYPE_COLORS[entry.recordType] || DEFAULT_RECORD_COLOR;
        const shortType = RECORD_TYPE_SHORT[entry.recordType] || entry.recordType.toUpperCase().slice(0, 4);
        return (
          <div
            key={entry.id}
            className="flex items-start gap-3 py-2 border-b transition-colors duration-150"
            style={{
              borderColor: "var(--retro-border)",
              cursor: onClickEntry ? "pointer" : undefined,
            }}
            onClick={() => onClickEntry?.(entry.id)}
            onMouseEnter={(e) => {
              if (onClickEntry) e.currentTarget.style.backgroundColor = "var(--retro-bg-card-hover)";
            }}
            onMouseLeave={(e) => {
              if (onClickEntry) e.currentTarget.style.backgroundColor = "transparent";
            }}
          >
            <span
              className="text-xs shrink-0 font-mono"
              style={{ color: "var(--retro-text-muted)" }}
            >
              {formatTimestamp(entry.timestamp)}
            </span>
            <span
              className="text-xs font-medium shrink-0 px-1.5 py-0.5 rounded"
              style={{
                backgroundColor: colors.bg,
                color: colors.text,
                minWidth: "3rem",
                textAlign: "center",
              }}
            >
              {shortType}
            </span>
            <span
              className="text-sm truncate"
              style={{ color: "var(--retro-text)" }}
            >
              {entry.text}
            </span>
          </div>
        );
      })}
    </div>
  );
}
```

**Step 5: Commit**

```bash
git add frontend/src/components/retro/RetroBadge.tsx frontend/src/components/retro/RetroTable.tsx frontend/src/components/retro/StatusReadout.tsx frontend/src/components/retro/TerminalLog.tsx
git commit -m "feat: soften RetroBadge, RetroTable, StatusReadout, TerminalLog"
```

---

### Task 10: Update RecordDetailSheet

**Files:**
- Modify: `frontend/src/components/retro/RecordDetailSheet.tsx`

**Step 1: Update RecordDetailSheet — remove uppercase, glow references, terminal language**

Key changes to make in `frontend/src/components/retro/RecordDetailSheet.tsx`:
- Line 49: Change `DATA READOUT` → `Record Details`
- Line 49: Remove `uppercase tracking-widest` from SheetTitle className
- Line 59: Change `LOADING RECORD` → `Loading record`
- Line 65: Change `RECORD NOT FOUND` → `Record not found`
- Lines 93–113: Change all label strings from UPPERCASE to Title Case: `TYPE` → `Type`, `FHIR` → `FHIR`, `DATE` → `Date`, `SOURCE` → `Source`, `CODE SYSTEM` → `Code system`, `CODE` → `Code`, `CODE DISPLAY` → `Code display`, `CATEGORIES` → `Categories`, `CREATED` → `Created`
- Line 133: Remove `uppercase tracking-wider` from the toggle button className
- Line 134–135: Change `cursor-pointer` style, remove hover glow color changes
- Line 138: Change `[-] HIDE` / `[+] SHOW` RAW FHIR → `Hide FHIR JSON` / `Show FHIR JSON`
- Line 176: Remove `uppercase tracking-wider` from label span className in `DetailRow`

**Step 2: Commit**

```bash
git add frontend/src/components/retro/RecordDetailSheet.tsx
git commit -m "feat: update RecordDetailSheet — remove uppercase and terminal language"
```

---

### Task 11: Update Dashboard Home Page

**Files:**
- Modify: `frontend/src/app/(dashboard)/page.tsx`

**Step 1: Update text casing and labels in dashboard page**

Key changes to make in `frontend/src/app/(dashboard)/page.tsx`:
- Line 57: Change `SYSTEM STATUS` → `Dashboard`
- Lines 61–65: Change StatusReadout labels from UPPERCASE to Title Case: `RECORDS` → `Records`, `PATIENTS` → `Patients`, `UPLOADS` → `Uploads`, `RANGE` → `Date range`
- Line 72: Change `RECORDS BY CATEGORY` → `Records by category`
- Line 83: Remove `uppercase tracking-wider` from the record-type badge spans
- Line 102: Change `RECENT ACTIVITY LOG` → `Recent activity`
- Line 111: Change `NO RECORDS IN DATABASE` → `No records yet`
- Line 114: Change `UPLOAD FIRST RECORDS` → `Upload records`
- Line 129: Change `CREATE SUMMARY` → `Create summary`
- Line 30: Change `LOADING DASHBOARD` → `Loading dashboard`

**Step 2: Commit**

```bash
git add frontend/src/app/(dashboard)/page.tsx
git commit -m "feat: update dashboard page text to sentence case"
```

---

### Task 12: Update Timeline Page

**Files:**
- Modify: `frontend/src/app/(dashboard)/timeline/page.tsx`

**Step 1: Update text casing and styles in timeline page**

Key changes to make in `frontend/src/app/(dashboard)/timeline/page.tsx`:
- Line 13–22: Update filter labels from ALL-CAPS to mixed case. Keep the short codes as-is since they're data labels: `ALL`, `COND`, `OBS`, etc. are fine as abbreviations.
- Line 81: Change `TIMELINE` → `Timeline`
- Line 87: Change `{data.total} EVENTS` → `{data.total} events`
- Line 100: Remove `uppercase tracking-wider` from filter buttons
- Line 106: Remove `fontFamily: "var(--font-display)"` from filter buttons (use body font)
- Line 128: Change `LOADING TIMELINE` → `Loading timeline`
- Line 138: Change `NO EVENTS IN DATABASE` → `No events found`
- Line 143: Change `CLEAR FILTER` → `Clear filter`, remove `uppercase tracking-wider`
- Line 172: Remove `tracking-widest` from month/year dividers, change `fontFamily` to body

**Step 2: Commit**

```bash
git add frontend/src/app/(dashboard)/timeline/page.tsx
git commit -m "feat: update timeline page text to sentence case"
```

---

### Task 13: Update Summaries Page

**Files:**
- Modify: `frontend/src/app/(dashboard)/summaries/page.tsx`

**Step 1: Update text casing in summaries page**

Key changes to make in `frontend/src/app/(dashboard)/summaries/page.tsx`:
- Line 21–24: Change SUMMARY_TYPES labels: `FULL` → `Full`, `CATEGORY` → `Category`, `DATE RANGE` → `Date range`
- Line 36–38: Change OUTPUT_TABS labels: `NATURAL LANGUAGE` → `Natural language`, `JSON DATA` → `JSON data`
- Line 132: Change `AI HEALTH SUMMARY` → `AI Health Summary`
- Line 144: Change `SELECT PATIENT` → `Select patient`
- Line 186: Change `DEDUP` → `Dedup`
- Line 203: Change `CONFIGURATION` → `Configuration`
- Line 218: Change `SUMMARY TYPE` → `Summary type`
- Line 236: Change `CATEGORY` → `Category`
- Line 270–295: Change `FROM` / `TO` → `From` / `To`
- Line 322: Change `OUTPUT FORMAT` → `Output format`
- Line 362: Change `- HIDE` / `+ CUSTOMIZE PROMPT` → `Hide prompt options` / `Customize prompt`
- Line 395: Change `GENERATING...` → `Generating...`, `GENERATE SUMMARY` → `Generate summary`
- Line 402: Change `CONTACTING GEMINI 3 FLASH` → `Generating summary`
- Line 418: Change `ERROR` badge (keep as-is, it's a semantic label)
- Line 434: Change `SUMMARY RESULTS` → `Summary results`
- Line 516: Change `DE-IDENTIFICATION REPORT` → `De-identification report`
- Line 564: Change `WARNING` → `Notice`
- Line 590: Change `- HIDE` / `+ SUMMARY HISTORY` → `Hide history` / `Summary history`
- All label `fontFamily` references: Change from `--font-display` to `--font-body` (or remove the inline style to use body default)
- Remove all `tracking-wider` and `tracking-widest` from labels

**Step 2: Commit**

```bash
git add frontend/src/app/(dashboard)/summaries/page.tsx
git commit -m "feat: update summaries page text to sentence case"
```

---

### Task 14: Update Admin Page

**Files:**
- Modify: `frontend/src/app/(dashboard)/admin/page.tsx`

**Step 1: Update admin page tabs and text casing**

This is the largest file (~1360 lines). Key changes:

**Tab definitions (lines 39–51):**
Change labels from ALL-CAPS to Title Case:
```tsx
const TABS = [
  { key: "all", label: "All" },
  { key: "labs", label: "Labs" },
  { key: "meds", label: "Meds" },
  { key: "cond", label: "Conditions" },
  { key: "enc", label: "Encounters" },
  { key: "immun", label: "Immunizations" },
  { key: "img", label: "Imaging" },
  { key: "upload", label: "Upload" },
  { key: "dedup", label: "Dedup" },
  { key: "sys", label: "System" },
];
```

Note: Remove the separator tab entry entirely (`{ key: "sep", label: "|", separator: true }`).

**Page header (line 66):**
Change `ADMIN CONSOLE` → `Admin Console`

**AllRecordsTab:**
- Line 128: Change `SEARCH` → `Search`
- Line 144: Keep `ALL TYPES` as-is (select option)
- Line 155–163: Change `NO RECORDS FOUND` → `No records found`, `CLEAR FILTERS` → `Clear filter`, remove `uppercase tracking-wider`
- Lines 223–231: Change `PREV` / `NEXT` → `Prev` / `Next`
- Line 150: Change `LOADING RECORDS` → `Loading records`

**LabsTab:**
- Line 283: Change `LOADING LAB RESULTS` → `Loading lab results`
- Line 291: Change `NO LAB RESULTS FOUND` → `No lab results found`
- Remove `uppercase tracking-wider` from interpretation labels (line 344)

**RecordTypeTab:**
- Line 389: Change `LOADING ${label}` → `Loading ${label.toLowerCase()}`
- Line 398: Change `NO ${label} FOUND` → `No ${label.toLowerCase()} found`
- Remove `uppercase tracking-wider` from status labels (line 425)

**UploadTab:**
- Line 520–528: Change `DROP FILES TO INITIATE DATA TRANSFER` → `Drop files here to upload`
- Line 530: Change `JSON or ZIP files up to 500MB` (keep as-is)
- Lines 551–554: Change `REMOVE` → `Remove`, `UPLOADING...` → `Uploading...`, `UPLOAD` → `Upload`
- Line 588: Change `UPLOAD COMPLETE` → `Upload complete`
- Lines 593–609: Change `STATUS`, `RECORDS INSERTED`, `ERRORS` → `Status`, `Records inserted`, `Errors`

**UnstructuredUploadSection:**
- Line 792: Change `UNSTRUCTURED DATA UPLOAD` → `Unstructured document upload`
- Line 811: Change `DROP PDF, RTF, OR TIFF FOR AI EXTRACTION` → `Drop PDF, RTF, or TIFF for AI extraction`
- Line 829–830: Change `REMOVE` → `Remove`, `EXTRACT` → `Extract`
- Line 844–847: Change `EXTRACTING TEXT AND ENTITIES` → `Extracting text and entities`, remove `blink-cursor`
- Line 871: Change `EXTRACTION CONFIRMED` → `Extraction confirmed`
- Line 886: Change `REVIEW EXTRACTED ENTITIES` → `Review extracted entities`
- Line 896: Change `ASSIGN TO PATIENT` → `Assign to patient`
- Line 971: Change `SAVING...` / `CONFIRM & SAVE ${n} ENTITIES` → `Saving...` / `Confirm ${n} entities`

**DedupTab:**
- Line 1055: Change `SCANNING...` / `SCAN FOR DUPLICATES` → `Scanning...` / `Scan for duplicates`
- Line 1091: Change `NO DUPLICATE CANDIDATES FOUND` → `No duplicate candidates`
- Lines 1108–1109: Change `PREV` / `NEXT` → `Prev` / `Next`
- Line 1148–1155: Change `MERGE` / `DISMISS` → `Merge` / `Dismiss`
- Remove `uppercase tracking-wider` from match reason badges (line 1131)

**SystemTab:**
- Line 1237: Change `LOADING SYSTEM INFO` → `Loading system info`
- Line 1249: Change `ACCOUNT INFORMATION` → `Account information`
- Lines 1255–1261: Change label strings to title case: `EMAIL` → `Email`, `DISPLAY NAME` → `Display name`, `STATUS` → `Status`, `USER ID` → `User ID`
- Line 1274: Change `DATA STATISTICS` → `Data statistics`
- Lines 1279–1282: Change to title case: `TOTAL RECORDS` → `Total records`, etc.
- Line 1300: Change `SIGN OUT` → `Sign out`
- Line 1315: Change `NOTICE` badge label (keep short)
- Remove `uppercase tracking-wider` from SysRow label (line 1350)

**Step 2: Commit**

```bash
git add frontend/src/app/(dashboard)/admin/page.tsx
git commit -m "feat: update admin page — sentence case, remove terminal language"
```

---

### Task 15: Update Records Detail Page

**Files:**
- Modify: `frontend/src/app/(dashboard)/records/[id]/page.tsx`

**Step 1: Update text casing in record detail page**

Key changes to make in `frontend/src/app/(dashboard)/records/[id]/page.tsx`:
- Line 32: Change `LOADING RECORD` → `Loading record`
- Line 40: Change `< BACK TO RECORDS` → `Back to records`, remove `uppercase tracking-wider`
- Line 46: Change `RECORD NOT FOUND` → `Record not found`
- Line 57: Same back link update
- Line 74: Change `RECORD DETAILS` → `Record details`
- Lines 79–100: Change all label strings to title case: `RECORD TYPE` → `Record type`, `FHIR RESOURCE TYPE` → `FHIR resource type`, `EFFECTIVE DATE` → `Effective date`, `STATUS` → `Status`, `SOURCE FORMAT` → `Source format`, `CODE SYSTEM` → `Code system`, `CODE VALUE` → `Code value`, `CODE DISPLAY` → `Code display`, `CATEGORIES` → `Categories`, `CREATED AT` → `Created`
- Line 108: Change `FHIR RESOURCE (JSON)` → `FHIR Resource (JSON)`
- Line 110: Change `HIDE` / `SHOW` RAW FHIR → `Hide` / `Show` FHIR
- Line 140: Remove `uppercase tracking-wider` from DetailRow label

**Step 2: Commit**

```bash
git add frontend/src/app/(dashboard)/records/[id]/page.tsx
git commit -m "feat: update record detail page — sentence case"
```

---

### Task 16: Update Providers Default Theme

**Files:**
- Modify: `frontend/src/components/Providers.tsx`

**Step 1: Change defaultTheme from "dark" to "system"**

In `frontend/src/components/Providers.tsx`, change line 21:
```tsx
<ThemeProvider attribute="class" defaultTheme="system" enableSystem>
```

**Step 2: Commit**

```bash
git add frontend/src/components/Providers.tsx
git commit -m "feat: default to system theme preference"
```

---

### Task 17: Rename CSS Variables — `--retro-*` → `--theme-*`

**Files:**
- Modify: All 20 files that reference `--retro-*` variables

**Step 1: Global find-and-replace `--retro-` → `--theme-` in all frontend source files**

This is a bulk search-and-replace across:
- `frontend/src/app/globals.css`
- All 12 remaining components in `frontend/src/components/retro/`
- All page files in `frontend/src/app/`
- `frontend/src/lib/constants.ts` (if it references CSS vars)

Use a single sed command or editor find-and-replace:
```bash
find frontend/src -type f \( -name "*.tsx" -o -name "*.ts" -o -name "*.css" \) -exec sed -i '' 's/--retro-/--theme-/g' {} +
```

**Step 2: Verify no remaining `--retro-` references**

Run: `grep -r "\-\-retro\-" frontend/src/`
Expected: No matches.

**Step 3: Verify dev server still works**

Run: `cd frontend && npm run dev`
Expected: Site loads correctly with all styles applied.

**Step 4: Commit**

```bash
git add frontend/src/
git commit -m "refactor: rename CSS variables --retro-* to --theme-*"
```

---

### Task 18: Visual Verification + Final Commit

**Step 1: Start the dev server and verify all pages**

Run: `cd frontend && npm run dev`

Check these pages in both light and dark mode:
- [ ] `/login` — warm cream/forest card, no CRT overlay
- [ ] `/register` — same as login
- [ ] `/` (dashboard) — earth-tone cards, no glow text, sentence case
- [ ] `/timeline` — forest-colored timeline line, clean cards
- [ ] `/summaries` — clean form, no uppercase labels
- [ ] `/admin` — all tabs load, sentence case throughout
- [ ] `/admin?tab=upload` — dropzone clean, no terminal language
- [ ] `/admin?tab=dedup` — merge/dismiss buttons styled correctly
- [ ] `/admin?tab=sys` — system info clean
- [ ] Theme toggle works in nav

**Step 2: Take a screenshot of the home page for comparison**

**Step 3: Final cleanup commit if needed**

```bash
git add -A
git commit -m "feat: Forest Floor theme redesign complete"
```

---

## Summary of All Files Changed

| File | Action |
|------|--------|
| `frontend/src/app/globals.css` | Major rewrite: new palette, remove CRT effects |
| `frontend/src/components/retro/CRTOverlay.tsx` | **Deleted** |
| `frontend/src/components/retro/GlowText.tsx` | Simplified: no glow |
| `frontend/src/components/retro/RetroButton.tsx` | Rewritten: no pulse/glow/uppercase |
| `frontend/src/components/retro/RetroCard.tsx` | Updated: shadow, rounded corners |
| `frontend/src/components/retro/RetroNav.tsx` | Rewritten: no F-keys/glow/uppercase |
| `frontend/src/components/retro/RetroTabs.tsx` | Rewritten: no separators/glow/uppercase |
| `frontend/src/components/retro/RetroInput.tsx` | Updated: standard focus ring |
| `frontend/src/components/retro/RetroLoadingState.tsx` | Simplified: no blinking cursor |
| `frontend/src/components/retro/RetroBadge.tsx` | Updated: rounded, no uppercase |
| `frontend/src/components/retro/RetroTable.tsx` | Updated: clean headers |
| `frontend/src/components/retro/StatusReadout.tsx` | Simplified: no separators |
| `frontend/src/components/retro/TerminalLog.tsx` | Simplified: clean date format |
| `frontend/src/components/retro/RecordDetailSheet.tsx` | Updated: sentence case |
| `frontend/src/app/(dashboard)/layout.tsx` | Remove CRTOverlay |
| `frontend/src/app/(auth)/login/page.tsx` | Remove CRTOverlay, sentence case |
| `frontend/src/app/(auth)/register/page.tsx` | Remove CRTOverlay, sentence case |
| `frontend/src/app/(dashboard)/page.tsx` | Sentence case |
| `frontend/src/app/(dashboard)/timeline/page.tsx` | Sentence case |
| `frontend/src/app/(dashboard)/summaries/page.tsx` | Sentence case |
| `frontend/src/app/(dashboard)/admin/page.tsx` | Major: sentence case throughout |
| `frontend/src/app/(dashboard)/records/[id]/page.tsx` | Sentence case |
| `frontend/src/components/Providers.tsx` | defaultTheme → "system" |
