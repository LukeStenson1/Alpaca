import React, { useState } from "react";
import { History as HistoryIcon, BarChart3 } from "lucide-react";
import TradeHistory from "./TradeHistory";
import Reports from "./Reports";

const TABS = [
  { key: "trades", label: "Trade History", icon: HistoryIcon, Component: TradeHistory },
  { key: "reports", label: "P&L Reports", icon: BarChart3, Component: Reports },
];

export default function History({ initialTab = "trades" }) {
  const [tab, setTab] = useState(initialTab);
  const Active = (TABS.find((t) => t.key === tab) || TABS[0]).Component;

  return (
    <div className="space-y-6" data-testid="history-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-50">History</h1>
        <p className="text-sm text-zinc-500">Every trade and your realized P&amp;L over time.</p>
      </div>
      <div className="flex gap-6 border-b border-zinc-800">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              data-testid={`history-tab-${t.key}`}
              className={`flex items-center gap-2 pb-3 -mb-px text-sm border-b-2 transition-colors ${
                tab === t.key
                  ? "border-klein text-zinc-50 font-medium"
                  : "border-transparent text-zinc-500 hover:text-zinc-300"
              }`}
            >
              <Icon size={15} /> {t.label}
            </button>
          );
        })}
      </div>
      <Active embedded />
    </div>
  );
}
