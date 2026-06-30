import React, { useEffect, useState, useCallback } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from "recharts";
import client, { fmtUSD } from "../api";
import { Card, CardHeader, Button, Spinner, EmptyState, Stat } from "../components/ui";
import { useToast } from "../components/Toast";

export default function Reports() {
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

  useEffect(() => {
    load();
  }, [load]);

  const rows = data?.rows || [];
  const chartData = [...rows].reverse().map((r) => ({ period: r.period, pnl: r.realized_pnl }));

  return (
    <div className="space-y-6" data-testid="reports-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">P&L Reports</h1>
          <p className="text-sm text-zinc-500">Realized P&L rolled up by period — the long-term scorecard</p>
        </div>
        <div className="flex gap-1 border border-zinc-200 rounded-md overflow-hidden">
          {["month", "quarter"].map((p) => (
            <button
              key={p}
              data-testid={`period-${p}`}
              onClick={() => setPeriod(p)}
              className={`px-4 py-2 text-sm capitalize transition-colors ${
                period === p ? "bg-zinc-950 text-white font-medium" : "bg-white text-zinc-600 hover:bg-zinc-50"
              }`}
            >
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
            <div className="grid grid-cols-2 md:grid-cols-3 divide-x divide-zinc-200">
              <Stat
                label="Realized P&L (all-time)"
                value={fmtUSD(data?.realized_total ?? 0)}
                tone={(data?.realized_total ?? 0) >= 0 ? "profit" : "loss"}
                testid="report-realized-total"
              />
              <Stat
                label="Current Unrealized"
                value={fmtUSD(data?.current_unrealized ?? 0)}
                tone={(data?.current_unrealized ?? 0) >= 0 ? "profit" : "loss"}
                testid="report-unrealized"
              />
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
                    <CartesianGrid stroke="#f1f1f3" vertical={false} />
                    <XAxis dataKey="period" tick={{ fontSize: 11, fontFamily: "JetBrains Mono" }} stroke="#a1a1aa" />
                    <YAxis tick={{ fontSize: 11, fontFamily: "JetBrains Mono" }} stroke="#a1a1aa" tickFormatter={(v) => `$${v}`} />
                    <Tooltip
                      contentStyle={{ fontSize: 12, fontFamily: "JetBrains Mono", borderRadius: 6, border: "1px solid #e4e4e7" }}
                      formatter={(v) => fmtUSD(v)}
                    />
                    <Bar dataKey="pnl">
                      {chartData.map((d, i) => (
                        <Cell key={i} fill={d.pnl >= 0 ? "#16A34A" : "#DC2626"} />
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
                  <tr className="border-b border-zinc-200 text-[11px] uppercase tracking-wide text-zinc-500">
                    <th className="text-left px-5 py-2.5 font-semibold">Period</th>
                    <th className="text-right px-3 py-2.5 font-semibold">Realized P&L</th>
                    <th className="text-right px-5 py-2.5 font-semibold">Sell Trades</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {rows.map((r) => (
                    <tr key={r.period} className="border-b border-zinc-100 hover:bg-zinc-50" data-testid={`report-row-${r.period}`}>
                      <td className="px-5 py-2.5 font-semibold">{r.period}</td>
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
