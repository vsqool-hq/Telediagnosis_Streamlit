"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  PlayCircle,
  BookText,
  ReceiptText,
  History,
  Settings,
  Activity,
  LogOut,
} from "lucide-react";
import { clearToken, getToken } from "@/lib/api";

const NAV = [
  { href: "/", label: "Pulpit", icon: LayoutDashboard },
  { href: "/rozliczenie", label: "Rozliczenie", icon: PlayCircle },
  { href: "/wzorcowe", label: "Pliki wzorcowe", icon: BookText },
  { href: "/cennik", label: "Cennik", icon: ReceiptText },
  { href: "/historia", label: "Historia", icon: History },
  { href: "/ustawienia", label: "Ustawienia", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-brand-border/60 bg-brand-surface/30 px-4 py-6 md:flex">
      <div className="mb-8 flex items-center gap-3 px-2">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-accent/20 text-brand-accent">
          <Activity size={22} />
        </div>
        <div>
          <p className="text-sm font-bold leading-tight">Telediagnosis</p>
          <p className="text-xs text-slate-400">Rozliczenia</p>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                active
                  ? "bg-brand-accent/15 text-brand-accent"
                  : "text-slate-300 hover:bg-brand-bg/50 hover:text-white"
              }`}
            >
              <Icon size={18} />
              {label}
            </Link>
          );
        })}
      </nav>

      {getToken() && (
        <button
          onClick={() => { clearToken(); window.location.reload(); }}
          className="mb-2 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-400 transition-colors hover:bg-brand-bg/50 hover:text-white"
        >
          <LogOut size={18} />
          Wyloguj
        </button>
      )}
      <p className="px-3 text-xs text-slate-500">v0.1 · {new Date().getFullYear()}</p>
    </aside>
  );
}
