"use client";

import { GitCompareArrows } from "lucide-react";
import { api } from "@/lib/api";
import ExclusionSettings from "@/components/ExclusionSettings";

export default function ComparativeUnitsSettings() {
  return (
    <ExclusionSettings
      icon={<GitCompareArrows size={18} className="text-brand-accent" />}
      title="Badania porównawcze — jednostki"
      description={<>
        Zaznacz jednostki, dla których <b className="text-slate-200">liczymy badania porównawcze</b> —
        czyli doliczamy dodatkową (drugą) linię po stawce porównawczej z cennika. Dla jednostek
        niezaznaczonych porównawcze NIE są doliczane. Działa spójnie wszędzie: tabela rozliczenia
        jednostek, Pulpit, Porównanie i Faktury. (Uwaga: doliczenie i tak wymaga stawki
        „… PORÓWNAWCZE …" w cenniku danej jednostki.)
      </>}
      cacheKey="comparativeUnitsList"
      load={() => api.comparativeUnitsList().then((r) => r.units)}
      save={(keys) => api.setComparativeUnits(keys)}
      savedMsg={'Zapisano. Pulpit odświeży się sam; na Porównaniu kliknij „Policz porównanie", a rozliczenie/faktury policz ponownie.'}
      searchPlaceholder="Szukaj jednostki…"
      excludedPill="liczone"
      emptyMsg="Brak danych — uruchom najpierw pełne rozliczenie jednostek."
      mode="include"
      counterLabel="Z porównawczymi"
    />
  );
}
