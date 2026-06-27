"use client";

// Lekki system powiadomień (toastów) bez zewnętrznych bibliotek.
// Użycie: import { toast } from "@/lib/toast"; toast("Zapisano"); toast("Błąd", "error");

export type ToastItem = { id: number; msg: string; kind: "ok" | "error" };
type Listener = (items: ToastItem[]) => void;

let items: ToastItem[] = [];
let counter = 0;
const listeners = new Set<Listener>();

function emit() {
  for (const l of listeners) l(items);
}

export function subscribeToasts(l: Listener) {
  listeners.add(l);
  l(items);
  return () => {
    listeners.delete(l);
  };
}

export function toast(msg: string, kind: "ok" | "error" = "ok") {
  const item: ToastItem = { id: ++counter, msg, kind };
  items = [...items, item];
  emit();
  setTimeout(() => {
    items = items.filter((x) => x.id !== item.id);
    emit();
  }, 3500);
}
