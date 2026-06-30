"""Rule-based, explainable adaptive suggestion engine (no auto-apply), v2.

Triggers only after a minimum sample size (sparse long-term trades), and can now
propose stop-loss and cooldown adjustments in addition to buy threshold / sell steps.
"""
from datetime import datetime, timezone
import statistics

from models import Watchlist, Parameters, Trade, Suggestion, PositionState

MIN_SAMPLE = 3  # minimum closed sell trades for a ticker before we suggest anything


def utcnow():
    return datetime.now(timezone.utc)


def _round(v):
    return round(v, 4)


def generate_for_ticker(db, ticker):
    params = db.query(Parameters).get(ticker)
    if not params:
        return []
    trades = (
        db.query(Trade).filter(Trade.ticker == ticker).order_by(Trade.timestamp.asc()).all()
    )
    buys = [t for t in trades if t.side == "buy"]
    sells = [t for t in trades if t.side == "sell"]
    closed_positions = (
        db.query(PositionState)
        .filter(PositionState.ticker == ticker, PositionState.status == "closed")
        .count()
    )
    created = []

    # sparse long-term cadence: require a minimum sample before proposing changes
    if len(sells) < MIN_SAMPLE and closed_positions < MIN_SAMPLE:
        return created

    db.query(Suggestion).filter(
        Suggestion.ticker == ticker, Suggestion.status == "pending"
    ).delete()
    db.commit()

    # --- Heuristic 1: buys followed by further drops => buy threshold too loose ---
    drops = []
    for b in buys:
        later = [t for t in trades if t.timestamp > b.timestamp]
        if later:
            drops.append((min(t.price for t in later) - b.price) / b.price)
    avg_drop = statistics.mean(drops) if drops else 0.0
    if drops and avg_drop < -0.03:
        cur = params.buy_threshold_stddev
        new = _round(min(cur + 0.4, 4.0))
        if new != cur:
            created.append(_mk(db, ticker, "buy_threshold_stddev", cur, new,
                f"Buys were followed by an average further drop of {avg_drop*100:.1f}%. "
                f"Threshold looks too loose — raising buy_threshold_stddev from {cur} to {new} "
                f"waits for deeper dislocations before entering."))
    elif drops and avg_drop > 0.04:
        cur = params.buy_threshold_stddev
        new = _round(max(cur - 0.4, 0.5))
        if new != cur:
            created.append(_mk(db, ticker, "buy_threshold_stddev", cur, new,
                f"Buys were typically followed by a quick rebound (avg +{avg_drop*100:.1f}%). "
                f"Threshold may be too tight — lowering buy_threshold_stddev from {cur} to {new} "
                f"lets entries trigger a bit earlier."))

    # --- Heuristic 2: first sell tranche vs eventual peak ---
    steps = params.sell_gain_steps or []
    if sells and steps and buys:
        first_step = steps[0]
        avg_buy = statistics.mean(t.price for t in buys)
        max_sell = max(t.price for t in sells)
        peak_gain = (max_sell - avg_buy) / avg_buy if avg_buy else 0
        if peak_gain > first_step * 2.5 and first_step < 0.15:
            new = _round(min(first_step + 0.03, peak_gain / 2))
            if new != first_step:
                created.append(_mk(db, ticker, "sell_gain_steps[0]", first_step, new,
                    f"Eventual peak gain reached +{peak_gain*100:.1f}% but the first tranche sold "
                    f"at only +{first_step*100:.1f}%. Raising the first sell step from {first_step} "
                    f"to {new} captures more of the upside."))
        elif 0 < peak_gain < first_step:
            new = _round(max(peak_gain * 0.6, 0.02))
            if new != first_step:
                created.append(_mk(db, ticker, "sell_gain_steps[0]", first_step, new,
                    f"Price rarely reached the first sell step (+{first_step*100:.1f}%); observed "
                    f"peak +{peak_gain*100:.1f}%. Lowering it to {new} locks in gains sooner."))

    # --- Heuristic 3: frequent stop-loss exits => stop too tight (or add one) ---
    stop_exits = [t for t in sells if t.trigger_reason and "STOP-LOSS" in t.trigger_reason]
    if len(stop_exits) >= 2:
        cur = params.stop_loss_pct or 0.0
        if cur == 0:
            created.append(_mk(db, ticker, "stop_loss_pct", 0.0, 0.15,
                f"{len(stop_exits)} stop-style exits observed but no stop-loss is configured. "
                f"Adding a 15% stop_loss_pct formalises downside protection."))
        else:
            new = _round(min(cur + 0.05, 0.40))
            if new != cur:
                created.append(_mk(db, ticker, "stop_loss_pct", cur, new,
                    f"{len(stop_exits)} stop-loss exits triggered — the {cur*100:.0f}% stop may be "
                    f"too tight and shaking you out. Widening to {new*100:.0f}% reduces premature exits."))

    # --- Heuristic 4: whipsaw re-entries => lengthen cooldown ---
    if closed_positions >= 2 and drops and avg_drop < -0.03:
        cur = params.cooldown_days or 0
        new = int(min(cur + 5, 30))
        if new != cur:
            created.append(_mk(db, ticker, "cooldown_days", cur, new,
                f"Re-entries tended to keep falling (avg {avg_drop*100:.1f}%) across "
                f"{closed_positions} closed positions. Lengthening cooldown_days from {cur} to {new} "
                f"avoids buying back into a continuing decline."))

    db.commit()
    return created


def _mk(db, ticker, param, cur, new, rationale):
    s = Suggestion(ticker=ticker, suggested_param=param, current_value=float(cur),
                   suggested_value=float(new), rationale=rationale, status="pending",
                   created_at=utcnow())
    db.add(s)
    db.flush()
    return s


def generate_all(db):
    total = 0
    for w in db.query(Watchlist).all():
        total += len(generate_for_ticker(db, w.ticker))
    db.commit()
    return total


def apply_suggestion(db, suggestion):
    params = db.query(Parameters).get(suggestion.ticker)
    if not params:
        return False
    param = suggestion.suggested_param
    if param.startswith("sell_gain_steps["):
        idx = int(param.split("[")[1].rstrip("]"))
        steps = list(params.sell_gain_steps or [])
        if idx < len(steps):
            steps[idx] = suggestion.suggested_value
            steps.sort()
            params.sell_gain_steps = steps
    elif param == "cooldown_days":
        params.cooldown_days = int(suggestion.suggested_value)
    elif hasattr(params, param):
        setattr(params, param, suggestion.suggested_value)
    params.updated_at = utcnow()
    db.commit()
    return True
