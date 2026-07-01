"""
Long-term mean-reversion strategy (v2).

Daily cadence using daily closing bars. Per ticker, on each run:
  1. STOP-LOSS check (priority)  -> full exit if price fell below stop
  2. SELL scale-out ladder       -> tranche exits as gains clear steps
  3. BUY (mean-reversion)        -> stddev signal + 200d trend filter + optional 52w-range
                                    gate, cooldown, volatility-adjusted sizing, LIMIT order
Hard safety rails (per-ticker max, total exposure, daily loss auto-kill) are enforced
independently of the strategy.
"""
from datetime import datetime, timezone
import statistics

from models import (
    Watchlist, Parameters, Trade, PositionState, AccountSnapshot, Alert, SystemState, GlobalStrategy
)
from alpaca_service import get_service


def utcnow():
    return datetime.now(timezone.utc)


def get_global(db):
    g = db.query(GlobalStrategy).get(1)
    if not g:
        g = GlobalStrategy(id=1)
        db.add(g)
        db.commit()
        db.refresh(g)
    return g


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


def _params_snapshot(p):
    return {
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
    }


def run_strategy(db, manual=False):
    state = get_state(db)
    svc = get_service(state.trading_mode)
    summary = {"buys": [], "sells": [], "skipped": [], "errors": [], "halted": False}

    try:
        acct = svc.get_account()
        ensure_day_baseline(db, state, acct["equity"])
        db.add(AccountSnapshot(equity=acct["equity"], cash=acct["cash"],
                               buying_power=acct["buying_power"], timestamp=utcnow()))
        db.commit()
        check_daily_loss(db, state, acct["equity"])
    except Exception as e:
        summary["errors"].append(f"account fetch failed: {e}")
        log_alert(db, "order_failure", f"Account fetch failed: {e}", "warning")

    db.refresh(state)
    if state.kill_switch_engaged:
        summary["halted"] = True
        summary["skipped"].append("Kill switch engaged - no new orders placed")
        return summary

    # cancel stale/unfilled limit orders from prior runs -> re-evaluate fresh
    svc.cancel_all_orders()

    try:
        positions = {p["ticker"]: p for p in svc.get_positions()}
    except Exception as e:
        positions = {}
        summary["errors"].append(f"positions fetch failed: {e}")

    _reconcile(db, svc, positions, summary)

    total_exposure = sum(p["market_value"] for p in positions.values())

    gconf = get_global(db)
    active = db.query(Watchlist).filter(Watchlist.active == True).all()  # noqa: E712
    for w in active:
        params = gconf  # one global config applies to every stock
        snapshot = _params_snapshot(params)

        pstate = db.query(PositionState).filter(
            PositionState.ticker == w.ticker, PositionState.status == "open"
        ).first()
        pos = positions.get(w.ticker)

        # 1 + 2: stop-loss (priority) then tranche ladder
        if pstate and pos and pos["qty"] > 0:
            try:
                stopped = _check_stop_loss(db, svc, w.ticker, params, snapshot, pstate, pos, summary)
                if not stopped:
                    _evaluate_sells(db, svc, w.ticker, params, snapshot, pstate, pos, summary)
            except Exception as e:
                summary["errors"].append(f"{w.ticker} sell error: {e}")
                log_alert(db, "order_failure", f"{w.ticker} sell failed: {e}", "warning")

        # 3: buy (with conviction + earnings gates)
        try:
            _evaluate_buy(db, svc, w, params, snapshot, positions,
                          total_exposure, state, summary)
            total_exposure = sum(p["market_value"] for p in positions.values())
        except Exception as e:
            summary["errors"].append(f"{w.ticker} buy error: {e}")
            log_alert(db, "order_failure", f"{w.ticker} buy failed: {e}", "warning")

    # weekly accumulation (DCA) — runs at most once per 7 days
    try:
        total_exposure = sum(p["market_value"] for p in positions.values())
        run_accumulation(db, svc, gconf, state, positions, total_exposure, summary)
    except Exception as e:
        summary["errors"].append(f"accumulation error: {e}")
        log_alert(db, "order_failure", f"Accumulation failed: {e}", "warning")

    return summary


def _days_since(date_str):
    if not date_str:
        return 9999
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (utcnow() - d).days
    except ValueError:
        return 9999


