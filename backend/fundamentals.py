"""Fundamentals via Financial Modeling Prep (FMP) + Conviction x Valuation scoring."""
import os
import logging
from datetime import datetime, timezone, timedelta

import requests

from models import Fundamentals, Watchlist

logger = logging.getLogger("fundamentals")
BASE = "https://financialmodelingprep.com/stable"
CACHE_TTL_HOURS = 24


def utcnow():
    return datetime.now(timezone.utc)


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def configured():
    return bool(os.environ.get("FMP_API_KEY"))


def _key():
    k = os.environ.get("FMP_API_KEY")
    if not k:
        raise RuntimeError("FMP_API_KEY not configured")
    return k


def _get(url):
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_fundamentals(symbol):
    k = _key()
    s = symbol.upper()
    ratios = _get(f"{BASE}/ratios-ttm?symbol={s}&apikey={k}")
    metrics = _get(f"{BASE}/key-metrics-ttm?symbol={s}&apikey={k}")
    growth = _get(f"{BASE}/financial-growth?symbol={s}&limit=1&apikey={k}")
    # A dict response means an FMP error/premium message; a list means data (or [] for ETFs).
    restricted = isinstance(ratios, dict)
    r_list = ratios if isinstance(ratios, list) else []
    g_list = growth if isinstance(growth, list) else []
    m_list = metrics if isinstance(metrics, list) else []
    dr = r_list[0] if r_list else {}
    dg = g_list[0] if g_list else {}
    dm = m_list[0] if m_list else {}
    out = {
        "pe_ratio": dr.get("priceToEarningsRatioTTM"),
        "profit_margin": dr.get("netProfitMarginTTM"),
        "operating_margin": dr.get("operatingProfitMarginTTM"),
        "revenue_growth": dg.get("revenueGrowth"),
        "earnings_growth": dg.get("epsgrowth"),
        "market_cap": dm.get("marketCap"),
        "is_etf": (not restricted) and (not r_list) and (not g_list),
    }
    if restricted:
        out["error"] = "Not available on current FMP plan"
    return out


def get_fundamentals(db, symbol, force=False):
    s = symbol.upper()
    row = db.query(Fundamentals).get(s)
    fresh = row and row.fetched_at and (utcnow() - _aware(row.fetched_at) < timedelta(hours=CACHE_TTL_HOURS))
    if row and fresh and not force:
        return row
    err = None
    try:
        data = fetch_fundamentals(s)
        err = data.pop("error", None)
    except Exception as e:
        logger.warning("FMP fetch failed for %s: %s", s, e)
        if row:
            return row
        data = {"is_etf": False}
        err = str(e)[:200]
    if not row:
        row = Fundamentals(symbol=s)
        db.add(row)
    for key, val in data.items():
        setattr(row, key, val)
    row.error = err
    row.fetched_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def refresh_all(db):
    tickers = [w.ticker for w in db.query(Watchlist).filter(Watchlist.active == True).all()]  # noqa: E712
    n = 0
    for t in tickers:
        try:
            get_fundamentals(db, t, force=True)
            n += 1
        except Exception as e:
            logger.warning("refresh failed for %s: %s", t, e)
    return n


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def quality_score(f):
    """0-100 fundamentals quality/valuation score, or None if not enough data (e.g. ETF)."""
    if not f or f.is_etf:
        return None
    parts = []
    if f.pe_ratio is not None and f.pe_ratio > 0:
        parts.append((_clamp(1.0 - max(0.0, f.pe_ratio - 20) / 60.0), 0.30))
    elif f.pe_ratio is not None:  # negative earnings
        parts.append((0.15, 0.30))
    if f.revenue_growth is not None:
        parts.append((_clamp(f.revenue_growth / 0.25), 0.25))
    if f.earnings_growth is not None:
        parts.append((_clamp(f.earnings_growth / 0.25), 0.20))
    if f.profit_margin is not None:
        parts.append((_clamp(f.profit_margin / 0.25), 0.25))
    if not parts:
        return None
    total_w = sum(w for _, w in parts)
    return round(100 * sum(v * w for v, w in parts) / total_w)


def build_shortlist(db):
    items = db.query(Watchlist).filter(Watchlist.active == True).all()  # noqa: E712
    out = []
    for w in items:
        f = db.query(Fundamentals).get(w.ticker)
        q = quality_score(f)
        conv = w.conviction or 3
        conv_norm = conv / 5.0
        if q is not None:
            blended = round(100 * (0.55 * conv_norm + 0.45 * (q / 100.0)))
        else:
            blended = round(100 * conv_norm * 0.7)  # discount unknown fundamentals
        out.append({
            "ticker": w.ticker,
            "name": w.name,
            "conviction": conv,
            "pe_ratio": f.pe_ratio if f else None,
            "revenue_growth": f.revenue_growth if f else None,
            "profit_margin": f.profit_margin if f else None,
            "market_cap": f.market_cap if f else None,
            "is_etf": bool(f.is_etf) if f else False,
            "quality_score": q,
            "blended_score": blended,
            "has_fundamentals": q is not None,
        })
    out.sort(key=lambda x: x["blended_score"], reverse=True)
    return out
