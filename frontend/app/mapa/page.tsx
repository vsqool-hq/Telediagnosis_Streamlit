"use client";

import { useEffect, useRef } from "react";
import { api, MapData } from "@/lib/api";
import { useCachedData } from "@/lib/cache";

const zl = (n: number) =>
  n.toLocaleString("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 });

const HEAT = ["#2c7fb8", "#41b6c4", "#a1dab4", "#fecc5c", "#fd8d3c", "#e31a1c"];

// Ładuje Leaflet (CSS+JS) z CDN raz; zwraca globalne `L`.
function loadLeaflet(): Promise<any> {
  const w = window as any;
  if (w.L) return Promise.resolve(w.L);
  if (!document.getElementById("leaflet-css")) {
    const link = document.createElement("link");
    link.id = "leaflet-css";
    link.rel = "stylesheet";
    link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    document.head.appendChild(link);
  }
  return new Promise((resolve, reject) => {
    const existing = document.getElementById("leaflet-js") as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve((window as any).L));
      if ((window as any).L) resolve((window as any).L);
      return;
    }
    const sc = document.createElement("script");
    sc.id = "leaflet-js";
    sc.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    sc.onload = () => resolve((window as any).L);
    sc.onerror = reject;
    document.body.appendChild(sc);
  });
}

function heatColor(frac: number): string {
  const stops = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0];
  for (let i = 0; i < stops.length; i++) if (frac <= stops[i]) return HEAT[i];
  return HEAT[HEAT.length - 1];
}

export default function MapaPage() {
  const { data, loading, error } = useCachedData<MapData>("mapData", () => api.mapData(), 300_000);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const layerRef = useRef<any>(null);

  useEffect(() => {
    if (!data || !containerRef.current) return;
    let cancelled = false;
    loadLeaflet()
      .then((L) => {
        if (cancelled || !containerRef.current) return;
        if (!mapRef.current) {
          mapRef.current = L.map(containerRef.current).setView([52.0, 19.3], 6);
          L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: "© OpenStreetMap",
          }).addTo(mapRef.current);
          layerRef.current = L.layerGroup().addTo(mapRef.current);
        }
        layerRef.current.clearLayers();
        const units = data.units;
        const max = Math.max(1, ...units.map((u) => u.latest));
        const months = [...data.months].reverse(); // najnowszy miesiąc na górze
        units.forEach((u) => {
          const frac = Math.min(1, u.latest / max);
          const radius = 6 + Math.sqrt(frac) * 22;
          const color = heatColor(frac);
          const rows = months.map((m) => `${m}: <b>${zl(u.months[m] ?? 0)}</b>`).join("<br>");
          L.circleMarker([u.lat, u.lng], {
            radius,
            color,
            weight: 1,
            fillColor: color,
            fillOpacity: 0.7,
          })
            .bindTooltip(`<div style="min-width:140px"><b>${u.miasto}</b><br>${rows}</div>`, {
              direction: "top",
              opacity: 0.95,
            })
            .addTo(layerRef.current);
        });
        mapRef.current.invalidateSize();
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [data]);

  // Sprzątanie mapy przy opuszczeniu zakładki.
  useEffect(
    () => () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    },
    [],
  );

  const latestMonth = data?.months[data.months.length - 1] ?? "—";
  const total = data?.units.reduce((a, u) => a + u.latest, 0) ?? 0;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-[26px] font-extrabold tracking-tight">Mapa</h1>
        <p className="text-sm text-slate-400">
          Rozliczone jednostki na mapie. Wielkość i kolor punktu = przychód za ostatni miesiąc
          (większy i cieplejszy = więcej). Najedź na punkt, aby zobaczyć kwoty z ostatnich miesięcy.
        </p>
      </header>

      {error && <div className="card border-red-500/40 text-red-300">{error}</div>}
      {!data && loading && (
        <div className="card p-0">
          <div className="skeleton h-[70vh] w-full" />
        </div>
      )}

      {data && (
        <>
          <div className="card flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <span className="text-slate-300">
              Jednostki na mapie: <b>{data.units.length}</b>
            </span>
            <span className="text-slate-300">
              Przychód ({latestMonth}): <b className="text-brand-accent2">{zl(total)}</b>
            </span>
            {data.missing_geo.length > 0 && (
              <span className="text-amber-300">
                Bez współrzędnych: {data.missing_geo.length}{" "}
                ({data.missing_geo.slice(0, 5).join(", ")}
                {data.missing_geo.length > 5 ? "…" : ""})
              </span>
            )}
          </div>

          <div className="card overflow-hidden p-0">
            <div ref={containerRef} className="h-[70vh] w-full" style={{ background: "#0e3b49" }} />
          </div>

          <div className="card flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span>Mniej</span>
            {HEAT.map((c) => (
              <span key={c} className="inline-block h-3 w-7 rounded" style={{ background: c }} />
            ))}
            <span>Więcej — przychód jednostki za ostatni miesiąc ({latestMonth}).</span>
          </div>
        </>
      )}
    </div>
  );
}
