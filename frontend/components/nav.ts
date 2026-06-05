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
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  short: string;
  icon: LucideIcon;
}

export const NAV: NavItem[] = [
  { href: "/", label: "Pulpit", short: "Pulpit", icon: LayoutDashboard },
  { href: "/rozliczenie", label: "Rozliczenie", short: "Rozliczenie", icon: PlayCircle },
  { href: "/wzorcowe", label: "Pliki wzorcowe", short: "Wzorcowe", icon: BookText },
  { href: "/cennik", label: "Cennik", short: "Cennik", icon: ReceiptText },
  { href: "/historia", label: "Historia", short: "Historia", icon: History },
  { href: "/rozliczenie-lekarzy", label: "Rozliczenie lekarzy", short: "Lekarze", icon: Stethoscope },
  { href: "/cennik-lekarzy", label: "Cennik lekarzy", short: "Cennik lek.", icon: Wallet },
  { href: "/porownanie", label: "Porównanie", short: "Porównanie", icon: Scale },
  { href: "/ustawienia", label: "Ustawienia", short: "Ustawienia", icon: SlidersHorizontal },
];

export function isActive(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}
