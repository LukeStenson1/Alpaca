import React, { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard, ListChecks, History, Lightbulb, Settings as SettingsIcon,
  Power, Bell, Activity, ShieldAlert, BarChart3, Target, Youtube,
} from "lucide-react";
import client from "../api";
import { useSystem } from "./SystemContext";
import { useToast } from "./Toast";
import { Badge } from "./ui";

const nav = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true, testid: "nav-overview" },
  { to: "/watchlist", label: "Watchlist", icon: ListChecks, testid: "nav-watchlist" },
  { to: "/strategy", label: "Strategy", icon: Target, testid: "nav-strategy" },
  { to: "/trades", label: "Trade History", icon: History, testid: "nav-trades" },
  { to: "/suggestions", label: "Suggestions", icon: Lightbulb, testid: "nav-suggestions" },
  { to: "/influencers", label: "Influencer Ideas", icon: Youtube, testid: "nav-influencers" },
  { to: "/reports", label: "P&L Reports", icon: BarChart3, testid: "nav-reports" },
  { to: "/settings", label: "Settings", icon: SettingsIcon, testid: "nav-settings" },
];

export default function Layout({ children }) {
  const { state, alerts, refresh } = useSystem();
  const toast = useToast();
  const [bellOpen, setBellOpen] = useState(false);
  const location = useLocation();

  const killed = state?.kill_switch_engaged;
  const mode = state?.trading_mode || "paper";
  const unack = alerts.filter((a) => !a.acknowledged).length;

  const toggleKill = async () => {
    try {
      await client.post("/system/kill-switch", {
        engaged: !killed,
        reason: !killed ? "Manual halt from dashboard" : null,
      });
      await refresh();
      toast(!killed ? "Kill switch ENGAGED — trading halted" : "Kill switch released", !killed ? "warning" : "success");
    } catch (e) {
      toast("Failed to toggle kill switch", "error");
    }
  };

  const ackAll = async () => {
    try {
      await client.post("/alerts/acknowledge-all");
      await refresh();
    } catch (e) {}
  };

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="hidden md:flex w-60 flex-col border-r border-zinc-200 bg-white">
        <div className="flex items-center gap-2 px-5 h-16 border-b border-zinc-200">
          <div className="flex h-8 w-8 items-center justify-center rounded bg-klein text-white">
            <Activity size={18} />
          </div>
          <div>
            <div className="text-sm font-bold tracking-tight leading-none">TERMINAL</div>
            <div className="text-[10px] text-zinc-500 font-mono mt-0.5">mean-reversion</div>
          </div>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {nav.map((n) => {
            const Icon = n.icon;
            return (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                data-testid={n.testid}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 text-sm rounded-md transition-colors ${
                    isActive
                      ? "bg-zinc-950 text-white font-medium"
                      : "text-zinc-600 hover:bg-zinc-100"
                  }`
                }
              >
                <Icon size={17} />
                {n.label}
              </NavLink>
            );
          })}
        </nav>
        <div className="p-3 border-t border-zinc-200">
          <div className="flex items-center justify-between px-1">
            <span className="text-[11px] uppercase tracking-wide text-zinc-500 font-semibold">Mode</span>
            <Badge tone={mode === "live" ? "danger" : "klein"} testid="sidebar-mode-badge">
              {mode}
            </Badge>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="sticky top-0 z-40 flex h-16 items-center justify-between gap-3 border-b border-zinc-200 bg-white/90 backdrop-blur px-4 md:px-6">
          <div className="flex items-center gap-3 min-w-0">
            <span className="md:hidden font-bold">TERMINAL</span>
            <Badge tone={mode === "live" ? "danger" : "klein"}>{mode} trading</Badge>
            {killed && (
              <Badge tone="danger" className="animate-pulse">
                <ShieldAlert size={12} /> HALTED
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Alerts */}
            <div className="relative">
              <button
                data-testid="alerts-bell"
                onClick={() => setBellOpen((v) => !v)}
                className="relative flex h-9 w-9 items-center justify-center rounded-md border border-zinc-300 hover:bg-zinc-50"
              >
                <Bell size={17} />
                {unack > 0 && (
                  <span className="absolute -top-1.5 -right-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-loss px-1 text-[10px] font-bold text-white">
                    {unack}
                  </span>
                )}
              </button>
              {bellOpen && (
                <div className="absolute right-0 mt-2 w-80 border border-zinc-200 bg-white rounded-md shadow-lg z-50" data-testid="alerts-panel">
                  <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-2.5">
                    <span className="text-sm font-semibold">Alerts</span>
                    <button onClick={ackAll} className="text-xs text-klein hover:underline" data-testid="ack-all-btn">
                      Mark all read
                    </button>
                  </div>
                  <div className="max-h-80 overflow-auto">
                    {alerts.length === 0 ? (
                      <div className="px-4 py-6 text-center text-sm text-zinc-400">No alerts</div>
                    ) : (
                      alerts.map((a) => (
                        <div key={a.id} className={`border-b border-zinc-100 px-4 py-2.5 ${a.acknowledged ? "opacity-50" : ""}`}>
                          <div className="flex items-center gap-2">
                            <Badge tone={a.severity === "critical" ? "danger" : a.severity === "warning" ? "warn" : "default"}>
                              {a.type}
                            </Badge>
                            <span className="text-[10px] text-zinc-400 font-mono">{new Date(a.created_at).toLocaleString()}</span>
                          </div>
                          <p className="mt-1 text-xs text-zinc-700">{a.message}</p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Kill switch */}
            <button
              data-testid="kill-switch"
              onClick={toggleKill}
              className={`flex items-center gap-2 px-3.5 h-9 text-sm font-semibold rounded-md border transition-colors ${
                killed
                  ? "bg-loss text-white border-loss hover:bg-red-700"
                  : "bg-white text-loss border-loss hover:bg-red-50"
              }`}
            >
              <Power size={16} />
              {killed ? "HALTED — Release" : "Kill Switch"}
            </button>
          </div>
        </header>

        {/* Halted banner */}
        {killed && (
          <div className="bg-loss text-white px-6 py-2 text-sm flex items-center gap-2" data-testid="halted-banner">
            <ShieldAlert size={16} />
            Trading halted — no new orders will be placed.
            {state?.kill_switch_reason ? ` (${state.kill_switch_reason})` : ""}
          </div>
        )}

        <main className="flex-1 p-4 md:p-6 max-w-[1400px] w-full mx-auto">{children}</main>
      </div>
    </div>
  );
}
