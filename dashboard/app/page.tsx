"use client";

import { useEffect, useMemo, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Search, RefreshCw, ExternalLink, TrendingUp } from "lucide-react";
import type { Brand } from "@/lib/types";

type Summary = {
  total_brands: number;
  brands_per_niche: Record<string, number>;
  niche_stats: { _id: string; count: number; avgScore: number }[];
  latest_run: {
    generated_at?: string;
    brands_found?: number;
    youtube_units_used?: number;
    web_calls_used?: number;
    duplicate_rate?: number;
    re_reported?: number;
    brands_per_niche?: Record<string, number>;
  } | null;
  generated_at: string | null;
};

const NICHE_COLORS = ["#38bdf8", "#a78bfa", "#34d399", "#fbbf24", "#f472b6"];

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [brands, setBrands] = useState<Brand[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [niche, setNiche] = useState("all");
  const [sort, setSort] = useState("score");
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  async function load() {
    setLoading(true);
    try {
      const [s, b] = await Promise.all([
        fetch("/api/summary", { cache: "no-store" }).then((r) => r.json()),
        fetch(`/api/brands?niche=${niche}&q=${encodeURIComponent(q)}&sort=${sort}&limit=500`, { cache: "no-store" }).then((r) => r.json()),
      ]);
      setSummary(s);
      setBrands(b.brands || []);
      setLastRefresh(new Date());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [niche, sort]);

  // debounce search
  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const chartData = useMemo(() => {
    if (!summary) return [];
    return Object.entries(summary.brands_per_niche || {})
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [summary]);

  const niches = useMemo(() => {
    const set = new Set<string>();
    (summary?.niche_stats || []).forEach((n) => n._id && set.add(n._id));
    return ["all", ...Array.from(set)];
  }, [summary]);

  const run = summary?.latest_run;

  return (
    <main className="max-w-7xl mx-auto px-6 py-8">
      <header className="flex items-center justify-between mb-8 flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Brand Discovery</h1>
          <p className="text-muted text-sm mt-1">Live tracking of discovered brands · auto-refreshes every 60s</p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-card border border-slate-700 hover:border-accent transition text-sm"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </header>

      <div className="text-xs text-muted mb-6">
        Last updated: {run?.generated_at || summary?.generated_at || "unknown"} · {summary?.total_brands ?? 0} brands · refreshed {lastRefresh.toLocaleTimeString()}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        <Kpi label="Total brands" value={summary?.total_brands ?? 0} accent />
        <Kpi label="Duplicate rate" value={`${Math.round((run?.duplicate_rate || 0) * 100)}%`} />
        <Kpi label="Re-reported" value={run?.re_reported ?? 0} />
        <Kpi label="YT units used" value={run?.youtube_units_used ?? 0} />
        <Kpi label="Web calls used" value={run?.web_calls_used ?? 0} />
      </div>

      {/* Charts */}
      <div className="grid md:grid-cols-2 gap-6 mb-8">
        <div className="card">
          <h3 className="text-xs uppercase tracking-wider text-muted mb-4">Brands per niche</h3>
          {chartData.length === 0 ? (
            <div className="text-muted text-center py-12">No data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={chartData} layout="vertical" margin={{ left: 10, right: 20 }}>
                <XAxis type="number" stroke="#94a3b8" fontSize={11} />
                <YAxis type="category" dataKey="name" stroke="#94a3b8" fontSize={11} width={130} />
                <Tooltip
                  contentStyle={{ background: "#111a2e", border: "1px solid #1e293b", borderRadius: 8 }}
                  cursor={{ fill: "#1e293b" }}
                />
                <Bar dataKey="value" radius={[0, 6, 6, 0]}>
                  {chartData.map((_, i) => (
                    <Cell key={i} fill={NICHE_COLORS[i % NICHE_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="card">
          <h3 className="text-xs uppercase tracking-wider text-muted mb-4">Quota used (latest run)</h3>
          <div className="space-y-4">
            <QuotaRow label="YouTube units" value={run?.youtube_units_used ?? 0} max={10000} color="#38bdf8" />
            <QuotaRow label="Web calls" value={run?.web_calls_used ?? 0} max={100} color="#a78bfa" />
          </div>
          <div className="mt-6 text-xs text-muted">
            Brands found this run: <span className="text-white font-semibold">{run?.brands_found ?? 0}</span>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search brands, domains, niches…"
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-card border border-slate-700 focus:border-accent outline-none text-sm"
          />
        </div>
        <select
          value={niche}
          onChange={(e) => setNiche(e.target.value)}
          className="px-3 py-2 rounded-lg bg-card border border-slate-700 text-sm"
        >
          {niches.map((n) => (
            <option key={n} value={n}>{n === "all" ? "All niches" : n}</option>
          ))}
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="px-3 py-2 rounded-lg bg-card border border-slate-700 text-sm"
        >
          <option value="score">Sort: score</option>
          <option value="name">Sort: name</option>
          <option value="recent">Sort: recent</option>
        </select>
      </div>

      {/* Brands table */}
      <div className="card overflow-hidden">
        <div className="overflow-auto max-h-[640px]">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-[#0f172a]">
              <tr className="text-left text-muted text-xs uppercase tracking-wider">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Website</th>
                <th className="px-4 py-3">Niche</th>
                <th className="px-4 py-3">Sub-niche</th>
                <th className="px-4 py-3">Score</th>
                <th className="px-4 py-3">Evidence</th>
                <th className="px-4 py-3">Creators</th>
                <th className="px-4 py-3">Older</th>
              </tr>
            </thead>
            <tbody>
              {brands.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center text-muted py-12">No brands yet</td>
                </tr>
              )}
              {brands.map((b) => (
                <tr key={b.domain} className="border-t border-slate-800 hover:bg-slate-800/40">
                  <td className="px-4 py-3 font-medium">{b.name}</td>
                  <td className="px-4 py-3">
                    {b.website ? (
                      <a href={b.website} target="_blank" rel="noopener" className="text-accent hover:underline inline-flex items-center gap-1">
                        {b.domain} <ExternalLink className="w-3 h-3" />
                      </a>
                    ) : (
                      b.domain
                    )}
                  </td>
                  <td className="px-4 py-3">{b.niche || "—"}</td>
                  <td className="px-4 py-3 text-muted">{b.sub_niche || "—"}</td>
                  <td className="px-4 py-3 font-semibold">{b.score ?? 0}</td>
                  <td className="px-4 py-3">
                    {(b.evidence || []).slice(0, 4).map((e, i) => (
                      <span key={i} className={`badge ${e.strength || "weak"} mr-1`}>{e.strength}</span>
                    ))}
                    {(b.evidence?.length || 0) > 4 && <span className="text-muted text-xs">+{b.evidence!.length - 4}</span>}
                  </td>
                  <td className="px-4 py-3">{b.creators_90d ?? 0}</td>
                  <td className="px-4 py-3">{b.older_evidence ? "yes" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <footer className="mt-10 text-center text-xs text-muted">
        Brand Discovery Agent · MongoDB-backed · Vercel
      </footer>
    </main>
  );
}

function Kpi({ label, value, accent }: { label: string; value: string | number; accent?: boolean }) {
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wider text-muted mb-2">{label}</div>
      <div className={`text-2xl font-bold ${accent ? "text-accent" : ""}`}>{value}</div>
    </div>
  );
}

function QuotaRow({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span>{label}</span>
        <span className="font-semibold">{value} <span className="text-muted">/ {max}</span></span>
      </div>
      <div className="bar">
        <div style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}