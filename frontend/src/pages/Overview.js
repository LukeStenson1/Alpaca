import React, { useEffect, useState, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import { Play, RefreshCw, WifiOff, AlertTriangle, PieChart, Trophy, Star, TrendingUp } from "lucide-react";
import client, { fmtUSD, fmtPct, fmtNum, fmtDate } from "../api";
import { Card, CardHeader, Button, Stat, Spinner, EmptyState, Badge } from "../components/ui";
import { useToast } from "../components/Toast";
import { useSystem } from "../components/SystemContext";

const tooltipStyle = {
  fontSize: 12, fontFamily: "IBM Plex Mono", borderRadius: 8,
  border: "1px solid #27272a", background: "#18181b", color: "#fafafa",
};

export default function Overview() {
  const toast = useToast();
  const { refresh: refreshSystem } = useSystem();
  const [account, setAccount] = useState(null);
  const [positions, setPositions] = useState([]);
  const [snaps, setSnaps] = useState([]);
  const [pnl, setPnl] = useState(null);
  const [closed, setClosed] = useState([]);
  const [flags, setFlags] = useState([]);
  const [sectors, setSectors] = useState([]);
  const [bench, setBench] = useState(null);
  const [shortlist, setShortlist] = useState(null);
  const [refreshingF, setRefreshingF] = useState(false);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    const calls = [
      ["account", "/account"],
      ["positions", "/positions"],
      ["snaps", "/account/snapshots", { limit: 200 }],
      ["pnl", "/pnl/summary"],
      ["closed", "/positions/closed"],
      ["flags", "/portfolio/flags"],
      ["sectors", "/portfolio/sectors"],
      ["bench", "/portfolio/benchmark"],
      ["shortlist", "/shortlist"],
    ];
    const results = await Promise.allSettled(
      calls.map(([, url, params]) => client.get(url, params ? { params } : undefined))
    );
    const get = (i) => (results[i].status === "fulfilled" ? results[i].value.data : null);
    if (get(0)) setAccount(get(0));
    if (get(1)) setPositions(get(1).positions || []);
    if (get(2)) setSnaps(get(2) || []);
    if (get(3)) setPnl(get(3));
    if (get(4)) setClosed(get(4) || []);
    if (get(5)) setFlags(get(5).flags || []);
    if (get(6)) setSectors(get(6).sectors || []);
    if (get(7)) setBench(get(7) || null);
    if (get(8)) setShortlist(get(8));
    setLoading(false);
  }, []);

  const refreshFundamentals = async () => {
    setRefreshingF(true);
    try {
      const res = await client.post("/fundamentals/refresh");
      setShortlist({ configured: true, items: res.data.shortlist });
      toast(`Fundamentals refreshed for ${res.data.refreshed} stocks`, "success");
    } catch (e) {
      toast(e.response?.data?.detail || "Failed to refresh fundamentals", "error");
    } finally {
      setRefreshingF(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, [load]);

  const runStrategy = async () => {
    setRunning(true);
    try {
      const res = await client.post("/strategy/run");
      const d = res.data;
      if (d.halted) {
        toast("Strategy skipped — kill switch engaged", "warning");
      } else {
        toast(`Strategy ran: ${d.buys.length} buys, ${d.sells.length} sells`, "success");
      }
      await load();
      await refreshSystem();
    } catch (e) {
      toast("Strategy run failed", "error");
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <Spinner />;

  const connected = account?.connected;
  const plTone = account?.today_pl > 0 ? "profit" : account?.today_pl < 0 ? "loss" : "default";

  return (
    <div className="space-y-6" data-testid="overview-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-50">Dashboard</h1>
          <p className="text-sm text-zinc-500 flex items-center gap-2">
            Account equity, P&amp;L and open positions
            {account?.market_open !== null && account?.market_open !== undefined && (
              <Badge tone={account.market_open ? "success" : "muted"}>
                market {account.market_open ? "open" : "closed"}
              </Badge>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} data-testid="refresh-btn">
            <RefreshCw size={15} /> Refresh
          </Button>
          <Button onClick={runStrategy} disabled={running} data-testid="run-strategy-btn">
            <Play size={15} /> {running ? "Running…" : "Run Strategy Now"}
          </Button>
        </div>
      </div>

      {!connected && (
        <Card className="border-loss/40">
          <div className="flex items-center gap-3 px-5 py-4 text-sm text-loss">
            <WifiOff size={18} />
            <div>
              <div className="font-semibold">Not connected to Alpaca</div>
              <div className="text-zinc-500 text-xs mt-0.5">{account?.error || "Check API keys in Settings."}</div>
            </div>
          </div>
        </Card>
      )}

      {connected && (
        <>
          <Card>
            <div className="grid grid-cols-2 md:grid-cols-5 divide-x divide-y md:divide-y-0 divide-zinc-800">
              <Stat label="Equity" value={fmtUSD(account.equity)} testid="stat-equity" />
              <Stat label="Today's P&L" value={fmtUSD(account.today_pl)} sub={fmtPct(account.today_pl_pct)} tone={plTone} testid="stat-today-pl" />
              <Stat label="Realized P&L" value={fmtUSD(pnl?.realized_total ?? 0)} sub={`${pnl?.closed_count ?? 0} closed`}
                tone={(pnl?.realized_total ?? 0) > 0 ? "profit" : (pnl?.realized_total ?? 0) < 0 ? "loss" : "default"} testid="stat-realized-pl" />
              <Stat label="Cash" value={fmtUSD(account.cash)} testid="stat-cash" />
              <Stat label="Buying Power" value={fmtUSD(account.buying_power)} testid="stat-buying-power" />
            </div>
          </Card>

          {flags.length > 0 && (
            <Card data-testid="review-flags-card" className="border-warn/40">
              <CardHeader title="Review Flags" subtitle="Informational — no automatic action taken" />
              <div className="divide-y divide-zinc-800">
                {flags.map((f, i) => (
                  <div key={i} className="flex items-center gap-3 px-5 py-3 text-sm" data-testid={`flag-${f.type}-${f.ticker}`}>
                    <AlertTriangle size={16} className="text-warn shrink-0" />
                    <Badge tone="warn">{f.type}</Badge>
                    <span className="text-zinc-300">{f.message}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <ShortlistCard data={shortlist} onRefresh={refreshFundamentals} refreshing={refreshingF} />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card className="lg:col-span-2" data-testid="benchmark-card">
              <CardHeader title="Portfolio vs Benchmark" subtitle={`Indexed to 100 · benchmark ${bench?.benchmark_ticker || "SPY"}`} />
              <div className="p-4 h-64">
                {!bench || (bench.series || []).length < 2 ? (
                  <EmptyState title="Not enough history yet" hint="Run the strategy across sessions to build the comparison." />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={bench.series} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke="#27272a" vertical={false} />
                      <XAxis dataKey="timestamp" tick={false} stroke="#3f3f46" />
                      <YAxis tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#71717a" }} stroke="#3f3f46" domain={["auto", "auto"]} />
                      <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: "#a1a1aa" }} labelFormatter={(v) => new Date(v).toLocaleString()} />
                      <Legend wrapperStyle={{ fontSize: 12, color: "#a1a1aa" }} />
                      <Line type="monotone" dataKey="portfolio" name="Portfolio" stroke="#3b82f6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="benchmark" name={bench.benchmark_ticker} stroke="#a1a1aa" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </Card>

            <Card>
              <CardHeader title="Open Positions" subtitle={`${positions.length} active`} />
              <div className="divide-y divide-zinc-800 max-h-64 overflow-auto">
                {positions.length === 0 ? (
                  <EmptyState title="No open positions" hint="The strategy opens positions when tickers dip below their buy trigger." />
                ) : (
                  positions.map((p) => (
                    <div key={p.ticker} className="flex items-center justify-between px-5 py-3" data-testid={`position-${p.ticker}`}>
                      <div>
                        <div className="font-mono font-semibold text-sm text-zinc-100">{p.ticker}</div>
                        <div className="font-mono text-xs text-zinc-500 tabular">{fmtNum(p.qty)} @ {fmtUSD(p.avg_entry_price)}</div>
                      </div>
                      <div className="text-right">
                        <div className="font-mono text-sm tabular text-zinc-100">{fmtUSD(p.market_value)}</div>
                        <div className={`font-mono text-xs tabular ${p.unrealized_pl >= 0 ? "text-profit" : "text-loss"}`}>
                          {fmtUSD(p.unrealized_pl)} ({fmtPct(p.unrealized_plpc * 100)})
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </Card>
          </div>

          {sectors.length > 0 && (
            <Card data-testid="sector-breakdown-card">
              <CardHeader title="Sector Exposure" subtitle="Current open positions by sector (manual tags)" />
              <div className="divide-y divide-zinc-800">
                {sectors.map((s) => (
                  <div key={s.sector} className="px-5 py-3" data-testid={`sector-${s.sector}`}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="flex items-center gap-2 text-zinc-300">
                        <PieChart size={14} className="text-klein" /> {s.sector}
                      </span>
                      <span className="font-mono tabular text-zinc-400">{fmtUSD(s.value)} · {s.pct}%</span>
                    </div>
                    <div className="mt-1.5 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div className="h-full bg-klein" style={{ width: `${Math.min(s.pct, 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card data-testid="closed-positions-card">
            <CardHeader title="Closed Positions — Realized P&L" subtitle={`${closed.length} fully closed`} />
            {closed.length === 0 ? (
              <EmptyState title="No closed positions yet" hint="A position closes once all its sell tranches have fired; realized P&L is recorded here." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="closed-positions-table">
                  <thead>
                    <tr className="border-b border-zinc-800 text-[11px] uppercase tracking-wide text-zinc-500">
                      <th className="text-left px-5 py-2.5 font-semibold">Ticker</th>
                      <th className="text-right px-3 py-2.5 font-semibold">Qty</th>
                      <th className="text-right px-3 py-2.5 font-semibold">Avg Entry</th>
                      <th className="text-right px-3 py-2.5 font-semibold">Realized P&L</th>
                      <th className="text-left px-3 py-2.5 font-semibold">Opened</th>
                      <th className="text-left px-5 py-2.5 font-semibold">Closed</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {closed.map((c) => (
                      <tr key={c.ticker + c.closed_at} className="border-b border-zinc-800/60 hover:bg-zinc-800/40" data-testid={`closed-row-${c.ticker}`}>
                        <td className="px-5 py-2.5 font-semibold text-zinc-100">{c.ticker}</td>
                        <td className="px-3 py-2.5 text-right tabular text-zinc-300">{fmtNum(c.original_qty)}</td>
                        <td className="px-3 py-2.5 text-right tabular text-zinc-300">{fmtUSD(c.avg_entry_price)}</td>
                        <td className={`px-3 py-2.5 text-right tabular font-semibold ${c.realized_pnl >= 0 ? "text-profit" : "text-loss"}`}>
                          {fmtUSD(c.realized_pnl)}
                        </td>
                        <td className="px-3 py-2.5 text-zinc-500">{fmtDate(c.opened_at)}</td>
                        <td className="px-5 py-2.5 text-zinc-500">{fmtDate(c.closed_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}


function ScoreBar({ value }) {
  const tone = value >= 70 ? "bg-profit" : value >= 45 ? "bg-klein" : "bg-zinc-600";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full ${tone}`} style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
      <span className="font-mono text-xs tabular text-zinc-300 w-6">{value}</span>
    </div>
  );
}

function ShortlistCard({ data, onRefresh, refreshing }) {
  const items = data?.items || [];
  const pctOrDash = (v) => (v == null ? "—" : `${(v * 100).toFixed(0)}%`);
  const num = (v) => (v == null ? "—" : v.toFixed(1));
  return (
    <Card data-testid="shortlist-card">
      <CardHeader
        title={<span className="flex items-center gap-2"><Trophy size={15} className="text-warn" /> Conviction × Valuation Shortlist</span>}
        subtitle="Your active watchlist ranked by conviction blended with fundamentals"
        right={
          <Button variant="outline" onClick={onRefresh} disabled={refreshing || !data?.configured} data-testid="refresh-fundamentals-btn">
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} /> {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
        }
      />
      {data && !data.configured ? (
        <div className="px-5 py-4 text-sm text-zinc-400">Add an <span className="font-mono text-zinc-200">FMP_API_KEY</span> to enable fundamentals scoring.</div>
      ) : items.length === 0 ? (
        <EmptyState title="No stocks to rank" hint="Add stocks to your watchlist, then Refresh to pull fundamentals." icon={Trophy} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="shortlist-table">
            <thead>
              <tr className="border-b border-zinc-800 text-[11px] uppercase tracking-wide text-zinc-500">
                <th className="text-left px-5 py-2.5 font-semibold">#</th>
                <th className="text-left px-3 py-2.5 font-semibold">Ticker</th>
                <th className="text-left px-3 py-2.5 font-semibold">Conviction</th>
                <th className="text-right px-3 py-2.5 font-semibold">P/E</th>
                <th className="text-right px-3 py-2.5 font-semibold">Rev Growth</th>
                <th className="text-right px-3 py-2.5 font-semibold">Margin</th>
                <th className="text-left px-3 py-2.5 font-semibold">Quality</th>
                <th className="text-left px-5 py-2.5 font-semibold">Blended</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {items.map((s, i) => (
                <tr key={s.ticker} className="border-b border-zinc-800/60 hover:bg-zinc-800/40" data-testid={`shortlist-row-${s.ticker}`}>
                  <td className="px-5 py-2.5 text-zinc-500">{i + 1}</td>
                  <td className="px-3 py-2.5 font-semibold text-zinc-100">
                    {s.ticker}
                    {s.is_etf && <span className="ml-1.5 text-[10px] text-zinc-600 font-sans">ETF</span>}
                    {!s.has_fundamentals && !s.is_etf && <span className="ml-1.5 text-[10px] text-zinc-600 font-sans">no data</span>}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className="flex items-center gap-0.5">
                      {[1, 2, 3, 4, 5].map((n) => (
                        <Star key={n} size={11} className={n <= s.conviction ? "fill-klein text-klein" : "text-zinc-700"} />
                      ))}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular text-zinc-300">{num(s.pe_ratio)}</td>
                  <td className={`px-3 py-2.5 text-right tabular ${s.revenue_growth > 0 ? "text-profit" : s.revenue_growth < 0 ? "text-loss" : "text-zinc-300"}`}>{pctOrDash(s.revenue_growth)}</td>
                  <td className="px-3 py-2.5 text-right tabular text-zinc-300">{pctOrDash(s.profit_margin)}</td>
                  <td className="px-3 py-2.5">{s.quality_score == null ? <span className="text-zinc-600">—</span> : <ScoreBar value={s.quality_score} />}</td>
                  <td className="px-5 py-2.5"><ScoreBar value={s.blended_score} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
