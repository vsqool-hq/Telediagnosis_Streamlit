"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { LogOut, Cloud, Laptop } from "lucide-react";
import { clearToken, getToken, isLocalBackend } from "@/lib/api";
import { NAV, isActive } from "@/components/nav";

export default function Sidebar() {
  const pathname = usePathname();
  const [local, setLocal] = useState(false);
  useEffect(() => setLocal(isLocalBackend()), []);

  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-white/10 bg-black/20 px-4 py-6 md:flex">
      <div className="mb-8 flex items-center gap-3 px-2">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png" alt="Telediagnosis" className="h-11 w-11 rounded-[13px]" />
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
      <div className={`mx-1 mb-1 flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs ${local ? "text-amber-300" : "text-slate-400"}`}>
        {local ? <Laptop size={14} /> : <Cloud size={14} />}
        Silnik: {local ? "Ten komputer" : "Chmura"}
      </div>
      <p className="px-3 text-xs text-slate-500">v0.2 · {new Date().getFullYear()}</p>
    </aside>
  );
}
