"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV, isActive } from "@/components/nav";

/** Poziomy pasek zakładek widoczny na węższych ekranach (telefon/tablet). */
export default function MobileNav() {
  const pathname = usePathname();

  return (
    <div className="mb-6 md:hidden">
      <div className="flex gap-1.5 overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.04] p-2 backdrop-blur-sm">
        {NAV.map(({ href, short, icon: Icon }) => {
          const active = isActive(href, pathname);
          return (
            <Link
              key={href}
              href={href}
              className={`navlink shrink-0 ${active ? "navlink-active" : ""}`}
            >
              <Icon size={18} />
              {short}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
