import {
  LayoutDashboard,
  PlayCircle,
  BookText,
  ReceiptText,
  History,
  SlidersHorizontal,
  Stethoscope,
  Wallet,
  Scale,
  Map as MapIcon,
  Users,
  AlarmClockCheck,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  short: string;
  icon: LucideIcon;
  adminOnly?: boolean;   // widoczne tylko dla administratora
}

export const NAV: NavItem[] = [
  { href: "/", label: "Pulpit", short: "Pulpit", icon: LayoutDashboard },
  { href: "/rozliczenie", label: "Rozliczenie", short: "Rozliczenie", icon: PlayCircle, adminOnly: true },
  { href: "/wzorcowe", label: "Pliki wzorcowe", short: "Wzorcowe", icon: BookText, adminOnly: true },
  { href: "/cennik", label: "Cennik", short: "Cennik", icon: ReceiptText, adminOnly: true },
  { href: "/historia", label: "Historia", short: "Historia", icon: History },
  { href: "/rozliczenie-lekarzy", label: "Rozliczenie lekarzy", short: "Lekarze", icon: Stethoscope },
  { href: "/cennik-lekarzy", label: "Cennik lekarzy", short: "Cennik lek.", icon: Wallet, adminOnly: true },
  { href: "/porownanie", label: "Porównanie", short: "Porównanie", icon: Scale },
  { href: "/mapa", label: "Mapa", short: "Mapa", icon: MapIcon },
  { href: "/windykacja", label: "Windykacja", short: "Windykacja", icon: AlarmClockCheck },
  { href: "/uzytkownicy", label: "Użytkownicy", short: "Konta", icon: Users, adminOnly: true },
  { href: "/ustawienia", label: "Ustawienia", short: "Ustawienia", icon: SlidersHorizontal, adminOnly: true },
];

export function isActive(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}
