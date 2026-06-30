import React, { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, History, Settings as SettingsIcon,
  Power, Bell, Activity, ShieldAlert, Telescope,
} from "lucide-react";
import client from "../api";
import { useSystem } from "./SystemContext";
import { useToast } from "./Toast";
import { Badge } from "./ui";

const nav = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, testid: "nav-dashboard" },
  { to: "/research", label: "Research", icon: Telescope, testid: "nav-research" },
  { to: "/settings", label: "Settings", icon: SettingsIcon, testid: "nav-settings" },
  { to: "/history", label: "History", icon: History, testid: "nav-history" },
];

export default function Layout({ children }) {
  const { state, alerts, refresh } = useSystem();
  const toast = useToast();
  const [bellOpen, setBellOpen] = useState(false);

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
    <div className="flex min-h-screen bg-zinc-950 text-zinc-200">
      {/* Sidebar */}
      <aside className="hidden md:flex w-60 flex-col border-r border-zinc-800 bg-zinc-950">
        <div className="flex items-center gap-2.5 px-5 h-16 border-b border-zinc-800">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-klein text-white">
            <Activity size={18} />
          </div>
          <div>
            <div className="text-sm font-bold tracking-tight leading-none text-zinc-50">TERMINAL</div>
            <div className="text-[10px] text-zinc-500 font-mono mt-0.5">conviction trading</div>
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
                  `flex items-center gap-3 px-3 py-2.5 text-sm rounded-lg transition-colors ${
                    isActive
                      ? "bg-zinc-800 text-zinc-50 font-medium"
                      : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                  }`
                }
              >
                <Icon size={17} />
                {n.label}
              </NavLink>
            );
          })}
        </nav>
        <div className="p-3 border-t border-zinc-800">
          <div className="flex items-center justify-between px-1">
            <span className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">Mode</span>
            <Badge tone={mode === "live" ? "danger" : "warn"}>{mode}</Badge>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="sticky top-0 z-40 flex h-16 items-center justify-between gap-3 border-b border-zinc-800 bg-zinc-950/85 backdrop-blur px-4 md:px-6">
          <div className="flex items-center gap-3 min-w-0">
            <span className="md:hidden font-bold text-zinc-50">TERMINAL</span>
            <Badge tone={mode === "live" ? "danger" : "warn"}>{mode} trading</Badge>
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
                className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-zinc-800 text-zinc-300 hover:bg-zinc-800"
              >
                <Bell size={17} />
                {unack > 0 && (
                  <span className="absolute -top-1.5 -right-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-loss px-1 text-[10px] font-bold text-zinc-950">
                    {unack}
                  </span>
                )}
              </button>
              {bellOpen && (
                <div className="absolute right-0 mt-2 w-80 border border-zinc-800 bg-zinc-900 rounded-xl shadow-2xl shadow-black/50 z-50" data-testid="alerts-panel">
                  <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2.5">
                    <span className="text-sm font-semibold text-zinc-50">Alerts</span>
                    <button onClick={ackAll} className="text-xs text-klein hover:underline" data-testid="ack-all-btn">
                      Mark all read
                    </button>
                  </div>
                  <div className="max-h-80 overflow-auto">
                    {alerts.length === 0 ? (
                      <div className="px-4 py-6 text-center text-sm text-zinc-500">No alerts</div>
                    ) : (
                      alerts.map((a) => (
                        <div key={a.id} className={`border-b border-zinc-800 px-4 py-2.5 ${a.acknowledged ? "opacity-50" : ""}`}>
                          <div className="flex items-center gap-2">
                            <Badge tone={a.severity === "critical" ? "danger" : a.severity === "warning" ? "warn" : "default"}>
                              {a.type}
                            </Badge>
                            <span className="text-[10px] text-zinc-500 font-mono">{new Date(a.created_at).toLocaleString()}</span>
                          </div>
                          <p className="mt-1 text-xs text-zinc-300">{a.message}</p>
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
              className={`flex items-center gap-2 px-3.5 h-9 text-sm font-semibold rounded-lg border transition-colors ${
                killed
                  ? "bg-loss text-zinc-950 border-loss hover:bg-rose-300"
                  : "bg-loss/10 text-loss border-loss/30 hover:bg-loss/20"
              }`}
            >
              <Power size={16} />
              {killed ? "HALTED — Release" : "Kill Switch"}
            </button>
          </div>
        </header>

        {/* Halted banner */}
        {killed && (
          <div className="bg-loss/15 border-b border-loss/30 text-loss px-6 py-2 text-sm flex items-center gap-2" data-testid="halted-banner">
            <ShieldAlert size={16} />
            Trading halted — no new orders will be placed.
            {state?.kill_switch_reason ? ` (${state.kill_switch_reason})` : ""}
          </div>
        )}

        <main className="flex-1 p-4 md:p-8 max-w-[1400px] w-full mx-auto">{children}</main>
      </div>
    </div>
  );
}
