"""Mean-reversion buy + scale-out sell strategy with hard safety rails."""
from datetime import datetime, timezone
import statistics

from models import (
    Watchlist, Parameters, Trade, PositionState, AccountSnapshot, Alert, SystemState
)
from alpaca_service import get_service


def utcnow():
    return datetime.now(timezone.utc)


def log_alert(db, type_, message, severity="info"):
    db.add(Alert(type=type_, message=message, severity=severity, created_at=utcnow()))
    db.commit()


def get_state(db):
    state = db.query(SystemState).get(1)
    if not state:
        state = SystemState(id=1)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def ensure_day_baseline(db, state, equity):
    today = utcnow().strftime("%Y-%m-%d")
    if state.day_start_date != today or state.day_start_equity is None:
        state.day_start_equity = equity
        state.day_start_date = today
        db.commit()


def check_daily_loss(db, state, equity):
    """Auto-engage kill switch if daily loss limit breached."""
    if state.day_start_equity is None:
        return
    loss = state.day_start_equity - equity
    if loss >= state.max_daily_loss_usd and not state.kill_switch_engaged:
        state.kill_switch_engaged = True
        state.kill_switch_reason = (
            f"Auto-engaged: daily loss ${loss:,.2f} breached limit ${state.max_daily_loss_usd:,.2f}"
        )
        db.commit()
        log_alert(db, "kill_switch", state.kill_switch_reason, "critical")


def run_strategy(db, manual=False):
    """Main strategy loop. Returns a summary dict of actions taken."""
    state = get_state(db)
    svc = get_service(state.trading_mode)
    summary = {"buys": [], "sells": [], "skipped": [], "errors": [], "halted": False}

    # snapshot account + safety checks
    try:
        acct = svc.get_account()
        ensure_day_baseline(db, state, acct["equity"])
        db.add(AccountSnapshot(
            equity=acct["equity"], cash=acct["cash"],
            buying_power=acct["buying_power"], timestamp=utcnow()
        ))
        db.commit()
        check_daily_loss(db, state, acct["equity"])
    except Exception as e:
        summary["errors"].append(f"account fetch failed: {e}")
        log_alert(db, "order_failure", f"Account fetch failed: {e}", "warning")
        acct = None

    db.refresh(state)
    if state.kill_switch_engaged:
        summary["halted"] = True
        summary["skipped"].append("Kill switch engaged - no new orders placed")
        return summary

    # live positions snapshot for exposure cap
    try:
        positions = {p["ticker"]: p for p in svc.get_positions()}
    except Exception as e:
        positions = {}
        summary["errors"].append(f"positions fetch failed: {e}")

    total_exposure = sum(p["market_value"] for p in positions.values())

    active = db.query(Watchlist).filter(Watchlist.active == True).all()  # noqa: E712
    for w in active:
        params = db.query(Parameters).get(w.ticker)
        if not params:
            continue
        snapshot = _params_snapshot(params)

        # ---------- SELL (scale-out ladder) ----------
        pstate = db.query(PositionState).filter(
            PositionState.ticker == w.ticker, PositionState.status == "open"
        ).first()
        pos = positions.get(w.ticker)
        if pstate and pos and pos["qty"] > 0:
            try:
                _evaluate_sells(db, svc, w.ticker, params, snapshot, pstate, pos, summary)
            except Exception as e:
                summary["errors"].append(f"{w.ticker} sell error: {e}")
                log_alert(db, "order_failure", f"{w.ticker} sell failed: {e}", "warning")

        # ---------- BUY (mean reversion) ----------
        try:
            _evaluate_buy(db, svc, w.ticker, params, snapshot, positions,
                          total_exposure, state, summary)
            # refresh exposure after potential buy
            total_exposure = sum(p["market_value"] for p in positions.values())
        except Exception as e:
            summary["errors"].append(f"{w.ticker} buy error: {e}")
            log_alert(db, "order_failure", f"{w.ticker} buy failed: {e}", "warning")

    return summary


def _params_snapshot(p):
    return {
        "buy_threshold_stddev": p.buy_threshold_stddev,
        "lookback_days": p.lookback_days,
        "sell_tranche_pct": p.sell_tranche_pct,
        "sell_gain_steps": p.sell_gain_steps,
        "max_position_size_usd": p.max_position_size_usd,
    }


