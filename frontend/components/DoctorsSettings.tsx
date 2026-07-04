"use client";

import { Stethoscope } from "lucide-react";
import { api } from "@/lib/api";
import ExclusionSettings from "@/components/ExclusionSettings";

export default function DoctorsSettings() {
  return (
    <ExclusionSettings
      icon={<Stethoscope size={18} className="text-brand-accent" />}
      title="Ustawienia lekarzy"
      description={<>
        Zaznacz lekarzy (z kolumny „Opisujący" w ostatnio wgranym pliku rozliczeniowym),
        których chcesz <b className="text-slate-200">wyłączyć</b> z rozliczenia lekarzy — np. rozliczanych
        osobno. Ich badania zostaną pominięte przy liczeniu stawek.
      </>}
      cacheKey="doctorsList"
      load={() => api.doctorsList().then((r) => r.doctors)}
      save={(keys) => api.setDoctorsExcluded(keys)}
      savedMsg={'Zapisano. Na zakładce „Rozliczenie lekarzy" kliknij „Przelicz ponownie".'}
      searchPlaceholder="Szukaj lekarza…"
      excludedPill="wyłączony"
      emptyMsg="Brak danych — uruchom najpierw pełne rozliczenie jednostek."
    />
  );
}
