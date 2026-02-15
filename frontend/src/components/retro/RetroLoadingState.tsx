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
          color: "var(--theme-text-dim)",
          fontFamily: "var(--font-body)",
        }}
      >
        {text}
        <span className="inline-block w-6 text-left">{dots}</span>
      </span>
    </div>
  );
}
