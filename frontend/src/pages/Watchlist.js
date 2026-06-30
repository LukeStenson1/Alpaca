import React, { useEffect, useState, useCallback } from "react";
import { Plus, Trash2, ChevronDown, ChevronUp, Save, CheckCircle2, XCircle, Sparkles, Info } from "lucide-react";
import client from "../api";
import { Card, CardHeader, Button, Input, Badge, Toggle, Spinner, EmptyState } from "../components/ui";
import { useToast } from "../components/Toast";

// ---------- recommended starting presets ----------
const PRESETS = {
  Conservative: {
    buy_threshold_stddev: 2.5, lookback_days: 200, sell_tranche_pct: 0.25,
    sell_gain_steps: "0.05, 0.10, 0.20, 0.30", max_position_size_usd: 1000,
    stop_loss_pct: 0.12, cooldown_days: 10, max_hold_days: 365, range_pct: 0.2,
    use_52w_range: true, use_volatility_sizing: true, allow_downtrend_buys: false,
  },
  Balanced: {
    buy_threshold_stddev: 2.0, lookback_days: 150, sell_tranche_pct: 0.33,
    sell_gain_steps: "0.08, 0.15, 0.30", max_position_size_usd: 1000,
    stop_loss_pct: 0.15, cooldown_days: 7, max_hold_days: "", range_pct: 0.15,
    use_52w_range: false, use_volatility_sizing: false, allow_downtrend_buys: false,
  },
  Aggressive: {
    buy_threshold_stddev: 1.5, lookback_days: 100, sell_tranche_pct: 0.5,
    sell_gain_steps: "0.10, 0.25", max_position_size_usd: 1000,
    stop_loss_pct: 0.2, cooldown_days: 3, max_hold_days: "", range_pct: 0.25,
    use_52w_range: false, use_volatility_sizing: false, allow_downtrend_buys: true,
  },
};

const pct = (v) => (isNaN(parseFloat(v)) ? "" : `${(parseFloat(v) * 100).toFixed(0)}%`);
const stepsToPct = (s) =>
  (s || "").split(",").map((x) => x.trim()).filter(Boolean)
    .map((x) => (isNaN(parseFloat(x)) ? x : `+${(parseFloat(x) * 100).toFixed(0)}%`)).join(", ");

function NumField({ label, desc, value, onChange, testid, step, helper }) {
  return (
    <div>
      <label className="text-sm font-semibold text-zinc-800">{label}</label>
      <p className="text-xs text-zinc-500 mt-0.5 leading-relaxed">{desc}</p>
      <div className="flex items-center gap-2 mt-1.5">
        <Input type="number" step={step} value={value} data-testid={testid}
               onChange={(e) => onChange(e.target.value)} className="font-mono" />
        {helper && <span className="text-xs font-mono text-klein whitespace-nowrap min-w-[44px]">{helper}</span>}
      </div>
    </div>
  );
}

function ToggleField({ label, desc, checked, onChange, testid, danger }) {
  return (
    <div className="flex items-start justify-between gap-3 border border-zinc-200 bg-white rounded-md px-3 py-2.5">
      <div>
        <div className="text-sm font-semibold text-zinc-800">{label}</div>
        <p className="text-xs text-zinc-500 mt-0.5 leading-relaxed">{desc}</p>
      </div>
      <div className="pt-0.5"><Toggle checked={checked} danger={danger} onChange={onChange} testid={testid} /></div>
    </div>
  );
}

