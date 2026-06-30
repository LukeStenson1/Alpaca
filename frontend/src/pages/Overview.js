import React, { useEffect, useState, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { Play, RefreshCw, WifiOff } from "lucide-react";
import client, { fmtUSD, fmtPct, fmtNum, fmtDate } from "../api";
import { Card, CardHeader, Button, Stat, Spinner, EmptyState, Badge } from "../components/ui";
import { useToast } from "../components/Toast";
import { useSystem } from "../components/SystemContext";

export default function Overview() {
  const toast = useToast();
  const { refresh: refreshSystem } = useSystem();
  const [account, setAccount] = useState(null);
  const [positions, setPositions] = useState([]);
  const [snaps, setSnaps] = useState([]);
  const [pnl, setPnl] = useState(null);
  const [closed, setClosed] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    try {
      const [a, p, s, summary, c] = await Promise.all([
        client.get("/account"),
        client.get("/positions"),
        client.get("/account/snapshots", { params: { limit: 200 } }),
        client.get("/pnl/summary"),
        client.get("/positions/closed"),
      ]);
      setAccount(a.data);
      setPositions(p.data.positions || []);
      setSnaps(s.data || []);
      setPnl(summary.data);
      setClosed(c.data || []);
    } catch (e) {
      toast("Failed to load overview", "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

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

  const chartData = snaps.map((s) => ({
    t: new Date(s.timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
    equity: s.equity,
  }));

  return (
    <div className="space-y-6" data-testid="overview-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Overview</h1>
          <p className="text-sm text-zinc-500">
            Account equity, P&amp;L and open positions
            {account?.market_open !== null && account?.market_open !== undefined && (
              <Badge tone={account.market_open ? "success" : "muted"} className="ml-2">
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
            <div className="grid grid-cols-2 md:grid-cols-5 divide-x divide-zinc-200">
              <Stat label="Equity" value={fmtUSD(account.equity)} testid="stat-equity" />
              <Stat
                label="Today's P&L"
                value={fmtUSD(account.today_pl)}
                sub={fmtPct(account.today_pl_pct)}
                tone={plTone}
                testid="stat-today-pl"
              />
              <Stat
                label="Realized P&L"
                value={fmtUSD(pnl?.realized_total ?? 0)}
                sub={`${pnl?.closed_count ?? 0} closed`}
                tone={(pnl?.realized_total ?? 0) > 0 ? "profit" : (pnl?.realized_total ?? 0) < 0 ? "loss" : "default"}
                testid="stat-realized-pl"
              />
              <Stat label="Cash" value={fmtUSD(account.cash)} testid="stat-cash" />
              <Stat label="Buying Power" value={fmtUSD(account.buying_power)} testid="stat-buying-power" />
            </div>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card className="lg:col-span-2">
              <CardHeader title="Equity Curve" subtitle="Recorded on each strategy run" />
              <div className="p-4 h-64">
                {chartData.length < 2 ? (
                  <EmptyState title="No equity history yet" hint="Run the strategy to start recording snapshots." />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke="#f1f1f3" vertical={false} />
                      <XAxis dataKey="t" tick={{ fontSize: 11, fontFamily: "JetBrains Mono" }} stroke="#a1a1aa" />
                      <YAxis
                        tick={{ fontSize: 11, fontFamily: "JetBrains Mono" }}
                        stroke="#a1a1aa"
                        domain={["auto", "auto"]}
                        tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                      />
                      <Tooltip
                        contentStyle={{ fontSize: 12, fontFamily: "JetBrains Mono", borderRadius: 6, border: "1px solid #e4e4e7" }}
                        formatter={(v) => fmtUSD(v)}
                      />
                      <Line type="monotone" dataKey="equity" stroke="#002FA7" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </Card>

            <Card>
              <CardHeader title="Open Positions" subtitle={`${positions.length} active`} />
              <div className="divide-y divide-zinc-100 max-h-64 overflow-auto">
                {positions.length === 0 ? (
                  <EmptyState title="No open positions" hint="The strategy will open positions when tickers dip below their buy trigger." />
                ) : (
                  positions.map((p) => (
                    <div key={p.ticker} className="flex items-center justify-between px-5 py-3" data-testid={`position-${p.ticker}`}>
                      <div>
                        <div className="font-mono font-semibold text-sm">{p.ticker}</div>
                        <div className="font-mono text-xs text-zinc-500 tabular">
                          {fmtNum(p.qty)} @ {fmtUSD(p.avg_entry_price)}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-mono text-sm tabular">{fmtUSD(p.market_value)}</div>
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

          <Card data-testid="closed-positions-card">
            <CardHeader title="Closed Positions — Realized P&L" subtitle={`${closed.length} fully closed`} />
            {closed.length === 0 ? (
              <EmptyState
                title="No closed positions yet"
                hint="A position closes once all its sell tranches have fired; realized P&L is recorded here."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="closed-positions-table">
                  <thead>
                    <tr className="border-b border-zinc-200 text-[11px] uppercase tracking-wide text-zinc-500">
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
                      <tr key={c.ticker + c.closed_at} className="border-b border-zinc-100 hover:bg-zinc-50" data-testid={`closed-row-${c.ticker}`}>
                        <td className="px-5 py-2.5 font-semibold">{c.ticker}</td>
                        <td className="px-3 py-2.5 text-right tabular">{fmtNum(c.original_qty)}</td>
                        <td className="px-3 py-2.5 text-right tabular">{fmtUSD(c.avg_entry_price)}</td>
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
