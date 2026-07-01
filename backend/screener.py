"""Fundamental stock discovery — ranks a curated large-cap universe by FMP quality
and surfaces new ideas (auto-added at low conviction, like YouTube ideas)."""
import logging
from datetime import datetime, timezone

from models import Watchlist, Parameters, InfluencerIdea
import fundamentals as fsvc

logger = logging.getLogger("screener")

# Curated large-cap universe (FMP free plan covers these individually).
UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "AMD", "NFLX",
    "COST", "V", "MA", "JPM", "LLY", "UNH", "HD", "PG", "KO", "PEP",
    "ADBE", "CRM", "ORCL", "QCOM", "TXN", "NKE", "DIS", "MCD", "CAT", "GE",
    "NOW", "INTU", "ISRG", "BKNG", "PANW", "AMAT", "LRCX", "ABBV", "WMT", "TMO",
]

MIN_QUALITY = 60  # only recommend names scoring at/above this


def utcnow():
    return datetime.now(timezone.utc)


def run_screen(db, top_n=6):
    if not fsvc.configured():
        raise RuntimeError("FMP_API_KEY not configured")
    on_watchlist = {w.ticker for w in db.query(Watchlist).all()}
    ranked = []
    for sym in UNIVERSE:
        if sym in on_watchlist:
            continue
        try:
            f = fsvc.get_fundamentals(db, sym)
        except Exception as e:
            logger.warning("screen fetch failed for %s: %s", sym, e)
            continue
        q = fsvc.quality_score(f)
        if q is None:
            continue
        ranked.append((sym, q, f))
    ranked.sort(key=lambda x: x[1], reverse=True)
    picks = [r for r in ranked if r[1] >= MIN_QUALITY][:top_n]

    added = 0
    ideas = []
    for sym, q, f in picks:
        thesis = _thesis(f, q)
        w = db.query(Watchlist).get(sym)
        if not w:
            db.add(Watchlist(ticker=sym, active=True, date_added=utcnow(), conviction=2,
                             thesis=thesis, notes="Auto-added from Fundamental Screener"))
            db.add(Parameters(ticker=sym))
            added += 1
        # dedup idea: one per symbol per day
        vid = f"screen-{sym}-{utcnow().strftime('%Y%m%d')}"
        if not db.query(InfluencerIdea).filter_by(video_id=vid, ticker=sym).first():
            db.add(InfluencerIdea(
                channel_name="Fundamental Screener", video_id=vid,
                video_title=f"Quality screen — {sym}",
                video_url=f"https://finance.yahoo.com/quote/{sym}",
                published_at=utcnow().isoformat(), ticker=sym, company=None,
                signal="bull", conviction=min(5, max(1, round(q / 20))), thesis=thesis,
                action="added" if not w else "advisory", status="pending", created_at=utcnow()))
            ideas.append({"ticker": sym, "quality": q})
    db.commit()
    return {
        "scanned": len([r for r in ranked]),
        "picks": len(picks),
        "watchlist_added": added,
        "ideas": ideas,
        "ranked": [{"ticker": s, "quality": q,
                    "pe_ratio": f.pe_ratio, "revenue_growth": f.revenue_growth,
                    "profit_margin": f.profit_margin} for s, q, f in ranked[:15]],
    }


def _thesis(f, q):
    bits = [f"Quality {q}/100"]
    if f.pe_ratio is not None:
        bits.append(f"P/E {f.pe_ratio:.1f}")
    if f.revenue_growth is not None:
        bits.append(f"rev growth {f.revenue_growth * 100:.0f}%")
    if f.profit_margin is not None:
        bits.append(f"net margin {f.profit_margin * 100:.0f}%")
    return "Fundamental screen: " + ", ".join(bits) + "."
