import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import Base, engine, get_db, SessionLocal
from models import (
    Watchlist, Parameters, Trade, PositionState, Suggestion,
    AccountSnapshot, Alert, SystemState,
)
from alpaca_service import get_service
import strategy
import suggestions
import scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

app = FastAPI(title="Mean-Reversion Trading Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def utcnow():
    return datetime.now(timezone.utc)


def _migrate():
    """Lightweight additive SQLite migration for new columns."""
    add_cols = {
        "position_states": [("realized_pnl", "FLOAT DEFAULT 0.0"), ("closed_at", "DATETIME"),
                            ("entry_order_id", "VARCHAR")],
        "trades": [("realized_pnl", "FLOAT")],
        "parameters": [
            ("stop_loss_pct", "FLOAT DEFAULT 0.0"), ("max_hold_days", "INTEGER"),
            ("use_volatility_sizing", "BOOLEAN DEFAULT 0"), ("use_52w_range", "BOOLEAN DEFAULT 0"),
            ("range_pct", "FLOAT DEFAULT 0.15"), ("allow_downtrend_buys", "BOOLEAN DEFAULT 0"),
            ("cooldown_days", "INTEGER DEFAULT 7"),
        ],
        "watchlist": [("sector", "VARCHAR"), ("name", "VARCHAR")],
        "system_state": [
            ("schedule_frequency", "VARCHAR DEFAULT 'daily'"),
            ("schedule_timing", "VARCHAR DEFAULT 'before_open'"),
            ("baseline_volatility", "FLOAT DEFAULT 0.02"),
            ("benchmark_ticker", "VARCHAR DEFAULT 'SPY'"),
            ("rebalance_threshold_pct", "FLOAT DEFAULT 0.20"),
        ],
    }
    with engine.connect() as conn:
        for table, cols in add_cols.items():
            try:
                existing = [r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()]
            except Exception:
                continue
            for name, ddl in cols:
                if name not in existing:
                    try:
                        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                    except Exception:
                        pass
        conn.commit()


# ---------------- Pydantic schemas ----------------
class WatchlistCreate(BaseModel):
    ticker: str
    notes: Optional[str] = None


class WatchlistUpdate(BaseModel):
    active: Optional[bool] = None
    notes: Optional[str] = None
    sector: Optional[str] = None


class ParametersUpdate(BaseModel):
    buy_threshold_stddev: Optional[float] = None
    lookback_days: Optional[int] = None
    sell_tranche_pct: Optional[float] = None
    sell_gain_steps: Optional[List[float]] = None
    max_position_size_usd: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    max_hold_days: Optional[int] = None
    use_volatility_sizing: Optional[bool] = None
    use_52w_range: Optional[bool] = None
    range_pct: Optional[float] = None
    allow_downtrend_buys: Optional[bool] = None
    cooldown_days: Optional[int] = None


class KillSwitchBody(BaseModel):
    engaged: bool
    reason: Optional[str] = None


class ModeBody(BaseModel):
    mode: str  # paper / live
    confirmation: Optional[str] = None


class SafetyLimitsBody(BaseModel):
    max_daily_loss_usd: Optional[float] = None
    max_total_exposure_usd: Optional[float] = None
    scheduler_enabled: Optional[bool] = None
    schedule_frequency: Optional[str] = None
    baseline_volatility: Optional[float] = None
    benchmark_ticker: Optional[str] = None
    rebalance_threshold_pct: Optional[float] = None


# ---------------- startup ----------------
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    _migrate()
    db = SessionLocal()
    try:
        state = db.query(SystemState).get(1)
        if not state:
            db.add(SystemState(id=1))
            db.commit()
        # seed a starter watchlist if empty
        if db.query(Watchlist).count() == 0:
            for tk in ["AAPL", "MSFT", "SPY"]:
                db.add(Watchlist(ticker=tk, active=True, date_added=utcnow()))
                db.add(Parameters(ticker=tk))
            db.commit()
        # backfill missing company names (one-time, few tickers)
        try:
            svc = get_service(db.query(SystemState).get(1).trading_mode)
            for w in db.query(Watchlist).filter(Watchlist.name.is_(None)).all():
                try:
                    w.name = svc.get_asset(w.ticker)["name"]
                except Exception:
                    pass
            db.commit()
        except Exception:
            pass
    finally:
        db.close()
    scheduler.start_scheduler()


# ---------------- helpers ----------------
def get_state(db):
    state = db.query(SystemState).get(1)
    if not state:
        state = SystemState(id=1)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def state_dict(s: SystemState):
    return {
        "kill_switch_engaged": s.kill_switch_engaged,
        "kill_switch_reason": s.kill_switch_reason,
        "trading_mode": s.trading_mode,
        "max_daily_loss_usd": s.max_daily_loss_usd,
        "max_total_exposure_usd": s.max_total_exposure_usd,
        "day_start_equity": s.day_start_equity,
        "scheduler_enabled": s.scheduler_enabled,
        "schedule_frequency": s.schedule_frequency,
        "schedule_timing": s.schedule_timing,
        "baseline_volatility": s.baseline_volatility,
        "benchmark_ticker": s.benchmark_ticker,
        "rebalance_threshold_pct": s.rebalance_threshold_pct,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


# ---------------- system / settings ----------------
@app.get("/api/system/state")
def system_state(db: Session = Depends(get_db)):
    s = get_state(db)
    unack = db.query(Alert).filter(Alert.acknowledged == False).count()  # noqa: E712
    d = state_dict(s)
    d["unacknowledged_alerts"] = unack
    return d


@app.post("/api/system/kill-switch")
def set_kill_switch(body: KillSwitchBody, db: Session = Depends(get_db)):
    s = get_state(db)
    s.kill_switch_engaged = body.engaged
    s.kill_switch_reason = body.reason if body.engaged else None
    db.commit()
    strategy.log_alert(
        db, "kill_switch",
        f"Kill switch manually {'ENGAGED' if body.engaged else 'RELEASED'}"
        + (f": {body.reason}" if body.reason else ""),
        "critical" if body.engaged else "info",
    )
    return state_dict(get_state(db))


@app.post("/api/system/mode")
def set_mode(body: ModeBody, db: Session = Depends(get_db)):
    mode = body.mode.lower()
    if mode not in ("paper", "live"):
        raise HTTPException(400, "mode must be 'paper' or 'live'")
    s = get_state(db)
    if mode == "live" and (body.confirmation or "").strip() != "CONFIRM LIVE":
        raise HTTPException(400, "Live mode requires typing exactly: CONFIRM LIVE")
    prev = s.trading_mode
    s.trading_mode = mode
    db.commit()
    if prev != mode:
        strategy.log_alert(db, "mode_switch",
                           f"Trading mode switched from {prev.upper()} to {mode.upper()}",
                           "warning")
    return state_dict(get_state(db))


@app.put("/api/system/safety-limits")
def set_safety(body: SafetyLimitsBody, db: Session = Depends(get_db)):
    s = get_state(db)
    if body.max_daily_loss_usd is not None:
        s.max_daily_loss_usd = body.max_daily_loss_usd
    if body.max_total_exposure_usd is not None:
        s.max_total_exposure_usd = body.max_total_exposure_usd
    if body.scheduler_enabled is not None:
        s.scheduler_enabled = body.scheduler_enabled
    if body.schedule_frequency is not None:
        freq = body.schedule_frequency.lower()
        if freq not in ("daily", "weekly"):
            raise HTTPException(400, "schedule_frequency must be 'daily' or 'weekly'")
        s.schedule_frequency = freq
        scheduler.reschedule_strategy(freq)
    if body.baseline_volatility is not None:
        s.baseline_volatility = body.baseline_volatility
    if body.benchmark_ticker is not None:
        s.benchmark_ticker = body.benchmark_ticker.strip().upper()
    if body.rebalance_threshold_pct is not None:
        s.rebalance_threshold_pct = body.rebalance_threshold_pct
    db.commit()
    return state_dict(get_state(db))


# ---------------- account / overview ----------------
@app.get("/api/account")
def account(db: Session = Depends(get_db)):
    s = get_state(db)
    svc = get_service(s.trading_mode)
    try:
        a = svc.get_account()
        clock = None
        try:
            clock = svc.get_clock()
        except Exception:
            pass
        return {
            "connected": True,
            "mode": s.trading_mode,
            "equity": a["equity"],
            "cash": a["cash"],
            "buying_power": a["buying_power"],
            "portfolio_value": a["portfolio_value"],
            "today_pl": a["equity"] - a["last_equity"],
            "today_pl_pct": ((a["equity"] - a["last_equity"]) / a["last_equity"] * 100)
            if a["last_equity"] else 0,
            "status": a["status"],
            "market_open": clock["is_open"] if clock else None,
        }
    except Exception as e:
        logger.warning("account fetch failed: %s", e)
        return {"connected": False, "mode": s.trading_mode, "error": str(e)}


@app.get("/api/positions")
def positions(db: Session = Depends(get_db)):
    s = get_state(db)
    svc = get_service(s.trading_mode)
    try:
        return {"connected": True, "positions": svc.get_positions()}
    except Exception as e:
        return {"connected": False, "positions": [], "error": str(e)}


@app.get("/api/account/snapshots")
def snapshots(limit: int = 200, db: Session = Depends(get_db)):
    rows = (
        db.query(AccountSnapshot)
        .order_by(desc(AccountSnapshot.timestamp))
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))
    return [
        {"timestamp": r.timestamp.isoformat(), "equity": r.equity,
         "cash": r.cash, "buying_power": r.buying_power}
        for r in rows
    ]


@app.get("/api/positions/closed")
def closed_positions(db: Session = Depends(get_db)):
    rows = (
        db.query(PositionState)
        .filter(PositionState.status == "closed")
        .order_by(desc(PositionState.closed_at))
        .all()
    )
    return [
        {
            "ticker": p.ticker,
            "original_qty": p.original_qty,
            "avg_entry_price": p.avg_entry_price,
            "realized_pnl": p.realized_pnl or 0.0,
            "tranches_executed": p.tranches_executed,
            "opened_at": p.opened_at.isoformat() if p.opened_at else None,
            "closed_at": p.closed_at.isoformat() if p.closed_at else None,
        }
        for p in rows
    ]


@app.get("/api/pnl/summary")
def pnl_summary(db: Session = Depends(get_db)):
    states = db.query(PositionState).all()
    realized_total = sum((s.realized_pnl or 0.0) for s in states)
    closed = [s for s in states if s.status == "closed"]
    open_with_realized = [s for s in states if s.status == "open" and (s.realized_pnl or 0) != 0]
    return {
        "realized_total": round(realized_total, 2),
        "closed_count": len(closed),
        "open_partial_count": len(open_with_realized),
    }


# ---------------- portfolio-level features ----------------
@app.get("/api/portfolio/flags")
def portfolio_flags(db: Session = Depends(get_db)):
    """Informational review flags: staleness (max_hold_days) + concentration/rebalance."""
    s = get_state(db)
    svc = get_service(s.trading_mode)
    flags = []
    try:
        positions = [p for p in svc.get_positions() if p["market_value"] >= 1.0]
    except Exception as e:
        return {"flags": [], "error": str(e)}
    total = sum(p["market_value"] for p in positions) or 0.0

    # concentration / rebalance flags
    for p in positions:
        share = (p["market_value"] / total) if total else 0
        if share >= s.rebalance_threshold_pct:
            flags.append({
                "type": "rebalance", "ticker": p["ticker"],
                "message": f"{p['ticker']} is {share*100:.0f}% of portfolio "
                           f"(threshold {s.rebalance_threshold_pct*100:.0f}%) — review for rebalance.",
            })

    # staleness flags
    open_states = db.query(PositionState).filter(PositionState.status == "open").all()
    pos_tickers = {p["ticker"] for p in positions}
    for ps in open_states:
        params = db.query(Parameters).get(ps.ticker)
        if not params or not params.max_hold_days or ps.ticker not in pos_tickers:
            continue
        if ps.opened_at:
            opened = ps.opened_at if ps.opened_at.tzinfo else ps.opened_at.replace(tzinfo=timezone.utc)
            held = (utcnow() - opened).days
            if held > params.max_hold_days:
                flags.append({
                    "type": "staleness", "ticker": ps.ticker,
                    "message": f"Review: {ps.ticker} held {held} days "
                               f"(> {params.max_hold_days}d) with no exit triggered.",
                })
    return {"flags": flags, "total_value": round(total, 2)}


@app.get("/api/portfolio/sectors")
def portfolio_sectors(db: Session = Depends(get_db)):
    s = get_state(db)
    svc = get_service(s.trading_mode)
    try:
        positions = [p for p in svc.get_positions() if p["market_value"] >= 1.0]
    except Exception as e:
        return {"sectors": [], "error": str(e)}
    sector_map = {w.ticker: (w.sector or "Unclassified") for w in db.query(Watchlist).all()}
    agg = {}
    total = 0.0
    for p in positions:
        sec = sector_map.get(p["ticker"], "Unclassified")
        agg[sec] = agg.get(sec, 0.0) + p["market_value"]
        total += p["market_value"]
    out = [{"sector": k, "value": round(v, 2), "pct": round((v / total * 100) if total else 0, 1)}
           for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]
    return {"sectors": out, "total_value": round(total, 2)}


@app.get("/api/portfolio/benchmark")
def portfolio_benchmark(db: Session = Depends(get_db)):
    """Portfolio equity vs benchmark, both indexed to 100 at the first snapshot."""
    s = get_state(db)
    svc = get_service(s.trading_mode)
    snaps = db.query(AccountSnapshot).order_by(AccountSnapshot.timestamp.asc()).all()
    if len(snaps) < 2:
        return {"benchmark_ticker": s.benchmark_ticker, "series": [], "note": "need more history"}
    base_eq = snaps[0].equity or 1
    # benchmark daily closes aligned by date
    bench_by_date = {}
    try:
        bars = svc.get_daily_bars(s.benchmark_ticker, 260)
        # map not date-aware (bars lack date here); fall back to indexing by order
        bench_closes = [b["close"] for b in bars]
    except Exception:
        bench_closes = []
    series = []
    for i, snap in enumerate(snaps):
        point = {
            "timestamp": snap.timestamp.isoformat(),
            "portfolio": round((snap.equity / base_eq) * 100, 2),
        }
        series.append(point)
    # overlay benchmark indexed to 100 across the same number of points (tail-aligned)
    if bench_closes:
        n = len(series)
        tail = bench_closes[-n:] if len(bench_closes) >= n else bench_closes
        if tail:
            b0 = tail[0]
            for i, point in enumerate(series):
                if i < len(tail):
                    point["benchmark"] = round((tail[i] / b0) * 100, 2)
    return {"benchmark_ticker": s.benchmark_ticker, "series": series}


# ---------------- reporting: monthly/quarterly P&L rollup ----------------
@app.get("/api/reports/pnl")
def reports_pnl(period: str = "month", db: Session = Depends(get_db)):
    s = get_state(db)
    svc = get_service(s.trading_mode)
    sells = db.query(Trade).filter(Trade.side == "sell").all()
    buckets = {}
    for t in sells:
        if not t.timestamp:
            continue
        if period == "quarter":
            q = (t.timestamp.month - 1) // 3 + 1
            key = f"{t.timestamp.year}-Q{q}"
        else:
            key = t.timestamp.strftime("%Y-%m")
        b = buckets.setdefault(key, {"period": key, "realized_pnl": 0.0, "trade_count": 0})
        b["realized_pnl"] += (t.realized_pnl or 0.0)
        b["trade_count"] += 1
    rows = sorted(buckets.values(), key=lambda r: r["period"], reverse=True)
    for r in rows:
        r["realized_pnl"] = round(r["realized_pnl"], 2)
    # current unrealized (point-in-time)
    unrealized = 0.0
    try:
        unrealized = round(sum(p["unrealized_pl"] for p in svc.get_positions()), 2)
    except Exception:
        pass
    return {"period": period, "rows": rows,
            "realized_total": round(sum(r["realized_pnl"] for r in rows), 2),
            "current_unrealized": unrealized}


# ---------------- watchlist + parameters ----------------
def params_dict(p: Parameters):
    return {
        "ticker": p.ticker,
        "buy_threshold_stddev": p.buy_threshold_stddev,
        "lookback_days": p.lookback_days,
        "sell_tranche_pct": p.sell_tranche_pct,
        "sell_gain_steps": p.sell_gain_steps,
        "max_position_size_usd": p.max_position_size_usd,
        "stop_loss_pct": p.stop_loss_pct,
        "max_hold_days": p.max_hold_days,
        "use_volatility_sizing": p.use_volatility_sizing,
        "use_52w_range": p.use_52w_range,
        "range_pct": p.range_pct,
        "allow_downtrend_buys": p.allow_downtrend_buys,
        "cooldown_days": p.cooldown_days,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@app.get("/api/watchlist")
def list_watchlist(db: Session = Depends(get_db)):
    out = []
    for w in db.query(Watchlist).order_by(Watchlist.ticker).all():
        p = db.query(Parameters).get(w.ticker)
        out.append({
            "ticker": w.ticker,
            "name": w.name,
            "date_added": w.date_added.isoformat() if w.date_added else None,
            "active": w.active,
            "notes": w.notes,
            "sector": w.sector,
            "parameters": params_dict(p) if p else None,
        })
    return out


@app.get("/api/watchlist/validate")
def validate_ticker(ticker: str, db: Session = Depends(get_db)):
    tk = (ticker or "").strip().upper()
    if not tk:
        return {"valid": False, "message": "Enter a ticker symbol."}
    if db.query(Watchlist).get(tk):
        return {"valid": False, "message": f"{tk} is already in your watchlist."}
    s = get_state(db)
    svc = get_service(s.trading_mode)
    try:
        asset = svc.get_asset(tk)
    except Exception:
        return {"valid": False, "message": f"'{tk}' is not a recognized symbol on Alpaca."}
    if not asset["tradable"]:
        return {"valid": False, "message": f"'{tk}' exists but isn't tradable on Alpaca."}
    return {"valid": True, "name": asset["name"], "exchange": asset["exchange"],
            "message": f"{tk} — {asset['name']}"}


@app.post("/api/watchlist")
def add_watchlist(body: WatchlistCreate, db: Session = Depends(get_db)):
    tk = body.ticker.strip().upper()
    if not tk:
        raise HTTPException(400, "ticker required")
    if db.query(Watchlist).get(tk):
        raise HTTPException(400, f"{tk} already in watchlist")
    s = get_state(db)
    svc = get_service(s.trading_mode)
    try:
        asset = svc.get_asset(tk)
    except Exception:
        raise HTTPException(400, f"'{tk}' is not a recognized symbol on Alpaca. Please check the spelling.")
    if not asset["tradable"]:
        raise HTTPException(400, f"'{tk}' exists but is not tradable on Alpaca.")
    db.add(Watchlist(ticker=tk, name=asset["name"], notes=body.notes, active=True, date_added=utcnow()))
    db.add(Parameters(ticker=tk))
    db.commit()
    return {"ticker": tk, "name": asset["name"], "status": "added"}


@app.put("/api/watchlist/{ticker}")
def update_watchlist(ticker: str, body: WatchlistUpdate, db: Session = Depends(get_db)):
    w = db.query(Watchlist).get(ticker.upper())
    if not w:
        raise HTTPException(404, "ticker not found")
    if body.active is not None:
        w.active = body.active
    if body.notes is not None:
        w.notes = body.notes
    if body.sector is not None:
        w.sector = body.sector.strip() or None
    db.commit()
    return {"ticker": w.ticker, "active": w.active, "notes": w.notes, "sector": w.sector}


@app.delete("/api/watchlist/{ticker}")
def delete_watchlist(ticker: str, db: Session = Depends(get_db)):
    tk = ticker.upper()
    w = db.query(Watchlist).get(tk)
    if not w:
        raise HTTPException(404, "ticker not found")
    db.query(Parameters).filter(Parameters.ticker == tk).delete()
    db.query(PositionState).filter(PositionState.ticker == tk).delete()
    db.delete(w)
    db.commit()
    return {"ticker": tk, "status": "deleted"}


@app.put("/api/parameters/{ticker}")
def update_parameters(ticker: str, body: ParametersUpdate, db: Session = Depends(get_db)):
    tk = ticker.upper()
    p = db.query(Parameters).get(tk)
    if not p:
        raise HTTPException(404, "parameters not found")
    data = body.model_dump(exclude_unset=True)
    if "sell_gain_steps" in data and data["sell_gain_steps"] is not None:
        data["sell_gain_steps"] = sorted([float(x) for x in data["sell_gain_steps"]])
    for k, v in data.items():
        setattr(p, k, v)
    p.updated_at = utcnow()
    db.commit()
    return params_dict(p)


# ---------------- trades ----------------
@app.get("/api/trades")
def list_trades(
    ticker: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Trade)
    if ticker:
        q = q.filter(Trade.ticker == ticker.upper())
    if start:
        q = q.filter(Trade.timestamp >= datetime.fromisoformat(start))
    if end:
        q = q.filter(Trade.timestamp <= datetime.fromisoformat(end))
    rows = q.order_by(desc(Trade.timestamp)).limit(500).all()
    return [
        {
            "id": t.id, "ticker": t.ticker, "side": t.side,
            "quantity": t.quantity, "price": t.price,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
            "order_id": t.order_id, "trigger_reason": t.trigger_reason,
            "params_snapshot": t.params_snapshot,
            "realized_pnl": t.realized_pnl,
        }
        for t in rows
    ]


# ---------------- suggestions ----------------
@app.get("/api/suggestions")
def list_suggestions(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Suggestion)
    if status:
        q = q.filter(Suggestion.status == status)
    rows = q.order_by(desc(Suggestion.created_at)).all()
    return [
        {
            "id": s.id, "ticker": s.ticker, "suggested_param": s.suggested_param,
            "current_value": s.current_value, "suggested_value": s.suggested_value,
            "rationale": s.rationale, "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in rows
    ]


@app.post("/api/suggestions/generate")
def generate_suggestions(db: Session = Depends(get_db)):
    n = suggestions.generate_all(db)
    return {"created": n}


@app.post("/api/suggestions/{sid}/approve")
def approve_suggestion(sid: int, db: Session = Depends(get_db)):
    s = db.query(Suggestion).get(sid)
    if not s:
        raise HTTPException(404, "suggestion not found")
    if s.status != "pending":
        raise HTTPException(400, "suggestion already resolved")
    ok = suggestions.apply_suggestion(db, s)
    if not ok:
        raise HTTPException(400, "could not apply suggestion")
    s.status = "approved"
    db.commit()
    return {"id": s.id, "status": "approved"}


@app.post("/api/suggestions/{sid}/reject")
def reject_suggestion(sid: int, db: Session = Depends(get_db)):
    s = db.query(Suggestion).get(sid)
    if not s:
        raise HTTPException(404, "suggestion not found")
    s.status = "rejected"
    db.commit()
    return {"id": s.id, "status": "rejected"}


# ---------------- strategy ----------------
@app.post("/api/strategy/run")
def run_strategy_now(db: Session = Depends(get_db)):
    return strategy.run_strategy(db, manual=True)


# ---------------- alerts ----------------
@app.get("/api/alerts")
def list_alerts(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(Alert).order_by(desc(Alert.created_at)).limit(limit).all()
    return [
        {
            "id": a.id, "type": a.type, "severity": a.severity,
            "message": a.message,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "acknowledged": a.acknowledged,
        }
        for a in rows
    ]


@app.post("/api/alerts/{aid}/acknowledge")
def ack_alert(aid: int, db: Session = Depends(get_db)):
    a = db.query(Alert).get(aid)
    if not a:
        raise HTTPException(404, "alert not found")
    a.acknowledged = True
    db.commit()
    return {"id": a.id, "acknowledged": True}


@app.post("/api/alerts/acknowledge-all")
def ack_all(db: Session = Depends(get_db)):
    db.query(Alert).filter(Alert.acknowledged == False).update({"acknowledged": True})  # noqa: E712
    db.commit()
    return {"status": "ok"}


@app.get("/api/")
def root():
    return {"status": "ok", "service": "trading-dashboard"}
