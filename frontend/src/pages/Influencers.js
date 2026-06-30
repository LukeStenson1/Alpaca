import React, { useEffect, useState, useCallback } from "react";
import { Youtube, RefreshCw, Trash2, Plus, X, ExternalLink, TrendingUp, TrendingDown, Minus, Star } from "lucide-react";
import client, { fmtDate } from "../api";
import { Card, CardHeader, Button, Input, Badge, Spinner, EmptyState, Toggle } from "../components/ui";
import { useToast } from "../components/Toast";

const signalMeta = {
  bull: { tone: "success", icon: TrendingUp, label: "Bullish" },
  bear: { tone: "danger", icon: TrendingDown, label: "Bearish" },
  neutral: { tone: "muted", icon: Minus, label: "Neutral" },
};
const actionTone = { added: "klein", updated: "success", advisory: "muted" };

export default function Influencers() {
  const toast = useToast();
  const [channels, setChannels] = useState([]);
  const [ideas, setIdeas] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [newQuery, setNewQuery] = useState("");
  const [tab, setTab] = useState("pending");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ch, st] = await Promise.all([
        client.get("/influencers/channels"),
        client.get("/influencers/status"),
      ]);
      setChannels(ch.data);
      setStatus(st.data);
    } catch (e) {
      toast("Failed to load influencer data", "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const loadIdeas = useCallback(async () => {
    try {
      const params = tab === "all" ? {} : { status: tab };
      const res = await client.get("/influencers/ideas", { params });
      setIdeas(res.data);
    } catch (e) {
      toast("Failed to load ideas", "error");
    }
  }, [tab, toast]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadIdeas(); }, [loadIdeas]);

  const addChannel = async () => {
    if (!newQuery.trim()) return;
    try {
      await client.post("/influencers/channels", { query: newQuery.trim() });
      setNewQuery("");
      toast("Channel added", "success");
      load();
    } catch (e) {
      toast(e.response?.data?.detail || "Failed to add channel", "error");
    }
  };

  const removeChannel = async (id) => {
    try {
      await client.delete(`/influencers/channels/${id}`);
      load();
    } catch (e) {
      toast("Failed to remove channel", "error");
    }
  };

  const toggleChannel = async (id) => {
    try {
      await client.post(`/influencers/channels/${id}/toggle`);
      load();
    } catch (e) {
      toast("Failed to toggle channel", "error");
    }
  };

  const scan = async () => {
    setScanning(true);
    try {
      const res = await client.post("/influencers/scan");
      const d = res.data;
      toast(
        `Scanned ${d.scanned_videos} videos — ${d.ideas_created} ideas, ${d.watchlist_added} added, ${d.watchlist_updated} updated`,
        "success"
      );
      load();
      loadIdeas();
    } catch (e) {
      toast(e.response?.data?.detail || "Scan failed", "error");
    } finally {
      setScanning(false);
    }
  };

  const dismiss = async (id) => {
    try {
      await client.post(`/influencers/ideas/${id}/dismiss`);
      loadIdeas();
    } catch (e) {
      toast("Failed to dismiss", "error");
    }
  };

  const configured = status?.configured;

  return (
    <div className="space-y-6" data-testid="influencers-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Youtube size={22} className="text-loss" /> Influencer Ideas
          </h1>
          <p className="text-sm text-zinc-500">
            AI reads recent videos from your chosen YouTubers and extracts stock ideas. Bullish, tradable
            picks are auto-added to your watchlist at low conviction; repeat mentions raise conviction.
          </p>
        </div>
        <Button onClick={scan} disabled={scanning || !configured} data-testid="scan-influencers-btn">
          <RefreshCw size={15} className={scanning ? "animate-spin" : ""} />
          {scanning ? "Scanning…" : "Scan Now"}
        </Button>
      </div>

      {status && !configured && (
        <Card className="border-warn" data-testid="influencer-config-warning">
          <div className="px-5 py-4 text-sm text-zinc-700">
            <span className="font-semibold text-warn">YouTube API key required.</span>{" "}
            Add your <span className="font-mono">YOUTUBE_API_KEY</span> to enable scanning.
            {" "}LLM key: {status.llm_key ? "✓ configured" : "✗ missing"}.
          </div>
        </Card>
      )}

      {/* Channels */}
      <Card>
        <CardHeader title="Tracked Channels" subtitle="Add a YouTube handle (e.g. @FinancialEducation) or a channel name" />
        <div className="px-5 py-4 space-y-4">
          <div className="flex gap-2">
            <Input
              placeholder="@handle or channel name"
              value={newQuery}
              data-testid="channel-query-input"
              onChange={(e) => setNewQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addChannel()}
            />
            <Button onClick={addChannel} data-testid="add-channel-btn"><Plus size={15} /> Add</Button>
          </div>
          {loading ? (
            <Spinner />
          ) : channels.length === 0 ? (
            <p className="text-sm text-zinc-400">No channels yet.</p>
          ) : (
            <div className="space-y-2">
              {channels.map((c) => (
                <div key={c.id} className="flex items-center justify-between border border-zinc-200 rounded-md px-4 py-2.5" data-testid={`channel-${c.id}`}>
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{c.name}</div>
                    <div className="text-[11px] text-zinc-400 font-mono truncate">
                      {c.channel_id ? `id:${c.channel_id}` : `query: ${c.query}`}
                      {c.last_scanned_at ? ` · scanned ${fmtDate(c.last_scanned_at)}` : " · not yet scanned"}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <Toggle checked={c.active} onChange={() => toggleChannel(c.id)} testid={`toggle-channel-${c.id}`} />
                    <button onClick={() => removeChannel(c.id)} data-testid={`delete-channel-${c.id}`} className="text-zinc-400 hover:text-loss">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      {/* Ideas */}
      <div className="flex gap-1 border-b border-zinc-200">
        {["pending", "dismissed", "all"].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            data-testid={`ideas-tab-${t}`}
            className={`px-4 py-2 text-sm capitalize border-b-2 -mb-px transition-colors ${
              tab === t ? "border-klein text-klein font-medium" : "border-transparent text-zinc-500 hover:text-zinc-800"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {ideas.length === 0 ? (
        <Card>
          <EmptyState
            title="No ideas yet"
            hint="Click 'Scan Now' to fetch recent videos and extract stock ideas with AI."
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {ideas.map((i) => {
            const sm = signalMeta[i.signal] || signalMeta.neutral;
            const SignalIcon = sm.icon;
            return (
              <Card key={i.id} data-testid={`idea-${i.id}`}>
                <div className="flex items-start justify-between px-5 py-3.5 border-b border-zinc-200">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono font-bold text-lg">{i.ticker}</span>
                    <Badge tone={sm.tone}><SignalIcon size={11} /> {sm.label}</Badge>
                    <Badge tone={actionTone[i.action] || "muted"}>{i.action}</Badge>
                  </div>
                  <div className="flex items-center gap-0.5">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <Star key={n} size={13} className={n <= i.conviction ? "fill-warn text-warn" : "text-zinc-300"} />
                    ))}
                  </div>
                </div>
                <div className="px-5 py-4 space-y-3">
                  {i.company && <div className="text-sm font-medium text-zinc-700">{i.company}</div>}
                  <p className="text-sm text-zinc-600 leading-relaxed">{i.thesis || "No thesis extracted."}</p>
                  <div className="flex items-center justify-between text-[11px] text-zinc-400">
                    <span className="truncate max-w-[60%]">{i.channel_name}</span>
                    <a href={i.video_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-klein hover:underline shrink-0" data-testid={`idea-video-link-${i.id}`}>
                      <ExternalLink size={12} /> Watch
                    </a>
                  </div>
                  {i.status === "pending" && (
                    <div className="pt-1">
                      <Button variant="outline" onClick={() => dismiss(i.id)} data-testid={`dismiss-idea-btn-${i.id}`}>
                        <X size={15} /> Dismiss
                      </Button>
                    </div>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
