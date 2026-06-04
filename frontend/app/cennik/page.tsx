import VersionManager from "@/components/VersionManager";

export default function CennikPage() {
  return (
    <VersionManager
      kind="cennik"
      title="Cennik"
      description="Cennik badań per jednostka (CSV: BADANIE;Jednostka;Cena). Wgraj nowe wersje i wskaż aktywną."
      accept=".csv"
    />
  );
}
