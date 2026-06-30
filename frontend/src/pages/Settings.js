import React, { useEffect, useState } from "react";
import { ShieldCheck, AlertTriangle, Save, Clock } from "lucide-react";
import client, { fmtUSD } from "../api";
import { Card, CardHeader, Button, Input, Badge, Toggle, Spinner } from "../components/ui";
import { useToast } from "../components/Toast";
import { useSystem } from "../components/SystemContext";

export default function Settings() {
  const toast = useToast();
  const { state, refresh } = useSystem();
  const [maxLoss, setMaxLoss] = useState("");
  const [maxExp, setMaxExp] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [showLiveConfirm, setShowLiveConfirm] = useState(false);
  const [savingLimits, setSavingLimits] = useState(false);

  useEffect(() => {
    if (state) {
      setMaxLoss(state.max_daily_loss_usd);
      setMaxExp(state.max_total_exposure_usd);
    }
  }, [state]);

  if (!state) return <Spinner />;

  const isLive = state.trading_mode === "live";

  const switchMode = async (targetLive) => {
    if (targetLive) {
      setShowLiveConfirm(true);
      return;
    }
    try {
      await client.post("/system/mode", { mode: "paper" });
      await refresh();
      toast("Switched to PAPER mode", "success");
    } catch (e) {
      toast("Failed to switch mode", "error");
    }
  };

  const confirmLive = async () => {
    try {
      await client.post("/system/mode", { mode: "live", confirmation: confirmText });
      await refresh();
      setShowLiveConfirm(false);
      setConfirmText("");
      toast("LIVE mode enabled — real orders are now possible", "warning");
    } catch (e) {
      toast(e.response?.data?.detail || "Confirmation failed", "error");
    }
  };

  const saveLimits = async () => {
    setSavingLimits(true);
    try {
      await client.put("/system/safety-limits", {
        max_daily_loss_usd: parseFloat(maxLoss),
        max_total_exposure_usd: parseFloat(maxExp),
      });
      await refresh();
      toast("Safety limits saved", "success");
    } catch (e) {
      toast("Failed to save limits", "error");
    } finally {
      setSavingLimits(false);
    }
  };

  const toggleScheduler = async () => {
    try {
      await client.put("/system/safety-limits", { scheduler_enabled: !state.scheduler_enabled });
      await refresh();
    } catch (e) {
      toast("Failed to update scheduler", "error");
    }
  };

  return (
    <div className="space-y-6 max-w-3xl" data-testid="settings-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-zinc-500">Trading mode and global safety limits</p>
      </div>

      {/* Trading mode */}
      <Card>
        <CardHeader title="Trading Mode" subtitle="Live mode requires an explicit typed confirmation" />
        <div className="px-5 py-5">
          <div className="flex items-center gap-4">
            <button
              onClick={() => switchMode(false)}
              data-testid="select-paper-btn"
              className={`flex-1 border rounded-md p-4 text-left transition-colors ${
                !isLive ? "border-klein bg-blue-50/50 ring-1 ring-klein" : "border-zinc-200 hover:bg-zinc-50"
              }`}
            >
              <div className="flex items-center gap-2 font-semibold">
                <ShieldCheck size={18} className="text-klein" /> Paper
              </div>
              <p className="text-xs text-zinc-500 mt-1">Simulated orders. Safe for testing.</p>
            </button>
            <button
              onClick={() => switchMode(true)}
              data-testid="select-live-btn"
              className={`flex-1 border rounded-md p-4 text-left transition-colors ${
                isLive ? "border-loss bg-red-50/50 ring-1 ring-loss" : "border-zinc-200 hover:bg-zinc-50"
              }`}
            >
              <div className="flex items-center gap-2 font-semibold text-loss">
                <AlertTriangle size={18} /> Live
              </div>
              <p className="text-xs text-zinc-500 mt-1">Real money. Real orders against your live account.</p>
            </button>
          </div>
          <div className="mt-4 flex items-center gap-2 text-sm">
            Current mode:
            <Badge tone={isLive ? "danger" : "klein"} testid="current-mode-badge">{state.trading_mode}</Badge>
          </div>

          {showLiveConfirm && (
            <div className="mt-4 border border-loss rounded-md bg-red-50 p-4" data-testid="live-confirm-box">
              <div className="flex items-center gap-2 text-loss font-semibold text-sm">
                <AlertTriangle size={16} /> Enable LIVE trading
              </div>
              <p className="text-xs text-zinc-600 mt-1">
                This will place real orders with real money. Type <span className="font-mono font-bold">CONFIRM LIVE</span> to proceed.
              </p>
              <div className="flex gap-2 mt-3">
                <Input
                  placeholder="CONFIRM LIVE"
                  value={confirmText}
                  data-testid="live-confirm-input"
                  onChange={(e) => setConfirmText(e.target.value)}
                  className="font-mono"
                />
                <Button variant="danger" onClick={confirmLive} disabled={confirmText !== "CONFIRM LIVE"} data-testid="confirm-live-btn">
                  Enable Live
                </Button>
                <Button variant="outline" onClick={() => { setShowLiveConfirm(false); setConfirmText(""); }}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* Safety limits */}
      <Card>
        <CardHeader title="Global Safety Limits" subtitle="Enforced server-side, independent of strategy logic" />
        <div className="px-5 py-5 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Max daily loss (USD)</label>
              <Input type="number" step="50" value={maxLoss} data-testid="max-daily-loss-input" onChange={(e) => setMaxLoss(e.target.value)} className="mt-1 font-mono" />
              <p className="text-xs text-zinc-400 mt-1">Kill switch auto-engages if breached.</p>
            </div>
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Max total exposure (USD)</label>
              <Input type="number" step="500" value={maxExp} data-testid="max-exposure-input" onChange={(e) => setMaxExp(e.target.value)} className="mt-1 font-mono" />
              <p className="text-xs text-zinc-400 mt-1">Hard cap across all open positions.</p>
            </div>
          </div>
          <div className="flex justify-end">
            <Button onClick={saveLimits} disabled={savingLimits} data-testid="save-limits-btn">
              <Save size={15} /> {savingLimits ? "Saving…" : "Save Limits"}
            </Button>
          </div>
        </div>
      </Card>

      {/* Scheduler */}
      <Card>
        <CardHeader title="Automated Scheduler" subtitle="Runs the strategy every 20 minutes" />
        <div className="px-5 py-5 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-zinc-600">
            <Clock size={16} />
            {state.scheduler_enabled ? "Scheduler is running" : "Scheduler is paused"}
          </div>
          <Toggle checked={state.scheduler_enabled} onChange={toggleScheduler} testid="scheduler-toggle" />
        </div>
      </Card>
    </div>
  );
}
