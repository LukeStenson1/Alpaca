import React, { useEffect, useState, useCallback } from "react";
import { Check, X, Sparkles, ArrowRight } from "lucide-react";
import client, { fmtDate } from "../api";
import { Card, CardHeader, Button, Badge, Spinner, EmptyState } from "../components/ui";
import { useToast } from "../components/Toast";

export default function Suggestions() {
  const toast = useToast();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [tab, setTab] = useState("pending");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = tab === "all" ? {} : { status: tab };
      const res = await client.get("/suggestions", { params });
      setItems(res.data);
    } catch (e) {
      toast("Failed to load suggestions", "error");
    } finally {
      setLoading(false);
    }
  }, [tab, toast]);

  useEffect(() => {
    load();
  }, [load]);

  const generate = async () => {
    setGenerating(true);
    try {
      const res = await client.post("/suggestions/generate");
      toast(`Analysis complete — ${res.data.created} suggestion(s)`, "success");
      load();
    } catch (e) {
      toast("Failed to generate suggestions", "error");
    } finally {
      setGenerating(false);
    }
  };

  const act = async (id, action) => {
    try {
      await client.post(`/suggestions/${id}/${action}`);
      toast(`Suggestion ${action}d`, action === "approve" ? "success" : "info");
      load();
    } catch (e) {
      toast(e.response?.data?.detail || "Action failed", "error");
    }
  };

  const tones = { pending: "warn", approved: "success", rejected: "muted" };

  return (
    <div className="space-y-6" data-testid="suggestions-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Suggestions</h1>
          <p className="text-sm text-zinc-500">Rule-based threshold tweaks from trade-history analysis — you approve or reject</p>
        </div>
        <Button onClick={generate} disabled={generating} data-testid="generate-suggestions-btn">
          <Sparkles size={15} /> {generating ? "Analyzing…" : "Run Analysis"}
        </Button>
      </div>

      <div className="flex gap-1 border-b border-zinc-200">
        {["pending", "approved", "rejected", "all"].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            data-testid={`tab-${t}`}
            className={`px-4 py-2 text-sm capitalize border-b-2 -mb-px transition-colors ${
              tab === t ? "border-klein text-klein font-medium" : "border-transparent text-zinc-500 hover:text-zinc-800"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {loading ? (
        <Spinner />
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            title={`No ${tab === "all" ? "" : tab} suggestions`}
            hint="Run analysis after some trades accumulate to get explainable threshold recommendations."
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {items.map((s) => (
            <Card key={s.id} data-testid={`suggestion-${s.id}`}>
              <div className="flex items-start justify-between px-5 py-3.5 border-b border-zinc-200">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold">{s.ticker}</span>
                  <Badge tone={tones[s.status]}>{s.status}</Badge>
                </div>
                <span className="text-[11px] text-zinc-400 font-mono">{fmtDate(s.created_at)}</span>
              </div>
              <div className="px-5 py-4 space-y-3">
                <div className="flex items-center gap-3 font-mono text-sm">
                  <span className="text-zinc-500">{s.suggested_param}</span>
                </div>
                <div className="flex items-center gap-3 font-mono text-lg">
                  <span className="text-zinc-400 line-through tabular">{s.current_value}</span>
                  <ArrowRight size={16} className="text-klein" />
                  <span className="text-klein font-semibold tabular">{s.suggested_value}</span>
                </div>
                <p className="text-sm text-zinc-600 leading-relaxed">{s.rationale}</p>
                {s.status === "pending" && (
                  <div className="flex gap-2 pt-1">
                    <Button variant="success" onClick={() => act(s.id, "approve")} data-testid={`approve-suggestion-btn-${s.id}`}>
                      <Check size={15} /> Approve
                    </Button>
                    <Button variant="outline" onClick={() => act(s.id, "reject")} data-testid={`reject-suggestion-btn-${s.id}`}>
                      <X size={15} /> Reject
                    </Button>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
