import VersionManager from "@/components/VersionManager";
import CennikConverter from "@/components/CennikConverter";

export default function CennikPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[26px] font-extrabold tracking-tight">Cennik</h1>
        <p className="text-sm text-slate-400">
          Konwerter cennika zbiorczego (szeroki Excel → CSV) oraz wersjonowanie gotowych cenników.
          Format docelowy: BADANIE;Jednostka;Cena.
        </p>
      </header>

      <CennikConverter />

      <VersionManager
        kind="cennik"
        title="Wersje cennika"
        description="Wgraj gotowy cennik (CSV) lub zapisz wynik konwersji. Wskaż wersję aktywną używaną przy rozliczeniach."
        accept=".csv"
        embedded
      />
    </div>
  );
}
