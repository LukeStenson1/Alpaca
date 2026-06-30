import React, { useEffect, useState, useCallback } from "react";
import { Plus, Trash2, ChevronDown, ChevronUp, Save, X } from "lucide-react";
import client, { fmtUSD, fmtDate } from "../api";
import { Card, CardHeader, Button, Input, Badge, Toggle, Spinner, EmptyState } from "../components/ui";
import { useToast } from "../components/Toast";

function ParamEditor({ ticker, params, sector, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState({
    buy_threshold_stddev: params.buy_threshold_stddev,
    lookback_days: params.lookback_days,
    sell_tranche_pct: params.sell_tranche_pct,
    sell_gain_steps: (params.sell_gain_steps || []).join(", "),
    max_position_size_usd: params.max_position_size_usd,
    stop_loss_pct: params.stop_loss_pct ?? 0,
    max_hold_days: params.max_hold_days ?? "",
    cooldown_days: params.cooldown_days ?? 7,
    range_pct: params.range_pct ?? 0.15,
    use_volatility_sizing: !!params.use_volatility_sizing,
    use_52w_range: !!params.use_52w_range,
    allow_downtrend_buys: !!params.allow_downtrend_buys,
    sector: sector || "",
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      const steps = form.sell_gain_steps.split(",").map((s) => parseFloat(s.trim())).filter((n) => !isNaN(n));
      await client.put(`/parameters/${ticker}`, {
        buy_threshold_stddev: parseFloat(form.buy_threshold_stddev),
        lookback_days: parseInt(form.lookback_days, 10),
        sell_tranche_pct: parseFloat(form.sell_tranche_pct),
        sell_gain_steps: steps,
        max_position_size_usd: parseFloat(form.max_position_size_usd),
        stop_loss_pct: parseFloat(form.stop_loss_pct),
        max_hold_days: form.max_hold_days === "" ? null : parseInt(form.max_hold_days, 10),
        cooldown_days: parseInt(form.cooldown_days, 10),
        range_pct: parseFloat(form.range_pct),
        use_volatility_sizing: form.use_volatility_sizing,
        use_52w_range: form.use_52w_range,
        allow_downtrend_buys: form.allow_downtrend_buys,
      });
      await client.put(`/watchlist/${ticker}`, { sector: form.sector });
      toast(`${ticker} parameters saved`, "success");
      onSaved();
    } catch (e) {
      toast("Failed to save parameters", "error");
    } finally {
      setSaving(false);
    }
  };

  const fields = [
    { k: "buy_threshold_stddev", label: "Buy threshold (std devs below mean)", step: "0.1" },
    { k: "lookback_days", label: "Lookback days (100–200 typical)", step: "1" },
    { k: "sell_tranche_pct", label: "Sell tranche % (0–1)", step: "0.05" },
    { k: "max_position_size_usd", label: "Max position size (USD)", step: "100" },
    { k: "stop_loss_pct", label: "Stop-loss % below entry (0 = off)", step: "0.01" },
    { k: "cooldown_days", label: "Re-entry cooldown (days)", step: "1" },
    { k: "max_hold_days", label: "Max hold days (blank = no flag)", step: "1" },
    { k: "range_pct", label: "52w-range gate: bottom X (0–1)", step: "0.05" },
  ];

  const toggles = [
    { k: "use_52w_range", label: "Use 52-week range gate" },
    { k: "use_volatility_sizing", label: "Volatility-adjusted sizing" },
    { k: "allow_downtrend_buys", label: "Allow buys in downtrend (below 200d MA)", danger: true },
  ];

  return (
    <div className="bg-zinc-50 border-t border-zinc-200 px-5 py-4" data-testid={`param-editor-${ticker}`}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {fields.map((f) => (
          <div key={f.k}>
            <label className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{f.label}</label>
            <Input
              type="number"
              step={f.step}
              value={form[f.k]}
              data-testid={`param-${f.k}-${ticker}`}
              onChange={(e) => set(f.k, e.target.value)}
              className="mt-1 font-mono"
            />
          </div>
        ))}
        <div className="md:col-span-2">
          <label className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
            Sell gain steps (comma-separated, e.g. 0.05, 0.10, 0.20)
          </label>
          <Input
            value={form.sell_gain_steps}
            data-testid={`param-sell_gain_steps-${ticker}`}
            onChange={(e) => set("sell_gain_steps", e.target.value)}
            className="mt-1 font-mono"
          />
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Sector (manual tag)</label>
          <Input
            value={form.sector}
            data-testid={`param-sector-${ticker}`}
            onChange={(e) => set("sector", e.target.value)}
            placeholder="e.g. Technology"
            className="mt-1"
          />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
        {toggles.map((t) => (
          <div key={t.k} className="flex items-center justify-between border border-zinc-200 bg-white rounded-md px-3 py-2">
            <span className="text-xs text-zinc-600 pr-2">{t.label}</span>
            <Toggle
              checked={form[t.k]}
              danger={t.danger}
              onChange={(v) => set(t.k, v)}
              testid={`param-${t.k}-${ticker}`}
            />
          </div>
        ))}
      </div>

      <div className="mt-4 flex justify-end">
        <Button onClick={save} disabled={saving} data-testid={`save-params-${ticker}`}>
          <Save size={15} /> {saving ? "Saving…" : "Save Parameters"}
        </Button>
      </div>
    </div>
  );
}

export default function Watchlist() {
  const toast = useToast();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ticker, setTicker] = useState("");
  const [notes, setNotes] = useState("");
  const [expanded, setExpanded] = useState(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await client.get("/watchlist");
      setItems(res.data);
    } catch (e) {
      toast("Failed to load watchlist", "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  const add = async (e) => {
    e.preventDefault();
    if (!ticker.trim()) return;
    setAdding(true);
    try {
      await client.post("/watchlist", { ticker: ticker.trim().toUpperCase(), notes: notes || null });
      toast(`${ticker.toUpperCase()} added`, "success");
      setTicker("");
      setNotes("");
      load();
    } catch (e) {
      toast(e.response?.data?.detail || "Failed to add ticker", "error");
    } finally {
      setAdding(false);
    }
  };

  const remove = async (tk) => {
    if (!window.confirm(`Remove ${tk} from the watchlist? Its trade history is kept.`)) return;
    try {
      await client.delete(`/watchlist/${tk}`);
      toast(`${tk} removed`, "success");
      load();
    } catch (e) {
      toast("Failed to remove ticker", "error");
    }
  };

  const toggleActive = async (item) => {
    try {
      await client.put(`/watchlist/${item.ticker}`, { active: !item.active });
      load();
    } catch (e) {
      toast("Failed to update", "error");
    }
  };

  if (loading) return <Spinner />;

  return (
    <div className="space-y-6" data-testid="watchlist-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Watchlist</h1>
        <p className="text-sm text-zinc-500">Add tickers and tune each one's strategy parameters</p>
      </div>

      <Card>
        <CardHeader title="Add Ticker" />
        <form onSubmit={add} className="flex flex-col md:flex-row gap-3 px-5 py-4">
          <Input
            placeholder="Ticker (e.g. NVDA)"
            value={ticker}
            data-testid="watchlist-ticker-input"
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            className="md:w-44 font-mono uppercase"
          />
          <Input
            placeholder="Notes (optional)"
            value={notes}
            data-testid="watchlist-notes-input"
            onChange={(e) => setNotes(e.target.value)}
            className="flex-1"
          />
          <Button type="submit" disabled={adding} data-testid="watchlist-add-btn">
            <Plus size={15} /> Add
          </Button>
        </form>
      </Card>

      <Card>
        <CardHeader title="Tracked Tickers" subtitle={`${items.length} total`} />
        {items.length === 0 ? (
          <EmptyState title="Watchlist is empty" hint="Add a ticker above to start tracking it." />
        ) : (
          <div className="divide-y divide-zinc-100">
            {items.map((item) => {
              const p = item.parameters;
              const open = expanded === item.ticker;
              return (
                <div key={item.ticker} data-testid={`watchlist-row-${item.ticker}`}>
                  <div className="flex items-center gap-4 px-5 py-3.5">
                    <div className="w-24">
                      <div className="font-mono font-bold text-base">{item.ticker}</div>
                      <Badge tone={item.active ? "success" : "muted"}>{item.active ? "active" : "paused"}</Badge>
                    </div>
                    <div className="flex-1 min-w-0 hidden md:block">
                      {p && (
                        <div className="font-mono text-xs text-zinc-500 tabular flex flex-wrap gap-x-4 gap-y-1">
                          <span>buy: {p.buy_threshold_stddev}σ</span>
                          <span>lookback: {p.lookback_days}d</span>
                          <span>tranche: {(p.sell_tranche_pct * 100).toFixed(0)}%</span>
                          <span>steps: [{(p.sell_gain_steps || []).map((s) => `${(s * 100).toFixed(0)}%`).join(", ")}]</span>
                          <span>cap: {fmtUSD(p.max_position_size_usd, 0)}</span>
                        </div>
                      )}
                      {item.notes && <div className="text-xs text-zinc-400 mt-1 truncate">{item.notes}</div>}
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-2 mr-1">
                        <span className="text-[11px] text-zinc-500 uppercase tracking-wide hidden sm:inline">Active</span>
                        <Toggle checked={item.active} onChange={() => toggleActive(item)} testid={`toggle-active-${item.ticker}`} />
                      </div>
                      <Button
                        variant="outline"
                        onClick={() => setExpanded(open ? null : item.ticker)}
                        data-testid={`edit-params-${item.ticker}`}
                      >
                        {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />} Params
                      </Button>
                      <Button variant="ghost" onClick={() => remove(item.ticker)} data-testid={`delete-${item.ticker}`}>
                        <Trash2 size={15} className="text-loss" />
                      </Button>
                    </div>
                  </div>
                  {open && p && (
                    <ParamEditor
                      ticker={item.ticker}
                      params={p}
                      sector={item.sector}
                      onSaved={() => {
                        setExpanded(null);
                        load();
                      }}
                    />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