def run_accumulation(db, svc, gconf, state, positions, total_exposure, summary, force=False):
    """Weekly dollar-cost-averaging: split weekly_budget across eligible active stocks,
    weighted by conviction (tilted by cached fundamentals quality). Long-term buys via
    market notional orders; respects per-stock max size and total exposure caps."""
    if not gconf.accumulate_enabled and not force:
        return
    if not force and _days_since(state.last_accumulate_date) < 7:
        summary["skipped"].append(
            f"accumulation: already ran {_days_since(state.last_accumulate_date)}d ago (weekly)")
        return

    from models import Fundamentals  # local import to avoid cycle
    active = db.query(Watchlist).filter(Watchlist.active == True).all()  # noqa: E712
    eligible = []
    for w in active:
        conv = w.conviction if w.conviction is not None else 3
        if conv < (gconf.min_conviction_to_buy or 0):
            continue
        # earnings blackout
        if w.next_earnings_date and gconf.earnings_blackout_days:
            try:
                ed = datetime.strptime(w.next_earnings_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                dt = (ed - utcnow()).days
                if 0 <= dt <= gconf.earnings_blackout_days:
                    continue
            except ValueError:
                pass
        f = db.query(Fundamentals).get(w.ticker)
        tilt = 1.0
        if f and f.pe_ratio is not None:  # has usable fundamentals
            from fundamentals import quality_score
            q = quality_score(f)
            if q is not None:
                tilt = 0.75 + q / 200.0  # ~0.75..1.25
        eligible.append((w, conv, conv * tilt))

    if not eligible:
        summary["skipped"].append("accumulation: no eligible stocks (check conviction gate)")
        return

    budget = float(gconf.weekly_budget_usd or 0)
    total_w = sum(x[2] for x in eligible)
    accumulated = []
    for w, conv, weight in eligible:
        alloc = budget * weight / total_w
        pos = positions.get(w.ticker)
        current_val = pos["market_value"] if pos else 0.0
        room = gconf.max_position_size_usd - current_val
        if room <= 1:
            continue
        alloc = min(alloc, room, state.max_total_exposure_usd - total_exposure)
        if alloc < 1:
            continue
        try:
            price = svc.get_latest_price(w.ticker)
        except Exception:
            price = pos["current_price"] if pos else None
        order = svc.submit_buy_notional(w.ticker, round(alloc, 2))
        qty = (alloc / price) if price else float(order.get("qty") or 0)
        reason = (f"Weekly accumulation: ${alloc:.2f} (conviction {conv}/5, "
                  f"weight {weight / total_w * 100:.0f}% of ${budget:.0f} budget)")
        db.add(Trade(ticker=w.ticker, side="buy", quantity=round(qty, 6),
                     price=round(price, 2) if price else 0.0, order_id=order["id"],
                     trigger_reason=reason, params_snapshot=_params_snapshot(gconf),
                     timestamp=utcnow()))
        pstate = db.query(PositionState).filter(
            PositionState.ticker == w.ticker, PositionState.status == "open").first()
        if not pstate:
            pstate = PositionState(ticker=w.ticker, original_qty=qty,
                                   avg_entry_price=price or 0.0, tranches_executed=[],
                                   opened_at=utcnow(), status="open", entry_order_id=order["id"])
            db.add(pstate)
        elif price:
            new_qty = pstate.original_qty + qty
            if new_qty > 0:
                pstate.avg_entry_price = (
                    (pstate.avg_entry_price * pstate.original_qty + price * qty) / new_qty)
                pstate.original_qty = new_qty
        total_exposure += alloc
        accumulated.append({"ticker": w.ticker, "alloc": round(alloc, 2), "reason": reason})
        summary["buys"].append({"ticker": w.ticker, "qty": round(qty, 6),
                                "notional": round(alloc, 2), "reason": reason})

    state.last_accumulate_date = utcnow().strftime("%Y-%m-%d")
    db.commit()
    summary["accumulated"] = accumulated
    if accumulated:
        log_alert(db, "info", f"Weekly accumulation bought {len(accumulated)} stocks "
                  f"(${budget:.0f} budget)", "info")


def _reconcile(db, svc, positions, summary):
    """Sync open position states to actual fills; clear phantom unfilled limit buys."""
    states = db.query(PositionState).filter(PositionState.status == "open").all()
    for ps in states:
        pos = positions.get(ps.ticker)
        has_pos = pos and pos["qty"] > 0
        sold_any = bool(ps.tranches_executed or [])
        if not has_pos:
            if not sold_any:
                # limit buy never filled -> remove phantom trade + state
                if ps.entry_order_id:
                    db.query(Trade).filter(
                        Trade.order_id == ps.entry_order_id, Trade.side == "buy"
                    ).delete()
                summary["skipped"].append(f"{ps.ticker}: prior limit buy did not fill — cleared")
                db.delete(ps)
            else:
                ps.status = "closed"
                ps.closed_at = utcnow()
        elif not sold_any:
            # sync to actual filled qty / entry (handles partial fills)
            ps.original_qty = pos["qty"]
            ps.avg_entry_price = pos["avg_entry_price"]
    db.commit()


def _last_closed_at(db, ticker):
    p = (
        db.query(PositionState)
        .filter(PositionState.ticker == ticker, PositionState.status == "closed")
        .order_by(PositionState.closed_at.desc())
        .first()
    )
    return p.closed_at if p else None


def _check_stop_loss(db, svc, ticker, params, snapshot, pstate, pos, summary):
    if not params.stop_loss_pct or params.stop_loss_pct <= 0:
        return False
    entry = pstate.avg_entry_price or pos["avg_entry_price"]
    price = pos["current_price"]
    if not entry or price > entry * (1 - params.stop_loss_pct):
        return False
    qty = pos["qty"]
    order = svc.submit_sell_qty(ticker, qty)
    realized = (price - entry) * qty
    pstate.realized_pnl = (pstate.realized_pnl or 0.0) + realized
    loss_pct = (price - entry) / entry * 100
    reason = (
        f"STOP-LOSS exit: price ${price:.2f} is {loss_pct:.1f}% vs entry ${entry:.2f} "
        f"(stop {params.stop_loss_pct * 100:.0f}%) — full position closed"
    )
    db.add(Trade(ticker=ticker, side="sell", quantity=round(qty, 6), price=price,
                 order_id=order["id"], trigger_reason=reason, params_snapshot=snapshot,
                 realized_pnl=round(realized, 2), timestamp=utcnow()))
    pstate.status = "closed"
    pstate.closed_at = utcnow()
    db.commit()
    log_alert(db, "safety", f"{ticker} stop-loss triggered ({loss_pct:.1f}%)", "warning")
    summary["sells"].append({"ticker": ticker, "qty": round(qty, 6),
                             "realized_pnl": round(realized, 2), "reason": reason,
                             "stop_loss": True})
    return True


def _evaluate_buy(db, svc, w, params, snapshot, positions, total_exposure, state, summary):
    ticker = w.ticker

    # conviction gate (manual quality/influencer rating)
    conviction = w.conviction if w.conviction is not None else 3
    if conviction < (params.min_conviction_to_buy or 0):
        summary["skipped"].append(
            f"{ticker}: skipped — conviction {conviction}/5 below minimum "
            f"{params.min_conviction_to_buy}/5")
        return

    # earnings blackout gate
    if w.next_earnings_date and params.earnings_blackout_days:
        try:
            ed = datetime.strptime(w.next_earnings_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_to = (ed - utcnow()).days
            if 0 <= days_to <= params.earnings_blackout_days:
                summary["skipped"].append(
                    f"{ticker}: skipped — earnings in {days_to}d "
                    f"(blackout {params.earnings_blackout_days}d)")
                return
        except ValueError:
            pass

    need = max(params.lookback_days, 200, 252) + 5
    bars = svc.get_daily_bars(ticker, need)
    closes = [b["close"] for b in bars]
    if len(closes) < max(20, params.lookback_days // 2):
        summary["skipped"].append(f"{ticker}: insufficient price history ({len(closes)} bars)")
        return

    price = closes[-1]  # prior session close (daily cadence)
    window = closes[-params.lookback_days:]
    mean = statistics.mean(window)
    std = statistics.pstdev(window)
    if std == 0:
        summary["skipped"].append(f"{ticker}: zero volatility")
        return
    threshold = mean - params.buy_threshold_stddev * std
    z = (price - mean) / std
    stddev_pass = price <= threshold

    # 200-day trend filter
    ma_window = closes[-200:] if len(closes) >= 200 else closes
    ma200 = statistics.mean(ma_window)
    above_ma = price > ma200
    trend_pass = above_ma or params.allow_downtrend_buys

    # optional 52-week range gate
    range_pass = True
    range_note = ""
    if params.use_52w_range:
        win = bars[-252:] if len(bars) >= 252 else bars
        hi = max(b["high"] for b in win)
        lo = min(b["low"] for b in win)
        pos_in = (price - lo) / (hi - lo) if hi > lo else 1.0
        range_pass = pos_in <= params.range_pct
        range_note = (f"; 52w-range {pos_in * 100:.0f}% (need <= {params.range_pct * 100:.0f}%, "
                      f"{'pass' if range_pass else 'fail'})")

    trend_label = "above" if above_ma else "below"
    if not above_ma and params.allow_downtrend_buys:
        trend_label = "below (override ON)"
    reason = (
        f"price ${price:.2f} is {abs(z):.2f} stddev below {params.lookback_days}d mean "
        f"${mean:.2f} (trigger {params.buy_threshold_stddev} stddev = ${threshold:.2f}, "
        f"{'pass' if stddev_pass else 'fail'}); trend: {trend_label} 200d MA ${ma200:.2f} "
        f"({'pass' if trend_pass else 'fail'}){range_note}"
    )

    if not (stddev_pass and trend_pass and range_pass):
        summary["skipped"].append(f"{ticker}: {reason}")
        return

    # cooldown gate (re-entry suppression after a recent close)
    last_closed = _last_closed_at(db, ticker)
    if last_closed and params.cooldown_days:
        if last_closed.tzinfo is None:
            last_closed = last_closed.replace(tzinfo=timezone.utc)
        days_since = (utcnow() - last_closed).days
        if days_since < params.cooldown_days:
            summary["skipped"].append(
                f"{ticker}: skipped — in cooldown (closed {days_since}d ago, "
                f"cooldown {params.cooldown_days}d)")
            return

    pos = positions.get(ticker)
    current_val = pos["market_value"] if pos else 0.0

    # volatility-adjusted sizing (optional)
    effective_max = params.max_position_size_usd
    size_note = ""
    if params.use_volatility_sizing:
        vol = std / price if price else 0
        if vol > 0:
            factor = min(1.0, state.baseline_volatility / vol)
            effective_max = params.max_position_size_usd * factor
            size_note = (f" [vol-adj: stock vol {vol*100:.1f}% vs baseline "
                         f"{state.baseline_volatility*100:.1f}% -> cap ${effective_max:.0f}]")

    room = effective_max - current_val
    if room <= 1:
        summary["skipped"].append(f"{ticker}: already at max position size{size_note}")
        return
    exposure_room = state.max_total_exposure_usd - total_exposure
    notional = min(room, exposure_room)
    if notional <= 1:
        summary["skipped"].append(f"{ticker}: total exposure cap reached")
        return

    # LIMIT buy at the trigger price (integer qty required for limit orders)
    limit_price = round(threshold, 2)
    qty = int(notional // limit_price)
    if qty < 1:
        summary["skipped"].append(
            f"{ticker}: buy size below 1 share at limit ${limit_price:.2f} "
            f"(notional ${notional:.0f}){size_note}")
        return

    reason = reason + f"; LIMIT buy {qty} @ ${limit_price:.2f}{size_note}"
    order = svc.submit_buy_limit(ticker, qty, limit_price)
    db.add(Trade(ticker=ticker, side="buy", quantity=float(qty), price=limit_price,
                 order_id=order["id"], trigger_reason=reason, params_snapshot=snapshot,
                 timestamp=utcnow()))
    pstate = db.query(PositionState).filter(
        PositionState.ticker == ticker, PositionState.status == "open").first()
    if not pstate:
        pstate = PositionState(ticker=ticker, original_qty=float(qty), avg_entry_price=limit_price,
                               tranches_executed=[], opened_at=utcnow(), status="open",
                               entry_order_id=order["id"])
        db.add(pstate)
    else:
        new_qty = pstate.original_qty + qty
        pstate.avg_entry_price = (
            (pstate.avg_entry_price * pstate.original_qty + limit_price * qty) / new_qty)
        pstate.original_qty = new_qty
    db.commit()
    summary["buys"].append({"ticker": ticker, "qty": qty, "limit_price": limit_price, "reason": reason})


def _evaluate_sells(db, svc, ticker, params, snapshot, pstate, pos, summary):
    entry = pstate.avg_entry_price or pos["avg_entry_price"]
    price = pos["current_price"]
    gain = (price - entry) / entry if entry else 0.0
    steps = params.sell_gain_steps or []
    executed = list(pstate.tranches_executed or [])
    available = pos["qty"]

    qualifying = [i for i, step in enumerate(steps) if i not in executed and gain >= step]
    if not qualifying:
        return

    # Aggregate qualifying tranches into ONE sell order (avoids overlapping-order rejects).
    desired = pstate.original_qty * params.sell_tranche_pct * len(qualifying)
    sell_qty = min(desired, available)
    if sell_qty <= 0:
        return

    multi = len(qualifying) > 1
    tranche_nums = ", ".join(str(i + 1) for i in qualifying)
    step_labels = ", ".join(f"+{steps[i] * 100:.1f}%" for i in qualifying)
    reason = (
        f"tranche{'s' if multi else ''} {tranche_nums} of {len(steps)} at "
        f"+{gain * 100:.1f}% gain (step trigger{'s' if multi else ''} {step_labels})"
    )
    order = svc.submit_sell_qty(ticker, sell_qty)
    realized = (price - entry) * sell_qty
    pstate.realized_pnl = (pstate.realized_pnl or 0.0) + realized
    db.add(Trade(ticker=ticker, side="sell", quantity=round(sell_qty, 6), price=price,
                 order_id=order["id"], trigger_reason=reason, params_snapshot=snapshot,
                 realized_pnl=round(realized, 2), timestamp=utcnow()))
    executed.extend(qualifying)
    pstate.tranches_executed = executed
    db.commit()
    summary["sells"].append({"ticker": ticker, "qty": round(sell_qty, 6),
                             "realized_pnl": round(realized, 2), "reason": reason})

    if len(executed) >= len(steps) and steps:
        pstate.status = "closed"
        pstate.closed_at = utcnow()
        db.commit()