def _evaluate_buy(db, svc, ticker, params, snapshot, positions, total_exposure, state, summary):
    closes = svc.get_daily_closes(ticker, params.lookback_days)
    if len(closes) < max(5, params.lookback_days // 2):
        summary["skipped"].append(f"{ticker}: insufficient price history ({len(closes)} bars)")
        return
    price = svc.get_latest_price(ticker)
    mean = statistics.mean(closes)
    std = statistics.pstdev(closes)
    if std == 0:
        summary["skipped"].append(f"{ticker}: zero volatility")
        return
    threshold = mean - params.buy_threshold_stddev * std
    z = (price - mean) / std

    if price > threshold:
        summary["skipped"].append(f"{ticker}: price ${price:.2f} above buy trigger ${threshold:.2f} (z={z:.2f})")
        return

    pos = positions.get(ticker)
    current_val = pos["market_value"] if pos else 0.0
    room = params.max_position_size_usd - current_val
    if room <= 1:
        summary["skipped"].append(f"{ticker}: already at max position size")
        return

    # exposure cap (hard server-side, independent of strategy)
    exposure_room = state.max_total_exposure_usd - total_exposure
    notional = min(room, exposure_room)
    if notional <= 1:
        summary["skipped"].append(f"{ticker}: total exposure cap reached")
        return

    reason = (
        f"price ${price:.2f} is {abs(z):.2f} stddev below {params.lookback_days}d mean "
        f"${mean:.2f} (trigger {params.buy_threshold_stddev} stddev = ${threshold:.2f})"
    )
    order = svc.submit_buy_notional(ticker, notional)
    qty_est = notional / price
    db.add(Trade(
        ticker=ticker, side="buy", quantity=round(qty_est, 6), price=price,
        order_id=order["id"], trigger_reason=reason, params_snapshot=snapshot,
        timestamp=utcnow(),
    ))
    # create / update position state
    pstate = db.query(PositionState).filter(
        PositionState.ticker == ticker, PositionState.status == "open"
    ).first()
    if not pstate:
        pstate = PositionState(ticker=ticker, original_qty=qty_est, avg_entry_price=price,
                               tranches_executed=[], opened_at=utcnow(), status="open")
        db.add(pstate)
    else:
        new_qty = pstate.original_qty + qty_est
        pstate.avg_entry_price = (
            (pstate.avg_entry_price * pstate.original_qty + price * qty_est) / new_qty
        )
        pstate.original_qty = new_qty
    db.commit()
    summary["buys"].append({"ticker": ticker, "notional": round(notional, 2), "reason": reason})


def _evaluate_sells(db, svc, ticker, params, snapshot, pstate, pos, summary):
    entry = pstate.avg_entry_price or pos["avg_entry_price"]
    price = pos["current_price"]
    gain = (price - entry) / entry if entry else 0.0
    steps = params.sell_gain_steps or []
    executed = list(pstate.tranches_executed or [])

    for idx, step in enumerate(steps):
        if idx in executed:
            continue
        if gain >= step:
            sell_qty = pstate.original_qty * params.sell_tranche_pct
            available = pos["qty"]
            sell_qty = min(sell_qty, available)
            if sell_qty <= 0:
                continue
            reason = (
                f"tranche {idx + 1} of {len(steps)} at +{gain * 100:.1f}% gain "
                f"(step trigger +{step * 100:.1f}%)"
            )
            order = svc.submit_sell_qty(ticker, sell_qty)
            realized = (price - entry) * sell_qty
            pstate.realized_pnl = (pstate.realized_pnl or 0.0) + realized
            db.add(Trade(
                ticker=ticker, side="sell", quantity=round(sell_qty, 6), price=price,
                order_id=order["id"], trigger_reason=reason, params_snapshot=snapshot,
                realized_pnl=round(realized, 2), timestamp=utcnow(),
            ))
            executed.append(idx)
            pstate.tranches_executed = executed
            available -= sell_qty
            db.commit()
            summary["sells"].append({
                "ticker": ticker, "qty": round(sell_qty, 6),
                "realized_pnl": round(realized, 2), "reason": reason,
            })

    # close position state if all tranches done or no shares left
    if len(executed) >= len(steps) and steps:
        pstate.status = "closed"
        pstate.closed_at = utcnow()
        db.commit()
