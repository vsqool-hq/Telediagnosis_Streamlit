"use client";

// Animowane „dobijanie" liczby do wartości docelowej (np. przychód na Pulpicie).
// Szanuje prefers-reduced-motion (wtedy pokazuje wartość od razu).
import { useEffect, useRef, useState } from "react";

export default function CountUp({
  value, format, durationMs = 650,
}: {
  value: number;
  format?: (n: number) => string;
  durationMs?: number;
}) {
  const [display, setDisplay] = useState(0);
  const fromRef = useRef(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const from = fromRef.current;
    const to = Number.isFinite(value) ? value : 0;
    if (reduce || from === to) {
      setDisplay(to);
      fromRef.current = to;
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      setDisplay(from + (to - from) * eased);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = to;
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [value, durationMs]);

  return <>{format ? format(display) : Math.round(display).toLocaleString("pl-PL")}</>;
}
