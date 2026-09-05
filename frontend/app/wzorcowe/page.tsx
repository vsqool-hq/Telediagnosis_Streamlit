import VersionManager from "@/components/VersionManager";

export default function WzorcowePage() {
  return (
    <VersionManager
      kind="wzorcowe"
      title="Pliki wzorcowe (słownik)"
      description="Słownik procedur i okolic anatomicznych. Wgraj nowe wersje i wskaż, która ma być używana przy rozliczeniach."
      accept=".xlsx,.xls"
      allowAppend
    />
  );
}
