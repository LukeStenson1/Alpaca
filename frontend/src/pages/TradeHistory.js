import React, { useEffect, useState, useCallback } from "react";
import { Filter, X } from "lucide-react";
import client, { fmtUSD, fmtNum, fmtDate } from "../api";
import { Card, CardHeader, Button, Input, Badge, Spinner, EmptyState } from "../components/ui";
import { useToast } from "../components/Toast";

export default function TradeHistory() {
  const toast = useToast();
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ticker, setTicker] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [detail, setDetail] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (ticker) params.ticker = ticker.toUpperCase();
      if (start) params.start = new Date(start).toISOString();
      if (end) params.end = new Date(end).toISOString();
      const res = await client.get("/trades", { params });
      setTrades(res.data);
    } catch (e) {
      toast("Failed to load trades", "error");
    } finally {
      setLoading(false);
    }
  }, [ticker, start, end, toast]);

  useEffect(() => {
    load();
  }, []); // eslint-disable-line

  const clearFilters = () => {
    setTicker("");
    setStart("");
    setEnd("");
    setTimeout(load, 0);
  };

  return (
    <div className="space-y-6" data-testid="trades-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Trade History</h1>
        <p className="text-sm text-zinc-500">Every trade with the condition that triggered it</p>
      </div>

      <Card>
        <CardHeader title="Filters" />
        <div className="flex flex-col md:flex-row gap-3 px-5 py-4">
          <Input
            placeholder="Ticker"
            value={ticker}
            data-testid="filter-ticker"
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            className="md:w-40 font-mono uppercase"
          />
          <div className="flex flex-col">
            <label className="text-[10px] uppercase text-zinc-400 mb-0.5">From</label>
            <Input type="date" value={start} data-testid="filter-start" onChange={(e) => setStart(e.target.value)} className="md:w-44" />
          </div>
          <div className="flex flex-col">
            <label className="text-[10px] uppercase text-zinc-400 mb-0.5">To</label>
            <Input type="date" value={end} data-testid="filter-end" onChange={(e) => setEnd(e.target.value)} className="md:w-44" />
          </div>
          <div className="flex items-end gap-2">
            <Button onClick={load} data-testid="apply-filters-btn">
              <Filter size={15} /> Apply
            </Button>
            <Button variant="outline" onClick={clearFilters} data-testid="clear-filters-btn">
              <X size={15} /> Clear
            </Button>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader title="Trades" subtitle={`${trades.length} records`} />
        {loading ? (
          <Spinner />
        ) : trades.length === 0 ? (
          <EmptyState title="No trades found" hint="Trades appear here once the strategy places orders." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="trades-table">
              <thead>
                <tr className="border-b border-zinc-200 text-[11px] uppercase tracking-wide text-zinc-500">
                  <th className="text-left px-5 py-2.5 font-semibold">Time</th>
                  <th className="text-left px-3 py-2.5 font-semibold">Ticker</th>
                  <th className="text-left px-3 py-2.5 font-semibold">Side</th>
                  <th className="text-right px-3 py-2.5 font-semibold">Qty</th>
                  <th className="text-right px-3 py-2.5 font-semibold">Price</th>
                  <th className="text-left px-3 py-2.5 font-semibold">Trigger</th>
                  <th className="text-right px-5 py-2.5 font-semibold">Params</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {trades.map((t) => (
                  <tr key={t.id} className="border-b border-zinc-100 hover:bg-zinc-50" data-testid={`trade-row-${t.id}`}>
                    <td className="px-5 py-2.5 text-zinc-500 whitespace-nowrap">{fmtDate(t.timestamp)}</td>
                    <td className="px-3 py-2.5 font-semibold">{t.ticker}</td>
                    <td className="px-3 py-2.5">
                      <Badge tone={t.side === "buy" ? "success" : "danger"}>{t.side}</Badge>
                    </td>
                    <td className="px-3 py-2.5 text-right tabular">{fmtNum(t.quantity)}</td>
                    <td className="px-3 py-2.5 text-right tabular">{fmtUSD(t.price)}</td>
                    <td className="px-3 py-2.5 text-zinc-600 font-sans text-xs max-w-md">{t.trigger_reason}</td>
                    <td className="px-5 py-2.5 text-right">
                      <button
                        className="text-klein text-xs hover:underline"
                        onClick={() => setDetail(t)}
                        data-testid={`view-params-${t.id}`}
                      >
                        view
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setDetail(null)}>
          <Card className="w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            <CardHeader
              title={`${detail.ticker} — ${detail.side.toUpperCase()} params snapshot`}
              right={
                <button onClick={() => setDetail(null)} data-testid="close-detail">
                  <X size={18} />
                </button>
              }
            />
            <div className="px-5 py-4 space-y-3">
              <div className="text-xs text-zinc-500">{fmtDate(detail.timestamp)} · order {detail.order_id || "—"}</div>
              <div className="text-sm">{detail.trigger_reason}</div>
              <pre className="bg-zinc-50 border border-zinc-200 rounded-md p-3 text-xs font-mono overflow-auto" data-testid="params-snapshot-json">
                {JSON.stringify(detail.params_snapshot, null, 2)}
              </pre>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
