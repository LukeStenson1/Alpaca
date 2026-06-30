import React, { useEffect, useState } from "react";
import { Save, Sparkles } from "lucide-react";
import client from "../api";
import { Card, CardHeader, Button, Input, Toggle, Spinner, SectionTitle } from "../components/ui";
import { useToast } from "../components/Toast";

const PRESETS = {
  Conservative: { buy_threshold_stddev: 2.5, lookback_days: 200, sell_tranche_pct: 0.25, sell_gain_steps: "0.10, 0.20, 0.35, 0.50", stop_loss_pct: 0.15, cooldown_days: 21, max_hold_days: 730, range_pct: 0.25, use_52w_range: true, use_volatility_sizing: true, allow_downtrend_buys: false, min_conviction_to_buy: 4, earnings_blackout_days: 7, investing_style: "longterm" },
  Balanced: { buy_threshold_stddev: 2.0, lookback_days: 150, sell_tranche_pct: 0.25, sell_gain_steps: "0.10, 0.20, 0.35, 0.50", stop_loss_pct: 0.20, cooldown_days: 14, max_hold_days: "", range_pct: 0.30, use_52w_range: true, use_volatility_sizing: true, allow_downtrend_buys: false, min_conviction_to_buy: 3, earnings_blackout_days: 5, investing_style: "blended" },
  Tactical: { buy_threshold_stddev: 1.5, lookback_days: 100, sell_tranche_pct: 0.5, sell_gain_steps: "0.10, 0.25", stop_loss_pct: 0.20, cooldown_days: 5, max_hold_days: "", range_pct: 0.4, use_52w_range: false, use_volatility_sizing: false, allow_downtrend_buys: true, min_conviction_to_buy: 2, earnings_blackout_days: 3, investing_style: "tactical" },
};
const PRESET_DESC = {
  Conservative: "Deep dips only · long holds · tight risk",
  Balanced: "Sensible defaults for most long-term investors",
  Tactical: "Earlier entries · quicker profits · more active",
};
const pct = (v) => (isNaN(parseFloat(v)) ? "" : `${(parseFloat(v) * 100).toFixed(0)}%`);
const stepsToPct = (s) => (s || "").split(",").map((x) => x.trim()).filter(Boolean).map((x) => (isNaN(parseFloat(x)) ? x : `+${(parseFloat(x) * 100).toFixed(0)}%`)).join(", ");

function NumField({ label, desc, value, onChange, testid, step, helper }) {
  return (
    <div>
      <label className="text-sm font-semibold text-zinc-100">{label}</label>
      <p className="text-xs text-zinc-500 mt-0.5 leading-relaxed">{desc}</p>
      <div className="flex items-center gap-2 mt-1.5">
        <Input type="number" step={step} value={value} data-testid={testid} onChange={(e) => onChange(e.target.value)} className="font-mono" />
        {helper && <span className="text-xs font-mono text-klein whitespace-nowrap min-w-[44px]">{helper}</span>}
      </div>
    </div>
  );
}
function ToggleField({ label, desc, checked, onChange, testid, danger }) {
  return (
    <div className="flex items-start justify-between gap-3 border border-zinc-800 bg-zinc-950 rounded-lg px-3 py-2.5">
      <div><div className="text-sm font-semibold text-zinc-100">{label}</div><p className="text-xs text-zinc-500 mt-0.5">{desc}</p></div>
      <div className="pt-0.5"><Toggle checked={checked} danger={danger} onChange={onChange} testid={testid} /></div>
    </div>
  );
}
function Section({ title, hint, children }) {
  return (
    <div>
      <SectionTitle title={title} hint={hint} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">{children}</div>
    </div>
  );
}

