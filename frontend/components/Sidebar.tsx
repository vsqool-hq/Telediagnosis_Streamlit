"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Plus, LogOut } from "lucide-react";
import { clearToken, getToken } from "@/lib/api";
import { NAV, isActive } from "@/components/nav";

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-white/10 bg-black/20 px-4 py-6 md:flex">
      <div className="mb-8 flex items-center gap-3 px-2">
        <div className="flex h-11 w-11 items-center justify-center rounded-[13px] bg-gradient-to-b from-brand-accent2 to-brand-accent text-[#04130b]">
          <Plus size={24} strokeWidth={2.6} />
        </div>
        <div>
          <p className="font-extrabold leading-tight">Telediagnosis</p>
          <p className="text-xs text-slate-400">Rozliczenia</p>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = isActive(href, pathname);
          return (
            <Link key={href} href={href} className={`navlink ${active ? "navlink-active" : ""}`}>
              <Icon size={19} />
              {label}
            </Link>
          );
        })}
      </nav>

      {getToken() && (
        <button
          onClick={() => { clearToken(); window.location.reload(); }}
          className="navlink !text-slate-400"
        >
          <LogOut size={19} />
          Wyloguj
        </button>
      )}
      <p className="px-3 pt-1.5 text-xs text-slate-500">v0.2 · {new Date().getFullYear()}</p>
    </aside>
  );
}
