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


# ---------------- Pydantic schemas ----------------
class WatchlistCreate(BaseModel):
    ticker: str
    notes: Optional[str] = None


class WatchlistUpdate(BaseModel):
    active: Optional[bool] = None
    notes: Optional[str] = None


class ParametersUpdate(BaseModel):
    buy_threshold_stddev: Optional[float] = None
    lookback_days: Optional[int] = None
    sell_tranche_pct: Optional[float] = None
    sell_gain_steps: Optional[List[float]] = None
    max_position_size_usd: Optional[float] = None


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


# ---------------- startup ----------------
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
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


# ---------------- watchlist + parameters ----------------
def params_dict(p: Parameters):
    return {
        "ticker": p.ticker,
        "buy_threshold_stddev": p.buy_threshold_stddev,
        "lookback_days": p.lookback_days,
        "sell_tranche_pct": p.sell_tranche_pct,
        "sell_gain_steps": p.sell_gain_steps,
        "max_position_size_usd": p.max_position_size_usd,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@app.get("/api/watchlist")
def list_watchlist(db: Session = Depends(get_db)):
    out = []
    for w in db.query(Watchlist).order_by(Watchlist.ticker).all():
        p = db.query(Parameters).get(w.ticker)
        out.append({
            "ticker": w.ticker,
            "date_added": w.date_added.isoformat() if w.date_added else None,
            "active": w.active,
            "notes": w.notes,
            "parameters": params_dict(p) if p else None,
        })
    return out


@app.post("/api/watchlist")
def add_watchlist(body: WatchlistCreate, db: Session = Depends(get_db)):
    tk = body.ticker.strip().upper()
    if not tk:
        raise HTTPException(400, "ticker required")
    if db.query(Watchlist).get(tk):
        raise HTTPException(400, f"{tk} already in watchlist")
    db.add(Watchlist(ticker=tk, notes=body.notes, active=True, date_added=utcnow()))
    db.add(Parameters(ticker=tk))
    db.commit()
    return {"ticker": tk, "status": "added"}


@app.put("/api/watchlist/{ticker}")
def update_watchlist(ticker: str, body: WatchlistUpdate, db: Session = Depends(get_db)):
    w = db.query(Watchlist).get(ticker.upper())
    if not w:
        raise HTTPException(404, "ticker not found")
    if body.active is not None:
        w.active = body.active
    if body.notes is not None:
        w.notes = body.notes
    db.commit()
    return {"ticker": w.ticker, "active": w.active, "notes": w.notes}


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