export default function Strategy({ embedded = false }) {
  const toast = useToast();
  const [f, setF] = useState(null);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    client.get("/strategy/config").then((r) => {
      const d = r.data;
      setF({ ...d, sell_gain_steps: (d.sell_gain_steps || []).join(", "), max_hold_days: d.max_hold_days ?? "" });
    });
  }, []);

  if (!f) return <Spinner />;

  const applyPreset = (name) => { setF((p) => ({ ...p, ...PRESETS[name] })); toast(`${name} preset loaded — review and Save`, "info"); };

  const save = async () => {
    setSaving(true);
    try {
      const steps = f.sell_gain_steps.split(",").map((s) => parseFloat(s.trim())).filter((n) => !isNaN(n));
      await client.put("/strategy/config", {
        buy_threshold_stddev: parseFloat(f.buy_threshold_stddev), lookback_days: parseInt(f.lookback_days, 10),
        sell_tranche_pct: parseFloat(f.sell_tranche_pct), sell_gain_steps: steps,
        max_position_size_usd: parseFloat(f.max_position_size_usd), stop_loss_pct: parseFloat(f.stop_loss_pct),
        cooldown_days: parseInt(f.cooldown_days, 10), max_hold_days: f.max_hold_days === "" ? null : parseInt(f.max_hold_days, 10),
        use_52w_range: f.use_52w_range, range_pct: parseFloat(f.range_pct), allow_downtrend_buys: f.allow_downtrend_buys,
        use_volatility_sizing: f.use_volatility_sizing, investing_style: f.investing_style,
        min_conviction_to_buy: parseInt(f.min_conviction_to_buy, 10), earnings_blackout_days: parseInt(f.earnings_blackout_days, 10),
      });
      toast("Strategy rules saved — applies to all stocks", "success");
    } catch (e) { toast("Failed to save", "error"); } finally { setSaving(false); }
  };

  return (
    <div className="space-y-5" data-testid="strategy-page">
      {!embedded && (
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-50">Strategy</h1>
          <p className="text-sm text-zinc-500">One set of rules applied to every stock in your watchlist.</p>
        </div>
      )}

      <Card>
        <CardHeader title="Quick start presets" subtitle="Pick a starting point, then fine-tune below — no need to touch every field" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-4">
          {Object.keys(PRESETS).map((n) => (
            <button key={n} onClick={() => applyPreset(n)} data-testid={`preset-${n.toLowerCase()}`}
              className="text-left border border-zinc-800 hover:border-klein/60 bg-zinc-950 rounded-lg p-4 transition-colors group">
              <div className="flex items-center gap-2 text-zinc-100 font-semibold text-sm">
                <Sparkles size={14} className="text-klein" /> {n}
              </div>
              <p className="text-xs text-zinc-500 mt-1.5 leading-relaxed">{PRESET_DESC[n]}</p>
            </button>
          ))}
        </div>
      </Card>

      <Card><CardHeader title="Approach" subtitle="How aggressive and how long-term" /><div className="px-5 py-5">
        <Section title="Investing style">
          <div className="md:col-span-2 flex gap-2">
            {["longterm", "blended", "tactical"].map((s) => (
              <button key={s} onClick={() => set("investing_style", s)} data-testid={`style-${s}`}
                className={`flex-1 border rounded-lg py-2.5 text-sm capitalize transition-colors ${f.investing_style === s ? "border-klein bg-klein/15 text-zinc-50 font-medium" : "border-zinc-800 text-zinc-300 hover:bg-zinc-800"}`}>
                {s === "longterm" ? "Long-term" : s}
              </button>
            ))}
          </div>
          <NumField label="Minimum conviction to buy (1–5)" testid="min-conviction" step="1" value={f.min_conviction_to_buy} onChange={(v) => set("min_conviction_to_buy", v)}
            desc="Only buy stocks you've rated at least this high on the Watchlist. Higher = only your best ideas." />
          <NumField label="Earnings blackout (days)" testid="earnings-blackout" step="1" value={f.earnings_blackout_days} onChange={(v) => set("earnings_blackout_days", v)}
            desc="Don't open new buys within this many days before a stock's earnings date." />
        </Section>
      </div></Card>

      <Card><CardHeader title="When to BUY" /><div className="px-5 py-5"><Section title="Dip trigger">
        <NumField label="Buy dip size (std devs below avg)" testid="buy-threshold" step="0.1" value={f.buy_threshold_stddev} onChange={(v) => set("buy_threshold_stddev", v)}
          desc="How far below average it must fall before buying. Higher = bigger dips only. Recommended 1.5–2.5." />
        <NumField label="Lookback window (days)" testid="lookback" step="1" value={f.lookback_days} onChange={(v) => set("lookback_days", v)}
          desc="Days of history defining 'normal'. Longer = more long-term. Recommended 100–200." />
        <ToggleField label="Only buy near 52-week lows" testid="use-52w" checked={f.use_52w_range} onChange={(v) => set("use_52w_range", v)} desc="Extra value safety." />
        {f.use_52w_range && <NumField label="…bottom how much of 52w range?" testid="range-pct" step="0.05" value={f.range_pct} onChange={(v) => set("range_pct", v)} helper={`= bottom ${pct(f.range_pct)}`} desc="0.30 = cheapest 30% of the year." />}
        <ToggleField label="Allow buying in a downtrend" testid="downtrend" danger checked={f.allow_downtrend_buys} onChange={(v) => set("allow_downtrend_buys", v)} desc="Off = only buy above the 200-day average (safer)." />
      </Section></div></Card>

      <Card><CardHeader title="Taking profits & Risk" /><div className="px-5 py-5"><Section title="Sell + protect">
        <NumField label="Profit levels to sell at" testid="sell-steps" step="0.01" value={f.sell_gain_steps} onChange={(v) => set("sell_gain_steps", v)} helper={stepsToPct(f.sell_gain_steps)}
          desc="Comma-separated gains, e.g. 0.10, 0.20 = sell some at +10%, +20%." />
        <NumField label="How much to sell each time" testid="tranche" step="0.05" value={f.sell_tranche_pct} onChange={(v) => set("sell_tranche_pct", v)} helper={`= ${pct(f.sell_tranche_pct)}`}
          desc="Fraction sold at each level. 0.25 = 25% at a time." />
        <NumField label="Stop-loss (auto-sell if it drops)" testid="stop-loss" step="0.01" value={f.stop_loss_pct} onChange={(v) => set("stop_loss_pct", v)} helper={`= ${pct(f.stop_loss_pct)}`}
          desc="Sell all if down this much from entry. 0 = off. Long-term often uses a wider 15–25%." />
        <NumField label="Most money per stock (USD)" testid="max-size" step="100" value={f.max_position_size_usd} onChange={(v) => set("max_position_size_usd", v)} helper="cap"
          desc="Never invest more than this in any single stock." />
        <NumField label="Cooldown after exit (days)" testid="cooldown" step="1" value={f.cooldown_days} onChange={(v) => set("cooldown_days", v)}
          desc="Wait this long before re-buying a stock you exited." />
        <NumField label="Flag if held too long (days, optional)" testid="max-hold" step="1" value={f.max_hold_days} onChange={(v) => set("max_hold_days", v)}
          desc="Just a review reminder. Never auto-sells. Blank = off." />
        <ToggleField label="Smaller bets on jumpier stocks" testid="vol-sizing" checked={f.use_volatility_sizing} onChange={(v) => set("use_volatility_sizing", v)} desc="Invest less in more volatile names." />
      </Section></div></Card>

      <div className="flex justify-end">
        <Button onClick={save} disabled={saving} data-testid="save-strategy-btn"><Save size={15} /> {saving ? "Saving…" : "Save Strategy Rules"}</Button>
      </div>
    </div>
  );
}
