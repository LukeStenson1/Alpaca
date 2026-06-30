import React, { useState } from "react";
import { ListChecks, Youtube, Lightbulb } from "lucide-react";
import Watchlist from "./Watchlist";
import Influencers from "./Influencers";
import Suggestions from "./Suggestions";

const TABS = [
  { key: "watchlist", label: "Watchlist", icon: ListChecks, Component: Watchlist },
  { key: "influencers", label: "Influencer Ideas", icon: Youtube, Component: Influencers },
  { key: "suggestions", label: "Tuning Suggestions", icon: Lightbulb, Component: Suggestions },
];

export default function Research({ initialTab = "watchlist" }) {
  const [tab, setTab] = useState(initialTab);
  const Active = (TABS.find((t) => t.key === tab) || TABS[0]).Component;

  return (
    <div className="space-y-6" data-testid="research-page">
      <div className="flex gap-1 border-b border-zinc-200">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              data-testid={`research-tab-${t.key}`}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm border-b-2 -mb-px transition-colors ${
                tab === t.key
                  ? "border-klein text-klein font-medium"
                  : "border-transparent text-zinc-500 hover:text-zinc-800"
              }`}
            >
              <Icon size={15} /> {t.label}
            </button>
          );
        })}
      </div>
      <Active />
    </div>
  );
}