function Section({ title, hint, children }) {
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-3">
        <h4 className="text-[11px] font-bold uppercase tracking-wider text-zinc-950">{title}</h4>
        {hint && <span className="text-xs text-zinc-400">{hint}</span>}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">{children}</div>
    </div>
  );
}

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
  const applyPreset = (name) => {
    setForm((f) => ({ ...f, ...PRESETS[name] }));
    toast(`${name} preset loaded — review and Save to apply`, "info");
  };

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
      toast(`${ticker} settings saved`, "success");
      onSaved();
    } catch (e) {
      toast("Failed to save settings", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-zinc-50 border-t border-zinc-200 px-5 py-5 space-y-6" data-testid={`param-editor-${ticker}`}>
      {/* presets */}
      <div className="flex flex-wrap items-center gap-2 bg-white border border-zinc-200 rounded-md px-3 py-2.5">
        <span className="text-xs text-zinc-600 flex items-center gap-1.5 mr-1">
          <Sparkles size={14} className="text-klein" /> Not sure where to start? Load a preset:
        </span>
        {Object.keys(PRESETS).map((name) => (
          <Button key={name} variant="outline" onClick={() => applyPreset(name)} data-testid={`preset-${name.toLowerCase()}-${ticker}`} className="py-1.5">
            {name}
          </Button>
        ))}
      </div>

      {/* BUY */}
      <Section title="When to BUY" hint="the dip-buying trigger">
        <NumField label="Buy dip size (std devs below average)" testid={`param-buy_threshold_stddev-${ticker}`} step="0.1"
          value={form.buy_threshold_stddev} onChange={(v) => set("buy_threshold_stddev", v)}
          desc="How far below its recent average price the stock must fall before buying. Higher = waits for bigger dips (buys less often); lower = buys on smaller dips. Recommended 1.5–2.5." />
        <NumField label="Lookback window (days)" testid={`param-lookback_days-${ticker}`} step="1"
          value={form.lookback_days} onChange={(v) => set("lookback_days", v)}
          desc="How many days of history define the 'normal' price. Longer = smoother, more long-term. Recommended 100–200." />
        <ToggleField label="Only buy near 52-week lows" testid={`param-use_52w_range-${ticker}`}
          checked={form.use_52w_range} onChange={(v) => set("use_52w_range", v)}
          desc="Extra safety: only buy when the price sits in the bottom slice of its 52-week range." />
        {form.use_52w_range && (
          <NumField label="…bottom how much of the 52-week range?" testid={`param-range_pct-${ticker}`} step="0.05"
            value={form.range_pct} onChange={(v) => set("range_pct", v)} helper={`= bottom ${pct(form.range_pct)}`}
            desc="0.15 = only buy in the cheapest 15% of the past year's range." />
        )}
        <ToggleField label="Allow buying in a downtrend" testid={`param-allow_downtrend_buys-${ticker}`} danger
          checked={form.allow_downtrend_buys} onChange={(v) => set("allow_downtrend_buys", v)}
          desc="By default the strategy only buys dips while the stock is above its 200-day average (an uptrend). Turn ON to also buy when it's falling long-term — riskier. Keep OFF if unsure." />
      </Section>

      {/* SELL */}
      <Section title="Taking profits (SELL)" hint="scale out as it rises">
        <NumField label="Profit levels to sell at" testid={`param-sell_gain_steps-${ticker}`} step="0.01"
          value={form.sell_gain_steps} onChange={(v) => set("sell_gain_steps", v)}
          helper={stepsToPct(form.sell_gain_steps)}
          desc="Comma-separated gains where a chunk is sold. e.g. 0.05, 0.10, 0.20 means sell some at +5%, +10%, +20%." />
        <NumField label="How much to sell each time" testid={`param-sell_tranche_pct-${ticker}`} step="0.05"
          value={form.sell_tranche_pct} onChange={(v) => set("sell_tranche_pct", v)} helper={`= ${pct(form.sell_tranche_pct)}`}
          desc="Fraction of the position sold at each profit level above. 0.25 = sell 25% at a time. Recommended 0.25–0.5." />
      </Section>

      {/* RISK */}
      <Section title="Risk controls" hint="protect the downside">
        <NumField label="Stop-loss (auto-sell if it drops)" testid={`param-stop_loss_pct-${ticker}`} step="0.01"
          value={form.stop_loss_pct} onChange={(v) => set("stop_loss_pct", v)} helper={`= ${pct(form.stop_loss_pct)}`}
          desc="Sell the entire position if it falls this far below your entry price. 0 = no stop-loss. 0.15 = bail out if down 15%. Recommended 0.10–0.20." />
        <NumField label="Most money in this stock (USD)" testid={`param-max_position_size_usd-${ticker}`} step="100"
          value={form.max_position_size_usd} onChange={(v) => set("max_position_size_usd", v)} helper="cap"
          desc="The strategy will never invest more than this in this one ticker." />
        <NumField label="Cooldown after exit (days)" testid={`param-cooldown_days-${ticker}`} step="1"
          value={form.cooldown_days} onChange={(v) => set("cooldown_days", v)}
          desc="After fully exiting, wait this many days before buying again — avoids jumping back into a still-falling stock. Recommended 5–10." />
        <NumField label="Flag if held too long (days, optional)" testid={`param-max_hold_days-${ticker}`} step="1"
          value={form.max_hold_days} onChange={(v) => set("max_hold_days", v)}
          desc="Just a reminder on the Overview page if a position is held longer than this. It never auto-sells. Leave blank to disable." />
        <ToggleField label="Smaller bets on jumpier stocks" testid={`param-use_volatility_sizing-${ticker}`}
          checked={form.use_volatility_sizing} onChange={(v) => set("use_volatility_sizing", v)}
          desc="Automatically invest less in more volatile names, scaled to your baseline volatility setting." />
      </Section>

      {/* INFO */}
      <Section title="Info" hint="optional tagging">
        <div className="md:col-span-2">
          <label className="text-sm font-semibold text-zinc-800">Sector (manual tag)</label>
          <p className="text-xs text-zinc-500 mt-0.5">Used for the sector-exposure breakdown on the Overview page. e.g. Technology, Healthcare.</p>
          <Input value={form.sector} data-testid={`param-sector-${ticker}`} onChange={(e) => set("sector", e.target.value)}
                 placeholder="e.g. Technology" className="mt-1.5" />
        </div>
      </Section>

      <div className="flex justify-end">
        <Button onClick={save} disabled={saving} data-testid={`save-params-${ticker}`}>
          <Save size={15} /> {saving ? "Saving…" : "Save Settings"}
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
  const [validation, setValidation] = useState(null); // {valid, message}

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

  useEffect(() => { load(); }, [load]);

  // live validation (debounced)
  useEffect(() => {
    const tk = ticker.trim().toUpperCase();
    if (!tk) { setValidation(null); return; }
    const id = setTimeout(async () => {
      try {
        const res = await client.get("/watchlist/validate", { params: { ticker: tk } });
        setValidation(res.data);
      } catch (e) {
        setValidation(null);
      }
    }, 450);
    return () => clearTimeout(id);
  }, [ticker]);

  const add = async (e) => {
    e.preventDefault();
    const tk = ticker.trim().toUpperCase();
    if (!tk) return;
    setAdding(true);
    try {
      const res = await client.post("/watchlist", { ticker: tk, notes: notes || null });
      toast(`${tk} added — ${res.data.name || ""}`, "success");
      setTicker(""); setNotes(""); setValidation(null);
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
  const canAdd = !ticker.trim() || (validation && validation.valid);

  return (
    <div className="space-y-6" data-testid="watchlist-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Watchlist</h1>
        <p className="text-sm text-zinc-500">Add stocks to trade and tune each one's strategy. Hit “Params” for plain-English settings.</p>
      </div>

      <Card>
        <CardHeader title="Add a Stock" subtitle="We check the symbol is real and tradable before adding" />
        <form onSubmit={add} className="px-5 py-4 space-y-3">
          <div className="flex flex-col md:flex-row gap-3">
            <Input placeholder="Ticker (e.g. NVDA)" value={ticker} data-testid="watchlist-ticker-input"
              onChange={(e) => setTicker(e.target.value.toUpperCase())} className="md:w-44 font-mono uppercase" />
            <Input placeholder="Notes (optional)" value={notes} data-testid="watchlist-notes-input"
              onChange={(e) => setNotes(e.target.value)} className="flex-1" />
            <Button type="submit" disabled={adding || !canAdd} data-testid="watchlist-add-btn">
              <Plus size={15} /> {adding ? "Adding…" : "Add"}
            </Button>
          </div>
          {validation && (
            <div className={`flex items-center gap-2 text-sm ${validation.valid ? "text-profit" : "text-loss"}`} data-testid="ticker-validation">
              {validation.valid ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
              <span>{validation.message}</span>
            </div>
          )}
        </form>
      </Card>

      <Card>
        <CardHeader title="Your Stocks" subtitle={`${items.length} tracked`} />
        {items.length === 0 ? (
          <EmptyState title="No stocks yet" hint="Add a ticker above to start tracking it." />
        ) : (
          <div className="divide-y divide-zinc-100">
            {items.map((item) => {
              const p = item.parameters;
              const open = expanded === item.ticker;
              return (
                <div key={item.ticker} data-testid={`watchlist-row-${item.ticker}`}>
                  <div className="flex items-center gap-4 px-5 py-3.5">
                    <div className="w-44 min-w-44">
                      <div className="font-mono font-bold text-base">{item.ticker}</div>
                      {item.name && <div className="text-xs text-zinc-400 truncate">{item.name}</div>}
                      <Badge tone={item.active ? "success" : "muted"} className="mt-1">{item.active ? "active" : "paused"}</Badge>
                    </div>
                    <div className="flex-1 min-w-0 hidden lg:block">
                      {p && (
                        <div className="text-xs text-zinc-500 flex flex-wrap gap-x-4 gap-y-1">
                          <span>Buys on a <b className="text-zinc-700">{p.buy_threshold_stddev}σ</b> dip ({p.lookback_days}d)</span>
                          <span>Sells {(p.sell_tranche_pct * 100).toFixed(0)}% at [{(p.sell_gain_steps || []).map((s) => `+${(s * 100).toFixed(0)}%`).join(", ")}]</span>
                          <span>Stop {p.stop_loss_pct > 0 ? `${(p.stop_loss_pct * 100).toFixed(0)}%` : "off"}</span>
                          <span>Cap ${Number(p.max_position_size_usd).toLocaleString()}</span>
                        </div>
                      )}
                      {item.sector && <div className="text-xs text-zinc-400 mt-1">{item.sector}</div>}
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-2 mr-1">
                        <span className="text-[11px] text-zinc-500 uppercase tracking-wide hidden sm:inline">Active</span>
                        <Toggle checked={item.active} onChange={() => toggleActive(item)} testid={`toggle-active-${item.ticker}`} />
                      </div>
                      <Button variant="outline" onClick={() => setExpanded(open ? null : item.ticker)} data-testid={`edit-params-${item.ticker}`}>
                        {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />} Params
                      </Button>
                      <Button variant="ghost" onClick={() => remove(item.ticker)} data-testid={`delete-${item.ticker}`}>
                        <Trash2 size={15} className="text-loss" />
                      </Button>
                    </div>
                  </div>
                  {open && p && (
                    <ParamEditor ticker={item.ticker} params={p} sector={item.sector}
                      onSaved={() => { setExpanded(null); load(); }} />
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
