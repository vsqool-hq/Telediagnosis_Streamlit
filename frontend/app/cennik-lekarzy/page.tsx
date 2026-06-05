import VersionManager from "@/components/VersionManager";
import CennikLekarzyConverter from "@/components/CennikLekarzyConverter";

export default function CennikLekarzyPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[26px] font-extrabold tracking-tight">Cennik lekarzy</h1>
        <p className="text-sm text-slate-400">
          Konwerter skoroszytu „ZOBOWIĄZANIA LEKARZY" (zakładka = lekarz) → cennik 3-kolumnowy
          Lekarz;Kategoria;Cena, oraz wersjonowanie. Używany przy rozliczeniu lekarzy.
        </p>
      </header>

      <CennikLekarzyConverter />

      <VersionManager
        kind="cennik_lekarzy"
        title="Wersje cennika lekarzy"
        description="Wgraj gotowy cennik lekarzy (CSV) lub zapisz wynik konwersji. Wskaż wersję aktywną."
        accept=".csv"
        embedded
      />
    </div>
  );
}
