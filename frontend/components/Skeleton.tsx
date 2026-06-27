"use client";

// Migoczący placeholder na czas ładowania (klasa .skeleton z globals.css).
export default function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}
