"""Rule-based, explainable adaptive suggestion engine (no auto-apply)."""
from datetime import datetime, timezone
import statistics

from models import Watchlist, Parameters, Trade, Suggestion


def utcnow():
    return datetime.now(timezone.utc)


def _round(v):
    return round(v, 4)


def generate_for_ticker(db, ticker):
    """Analyze a ticker's trade history and emit pending suggestions."""
    params = db.query(Parameters).get(ticker)
    if not params:
        return []
    trades = (
        db.query(Trade)
        .filter(Trade.ticker == ticker)
        .order_by(Trade.timestamp.asc())
        .all()
    )
    buys = [t for t in trades if t.side == "buy"]
    sells = [t for t in trades if t.side == "sell"]
    created = []

    if len(buys) < 2 and len(sells) < 2:
        return created  # not enough signal

    # clear stale pending suggestions for this ticker so we don't pile duplicates
    db.query(Suggestion).filter(
        Suggestion.ticker == ticker, Suggestion.status == "pending"
    ).delete()
    db.commit()

    # --- Heuristic 1: buys followed by further drops => threshold too loose ---
    # Compare each buy price to the lowest subsequent buy/sell price.
    drops = []
    for i, b in enumerate(buys):
        later = [t for t in trades if t.timestamp > b.timestamp]
        if later:
            min_later = min(t.price for t in later)
            drops.append((min_later - b.price) / b.price)
    if drops:
        avg_drop = statistics.mean(drops)
        if avg_drop < -0.03:  # avg 3%+ further drop after buying
            cur = params.buy_threshold_stddev
            new = _round(min(cur + 0.4, 4.0))
            if new != cur:
                created.append(_mk(db, ticker, "buy_threshold_stddev", cur, new,
                    f"Buys were followed by an average further drop of {avg_drop*100:.1f}%. "
                    f"Threshold looks too loose — raising buy_threshold_stddev from {cur} to {new} "
                    f"waits for deeper dislocations before entering."))
        elif avg_drop > 0.04:  # price rebounded quickly after buys
            cur = params.buy_threshold_stddev
            new = _round(max(cur - 0.4, 0.5))
            if new != cur:
                created.append(_mk(db, ticker, "buy_threshold_stddev", cur, new,
                    f"Buys were typically followed by a quick rebound (avg +{avg_drop*100:.1f}%). "
                    f"Threshold may be too tight — lowering buy_threshold_stddev from {cur} to {new} "
                    f"lets entries trigger a bit earlier."))

    # --- Heuristic 2: first sell tranche fires too early vs eventual peak ---
    if sells:
        # gain captured at first tranche vs max sell gain achieved
        steps = params.sell_gain_steps or []
        if steps:
            first_step = steps[0]
            # estimate realized vs peak using sell prices relative to buys
            if buys:
                avg_buy = statistics.mean(t.price for t in buys)
                max_sell = max(t.price for t in sells)
                peak_gain = (max_sell - avg_buy) / avg_buy if avg_buy else 0
                if peak_gain > first_step * 2.5 and first_step < 0.15:
                    new = _round(min(first_step + 0.03, peak_gain / 2))
                    if new != first_step:
                        created.append(_mk(db, ticker, "sell_gain_steps[0]", first_step, new,
                            f"Eventual peak gain reached +{peak_gain*100:.1f}% but the first tranche "
                            f"sold at only +{first_step*100:.1f}%. Raising the first sell step from "
                            f"{first_step} to {new} captures more of the upside move."))
                elif peak_gain < first_step and peak_gain > 0:
                    new = _round(max(peak_gain * 0.6, 0.02))
                    if new != first_step:
                        created.append(_mk(db, ticker, "sell_gain_steps[0]", first_step, new,
                            f"Price rarely reached the first sell step (+{first_step*100:.1f}%); "
                            f"observed peak was only +{peak_gain*100:.1f}%. Lowering the first sell "
                            f"step from {first_step} to {new} locks in gains sooner."))

    db.commit()
    return created


def _mk(db, ticker, param, cur, new, rationale):
    s = Suggestion(
        ticker=ticker, suggested_param=param,
        current_value=float(cur), suggested_value=float(new),
        rationale=rationale, status="pending", created_at=utcnow(),
    )
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
    """Apply an approved suggestion to the parameters row."""
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
    elif hasattr(params, param):
        setattr(params, param, suggestion.suggested_value)
    params.updated_at = utcnow()
    db.commit()
    return True
