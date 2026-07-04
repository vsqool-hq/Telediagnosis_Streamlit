"use client";

import { Building2 } from "lucide-react";
import { api } from "@/lib/api";
import ExclusionSettings from "@/components/ExclusionSettings";

export default function UnitsSettings() {
  return (
    <ExclusionSettings
      icon={<Building2 size={18} className="text-brand-accent" />}
      title="Ustawienia jednostek"
      description={<>
        Zaznacz jednostki (z kolumny „Klient" w ostatnio wgranym pliku rozliczeniowym),
        które chcesz <b className="text-slate-200">wyłączyć</b> z rozliczenia. Wyłączona jednostka
        znika z Pulpitu, trendu, Mapy i Porównania (badania pomijane po obu stronach marży).
        Rozliczenie lekarzy pozostaje bez zmian — lekarzy wyłączasz osobno powyżej.
      </>}
      cacheKey="unitsList"
      load={() => api.unitsList().then((r) => r.units)}
      save={(keys) => api.setUnitsExcluded(keys)}
      savedMsg={'Zapisano. Pulpit i Mapa odświeżą się same; na Porównaniu kliknij „Policz porównanie".'}
      searchPlaceholder="Szukaj jednostki…"
      excludedPill="wyłączona"
      emptyMsg="Brak danych — uruchom najpierw pełne rozliczenie jednostek."
    />
  );
}
