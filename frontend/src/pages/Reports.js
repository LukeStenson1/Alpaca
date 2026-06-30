import React, { useEffect, useState, useCallback } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from "recharts";
import client, { fmtUSD } from "../api";
import { Card, CardHeader, Spinner, EmptyState, Stat } from "../components/ui";
import { useToast } from "../components/Toast";

const tooltipStyle = {
  fontSize: 12, fontFamily: "IBM Plex Mono", borderRadius: 8,
  border: "1px solid #27272a", background: "#18181b", color: "#fafafa",
};

export default function Reports({ embedded = false }) {
  const toast = useToast();
  const [period, setPeriod] = useState("month");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await client.get("/reports/pnl", { params: { period } });
      setData(res.data);
    } catch (e) {
      toast("Failed to load report", "error");
    } finally {
      setLoading(false);
    }
  }, [period, toast]);

  useEffect(() => { load(); }, [load]);

  const rows = data?.rows || [];
  const chartData = [...rows].reverse().map((r) => ({ period: r.period, pnl: r.realized_pnl }));

  return (
    <div className="space-y-6" data-testid="reports-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          {!embedded && <h1 className="text-2xl font-bold tracking-tight text-zinc-50">P&L Reports</h1>}
          <p className="text-sm text-zinc-500">Realized P&amp;L rolled up by period — the long-term scorecard</p>
        </div>
        <div className="flex border border-zinc-800 rounded-lg overflow-hidden">
          {["month", "quarter"].map((p) => (
            <button key={p} data-testid={`period-${p}`} onClick={() => setPeriod(p)}
              className={`px-4 py-2 text-sm capitalize transition-colors ${
                period === p ? "bg-klein text-white font-medium" : "bg-transparent text-zinc-400 hover:bg-zinc-800"
              }`}>
              {p}ly
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <Spinner />
      ) : (
        <>
          <Card>
            <div className="grid grid-cols-2 md:grid-cols-3 divide-x divide-zinc-800">
              <Stat label="Realized P&L (all-time)" value={fmtUSD(data?.realized_total ?? 0)}
                tone={(data?.realized_total ?? 0) >= 0 ? "profit" : "loss"} testid="report-realized-total" />
              <Stat label="Current Unrealized" value={fmtUSD(data?.current_unrealized ?? 0)}
                tone={(data?.current_unrealized ?? 0) >= 0 ? "profit" : "loss"} testid="report-unrealized" />
              <Stat label={`${period === "quarter" ? "Quarters" : "Months"} recorded`} value={rows.length} />
            </div>
          </Card>

          <Card>
            <CardHeader title={`Realized P&L by ${period}`} />
            <div className="p-4 h-64">
              {chartData.length === 0 ? (
                <EmptyState title="No realized P&L yet" hint="Closed sell tranches will roll up here by period." />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="#27272a" vertical={false} />
                    <XAxis dataKey="period" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#71717a" }} stroke="#3f3f46" />
                    <YAxis tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#71717a" }} stroke="#3f3f46" tickFormatter={(v) => `$${v}`} />
                    <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#27272a55" }} formatter={(v) => fmtUSD(v)} />
                    <Bar dataKey="pnl">
                      {chartData.map((d, i) => (
                        <Cell key={i} fill={d.pnl >= 0 ? "#34d399" : "#fb7185"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Breakdown" />
            {rows.length === 0 ? (
              <EmptyState title="No periods yet" />
            ) : (
              <table className="w-full text-sm" data-testid="report-table">
                <thead>
                  <tr className="border-b border-zinc-800 text-[11px] uppercase tracking-wide text-zinc-500">
                    <th className="text-left px-5 py-2.5 font-semibold">Period</th>
                    <th className="text-right px-3 py-2.5 font-semibold">Realized P&L</th>
                    <th className="text-right px-5 py-2.5 font-semibold">Sell Trades</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {rows.map((r) => (
                    <tr key={r.period} className="border-b border-zinc-800/60 hover:bg-zinc-800/40" data-testid={`report-row-${r.period}`}>
                      <td className="px-5 py-2.5 font-semibold text-zinc-100">{r.period}</td>
                      <td className={`px-3 py-2.5 text-right tabular ${r.realized_pnl >= 0 ? "text-profit" : "text-loss"}`}>
                        {fmtUSD(r.realized_pnl)}
                      </td>
                      <td className="px-5 py-2.5 text-right tabular text-zinc-500">{r.trade_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
