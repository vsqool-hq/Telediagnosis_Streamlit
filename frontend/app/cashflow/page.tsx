"use client";

import {
  LineChart as ReLineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine, Legend,
} from "recharts";
import { LineChart as LineChartIcon, Wallet, AlertTriangle, TrendingUp, Info } from "lucide-react";
import { api, CashflowOverview } from "@/lib/api";
import { useCachedData } from "@/lib/cache";
import Skeleton from "@/components/Skeleton";

const TOOLTIP_STYLE = { background: "#0e3b49", border: "1px solid #214652", borderRadius: 12 };
const REVENUE_COLOR = "#1dab5a";
const REVENUE_COLOR_SOFT = "#25c96b";
const COST_COLOR = "#9b6cf0";

const zl = (n?: number | null) =>
  n === undefined || n === null ? "—" : n.toLocaleString("pl-PL", { style: "currency", currency: "PLN", maximumFractionDigits: 0 });

function Tile({
  icon, label, value, sub, tone = "default",
}: { icon: React.ReactNode; label: string; value: React.ReactNode; sub?: string; tone?: "default" | "good" | "bad" }) {
  const valueClass = tone === "good" ? "text-brand-accent2" : tone === "bad" ? "text-red-300" : "";
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400">{label}</p>
        <span className="text-brand-accent">{icon}</span>
      </div>
      <p className={`mt-2.5 truncate text-[26px] font-extrabold leading-none ${valueClass}`}>{value}</p>
      {sub && <p className="mt-1.5 truncate text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

export default function CashflowPage() {
  const { data, error } = useCachedData<CashflowOverview>("cashflow-overview", () => api.cashflowOverview(), 5 * 60_000);
  const k = data?.kpis;

  const barData = (data?.buckets ?? []).map((b) => ({
    label: b.label,
    wpływy: round2(b.inflow_actual + b.inflow_forecast),
    koszty: round2(-b.outflow_forecast),
    isPast: b.index < 0,
  }));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-[26px] font-extrabold tracking-tight">
          <LineChartIcon className="text-brand-accent" size={24} /> Cashflow
        </h1>
        <p className="text-sm text-slate-400">
          Przepływy pieniężne: przychód z jednostek (fakt — odnotowane wpłaty; prognoza — pozostałe kwoty wg
          terminu płatności) i koszt lekarzy (wyłącznie prognoza).
        </p>
      </header>

      {error && (
        <div className="card border-red-500/40 text-red-300">
          Nie udało się połączyć z API ({error}). Sprawdź, czy backend jest uruchomiony.
        </div>
      )}

      {!data ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="card space-y-3">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-8 w-32" />
            </div>
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Tile icon={<Wallet size={20} />} label="Saldo narastająco (do dziś)"
              value={zl(k!.balance_to_date)} tone={k!.balance_to_date >= 0 ? "good" : "bad"}
              sub="wpłaty od zawsze − szacowane rozliczone koszty lekarzy" />
            <Tile icon={<AlertTriangle size={20} />} label="Przeterminowane należności"
              value={zl(k!.overdue_amount)} tone={k!.overdue_amount > 0 ? "bad" : "default"} />
            <Tile icon={<TrendingUp size={20} />} label="Prognoza wpływów (90 dni)"
              value={zl(k!.forecast_inflow_90d)} tone="good" />
            <Tile icon={<TrendingUp size={20} />} label="Prognoza wyniku netto (90 dni)"
              value={zl(k!.forecast_net_90d)} tone={k!.forecast_net_90d >= 0 ? "good" : "bad"}
              sub={`w tym koszt lekarzy: ${zl(k!.forecast_outflow_90d)}`} />
          </div>

          <div className="card flex items-start gap-2 border-brand-accent/20 text-[13px] text-slate-400">
            <Info size={15} className="mt-0.5 shrink-0 text-brand-accent2" />
            Koszt lekarzy jest tu wyłącznie założeniem — moduł nie śledzi jeszcze rzeczywistych wypłat lekarzom.
            Przyjęto stały termin: koniec miesiąca rozliczeniowego + {data.doctor_cost_payment_term_days} dni
            kalendarzowych (do zmiany w Ustawieniach → Terminy płatności).
          </div>

          <div className="card">
            <h2 className="mb-1 text-base font-bold">Skumulowane saldo</h2>
            <p className="mb-4 text-[13px] text-slate-400">
              Trend w widocznym oknie (nie prawdziwe saldo konta — system nie ma integracji bankowej). Linia ciągła
              = fakt (odnotowane wpłaty), przerywana = prognoza.
            </p>
            <ResponsiveContainer width="100%" height={280}>
              <ReLineChart data={data.buckets} margin={{ left: 10, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" />
                <XAxis dataKey="label" stroke="#8aa0a3" fontSize={11} />
                <YAxis stroke="#8aa0a3" fontSize={12} tickFormatter={(v) => (v / 1000).toFixed(0) + "k"} />
                <ReferenceLine y={0} stroke="#ffffff22" />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => zl(v)} />
                <Line type="monotone" dataKey="balance_actual" name="Saldo (fakt)" stroke={REVENUE_COLOR}
                  strokeWidth={3} dot={false} connectNulls={false} />
                <Line type="monotone" dataKey="balance_forecast" name="Saldo (prognoza)" stroke={REVENUE_COLOR_SOFT}
                  strokeWidth={2.5} strokeDasharray="6 5" dot={false} connectNulls={false} />
              </ReLineChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h2 className="mb-1 text-base font-bold">Wpływy i koszty per tydzień</h2>
            <p className="mb-4 text-[13px] text-slate-400">
              Zielone słupki — wpływy z jednostek (fakt + prognoza wg terminu). Fioletowe — koszt lekarzy (prognoza).
            </p>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={barData} margin={{ left: 10, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" />
                <XAxis dataKey="label" stroke="#8aa0a3" fontSize={11} />
                <YAxis stroke="#8aa0a3" fontSize={12} tickFormatter={(v) => (v / 1000).toFixed(0) + "k"} />
                <ReferenceLine y={0} stroke="#ffffff33" />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => zl(Math.abs(v))} />
                <Legend />
                <Bar dataKey="wpływy" name="Wpływy" fill={REVENUE_COLOR} radius={[4, 4, 0, 0]} />
                <Bar dataKey="koszty" name="Koszt lekarzy" fill={COST_COLOR} radius={[0, 0, 4, 4]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
