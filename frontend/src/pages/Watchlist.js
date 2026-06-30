import React, { useEffect, useState, useCallback } from "react";
import { Plus, Trash2, ChevronDown, ChevronUp, Save, CheckCircle2, XCircle, Star } from "lucide-react";
import { Link } from "react-router-dom";
import client from "../api";
import { Card, CardHeader, Button, Input, Badge, Toggle, Spinner, EmptyState } from "../components/ui";
import { useToast } from "../components/Toast";

function Stars({ value, onChange, testid }) {
  return (
    <div className="flex items-center gap-1" data-testid={testid}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" onClick={() => onChange(n)} data-testid={`${testid}-${n}`}
          className="p-0.5 transition-transform hover:scale-110">
          <Star size={20} className={n <= value ? "fill-klein text-klein" : "text-zinc-300"} />
        </button>
      ))}
    </div>
  );
}

function StockEditor({ item, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState({
    conviction: item.conviction ?? 3,
    thesis: item.thesis || "",
    next_earnings_date: item.next_earnings_date || "",
    sector: item.sector || "",
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      await client.put(`/watchlist/${item.ticker}`, {
        conviction: parseInt(form.conviction, 10),
        thesis: form.thesis,
        next_earnings_date: form.next_earnings_date,
        sector: form.sector,
      });
      toast(`${item.ticker} updated`, "success");
      onSaved();
    } catch (e) {
      toast("Failed to save", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-zinc-50 border-t border-zinc-200 px-5 py-5 space-y-4" data-testid={`stock-editor-${item.ticker}`}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <div>
          <label className="text-sm font-semibold text-zinc-800">Conviction (1–5)</label>
          <p className="text-xs text-zinc-500 mt-0.5 mb-2">How strongly you believe in this stock. The strategy only buys names at or above your global minimum-conviction setting.</p>
          <Stars value={parseInt(form.conviction, 10)} onChange={(v) => set("conviction", v)} testid={`conviction-${item.ticker}`} />
        </div>
        <div>
          <label className="text-sm font-semibold text-zinc-800">Next earnings date (optional)</label>
          <p className="text-xs text-zinc-500 mt-0.5 mb-2">Used to pause buys just before earnings. Format YYYY-MM-DD.</p>
          <Input type="date" value={form.next_earnings_date} data-testid={`earnings-${item.ticker}`}
            onChange={(e) => set("next_earnings_date", e.target.value)} className="font-mono" />
        </div>
        <div>
          <label className="text-sm font-semibold text-zinc-800">Sector (optional)</label>
          <p className="text-xs text-zinc-500 mt-0.5 mb-2">Shown in the Overview sector breakdown.</p>
          <Input value={form.sector} data-testid={`sector-${item.ticker}`} placeholder="e.g. Technology"
            onChange={(e) => set("sector", e.target.value)} />
        </div>
        <div className="md:col-span-2">
          <label className="text-sm font-semibold text-zinc-800">Thesis — why you own it (optional)</label>
          <p className="text-xs text-zinc-500 mt-0.5 mb-2">Your reasoning, e.g. a pick from Financial Education / BWB, strong moat, growth, etc.</p>
          <textarea value={form.thesis} data-testid={`thesis-${item.ticker}`} rows={3}
            onChange={(e) => set("thesis", e.target.value)}
            className="w-full border border-zinc-300 rounded-md px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-zinc-950" />
        </div>
      </div>
      <div className="flex justify-end">
        <Button onClick={save} disabled={saving} data-testid={`save-stock-${item.ticker}`}>
          <Save size={15} /> {saving ? "Saving…" : "Save"}
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
  const [validation, setValidation] = useState(null);

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

  useEffect(() => {
    const tk = ticker.trim().toUpperCase();
    if (!tk) { setValidation(null); return; }
    const id = setTimeout(async () => {
      try {
        const res = await client.get("/watchlist/validate", { params: { ticker: tk } });
        setValidation(res.data);
      } catch (e) { setValidation(null); }
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
    if (!window.confirm(`Remove ${tk}? Its trade history is kept.`)) return;
    try {
      await client.delete(`/watchlist/${tk}`);
      toast(`${tk} removed`, "success");
      load();
    } catch (e) { toast("Failed to remove ticker", "error"); }
  };

  const toggleActive = async (item) => {
    try {
      await client.put(`/watchlist/${item.ticker}`, { active: !item.active });
      load();
    } catch (e) { toast("Failed to update", "error"); }
  };

  if (loading) return <Spinner />;
  const canAdd = !ticker.trim() || (validation && validation.valid);

  return (
    <div className="space-y-6" data-testid="watchlist-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Watchlist</h1>
          <p className="text-sm text-zinc-500">Pick your stocks and rate your conviction. The buy/sell rules are set once on the <Link to="/strategy" className="text-klein underline">Strategy</Link> page.</p>
        </div>
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
              const open = expanded === item.ticker;
              const conv = item.conviction ?? 3;
              return (
                <div key={item.ticker} data-testid={`watchlist-row-${item.ticker}`}>
                  <div className="flex items-center gap-4 px-5 py-3.5">
                    <div className="w-44 min-w-44">
                      <div className="font-mono font-bold text-base">{item.ticker}</div>
                      {item.name && <div className="text-xs text-zinc-400 truncate">{item.name}</div>}
                      <Badge tone={item.active ? "success" : "muted"} className="mt-1">{item.active ? "active" : "paused"}</Badge>
                    </div>
                    <div className="flex-1 min-w-0 hidden md:block">
                      <div className="flex items-center gap-1">
                        {[1, 2, 3, 4, 5].map((n) => (
                          <Star key={n} size={14} className={n <= conv ? "fill-klein text-klein" : "text-zinc-200"} />
                        ))}
                        <span className="text-xs text-zinc-400 ml-1">conviction</span>
                      </div>
                      <div className="text-xs text-zinc-500 mt-1 flex flex-wrap gap-x-4">
                        {item.sector && <span>{item.sector}</span>}
                        {item.next_earnings_date && <span>earnings {item.next_earnings_date}</span>}
                        {item.thesis && <span className="truncate max-w-md italic">“{item.thesis}”</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-2 mr-1">
                        <span className="text-[11px] text-zinc-500 uppercase tracking-wide hidden sm:inline">Active</span>
                        <Toggle checked={item.active} onChange={() => toggleActive(item)} testid={`toggle-active-${item.ticker}`} />
                      </div>
                      <Button variant="outline" onClick={() => setExpanded(open ? null : item.ticker)} data-testid={`edit-params-${item.ticker}`}>
                        {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />} Edit
                      </Button>
                      <Button variant="ghost" onClick={() => remove(item.ticker)} data-testid={`delete-${item.ticker}`}>
                        <Trash2 size={15} className="text-loss" />
                      </Button>
                    </div>
                  </div>
                  {open && <StockEditor item={item} onSaved={() => { setExpanded(null); load(); }} />}
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
