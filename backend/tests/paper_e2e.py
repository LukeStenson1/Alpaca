"""
Extensive PAPER-mode end-to-end test harness.

Exercises the full strategy lifecycle and every safety rail against the LIVE Alpaca
paper account, then cleans up. Run with: /root/.venv/bin/python tests/paper_e2e.py
(cwd = /app/backend). Prints a PASS/FAIL report.
"""
import time
import sys
import requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/app/backend")
from database import SessionLocal
from models import (
    Watchlist, Parameters, Trade, PositionState, Suggestion, SystemState, Alert
)

BASE = "http://localhost:8001/api"
TK = "F"  # liquid, low-priced test ticker
SG = "AAPL"  # ticker used for synthetic suggestion-engine history

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def api(method, path, **kw):
    r = requests.request(method, BASE + path, timeout=30, **kw)
    return r


def run_strategy():
    return api("POST", "/strategy/run").json()


def positions_map():
    d = api("GET", "/positions").json()
    return {p["ticker"]: p for p in d.get("positions", [])}


def set_params(ticker, **fields):
    return api("PUT", f"/parameters/{ticker}", json=fields)


def db():
    return SessionLocal()


def flatten_account():
    """Cancel all open orders and close all positions; wait until flat."""
    from alpaca_service import get_service
    svc = get_service("paper")
    try:
        svc.trading.close_all_positions(cancel_orders=True)
    except Exception as e:
        print("flatten note:", e)
    for _ in range(20):
        time.sleep(1.5)
        try:
            if not svc.trading.get_all_positions() and not svc.trading.get_orders():
                break
        except Exception:
            pass


def wait_orders_clear(ticker, timeout=20):
    """Wait until there are no open orders for ticker (avoids wash-trade rejects)."""
    from alpaca_service import get_service
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus
    svc = get_service("paper")
    for _ in range(timeout):
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
            if not svc.trading.get_orders(filter=req):
                return
        except Exception:
            return
        time.sleep(1)


def reset_clean_state():
    s = db()
    st = s.query(SystemState).get(1)
    st.kill_switch_engaged = False
    st.kill_switch_reason = None
    st.trading_mode = "paper"
    st.max_daily_loss_usd = 500.0
    st.max_total_exposure_usd = 10000.0
    eq = api("GET", "/account").json().get("equity")
    st.day_start_equity = eq
    st.day_start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    st.scheduler_enabled = True
    s.commit()
    s.close()


# ============================================================
print("\n=== EXTENSIVE PAPER E2E TEST ===\n")
reset_clean_state()

acct = api("GET", "/account").json()
check("Alpaca paper connected", acct.get("connected") and acct.get("mode") == "paper",
      f"equity={acct.get('equity')}, market_open={acct.get('market_open')}")
MARKET_OPEN = acct.get("market_open")

# ---- start from a FLAT paper account + clean strategy state ----
flatten_account()
s = db()
s.query(PositionState).delete()
s.commit()
s.close()
print("account flattened, position states cleared\n")

# ---- setup test ticker F ----
if not api("GET", "/watchlist").json() or TK not in [w["ticker"] for w in api("GET", "/watchlist").json()]:
    api("POST", "/watchlist", json={"ticker": TK, "notes": "e2e test ticker"})
set_params(TK, buy_threshold_stddev=-5.0, lookback_days=30, sell_tranche_pct=0.5,
           sell_gain_steps=[0.02, 0.04], max_position_size_usd=200.0)

# ============================================================
# TEST 1: BUY (mean-reversion forced trigger)
# ============================================================
res = run_strategy()
bought = any(b["ticker"] == TK for b in res.get("buys", []))
check("T1 buy placed for forced trigger", bought, str(res.get("buys")))

wait_orders_clear(TK)
time.sleep(2)
pos = positions_map()
s = db()
ps = s.query(PositionState).filter(PositionState.ticker == TK, PositionState.status == "open").first()
s.close()
check("T1 position_state open created", ps is not None and ps.original_qty > 0,
      f"qty={getattr(ps,'original_qty',None)}")
check("T1 Alpaca position exists", TK in pos, f"{pos.get(TK,{}).get('qty')}")
buy_trades = [t for t in api("GET", f"/trades?ticker={TK}").json() if t["side"] == "buy"]
check("T1 buy trade logged w/ reason+snapshot",
      buy_trades and buy_trades[0]["trigger_reason"] and buy_trades[0]["params_snapshot"],
      buy_trades[0]["trigger_reason"] if buy_trades else "none")

# ============================================================
# TEST 2: PER-TICKER MAX SIZE SKIP (no double-buy at cap)
# ============================================================
res = run_strategy()
skipped_max = any(TK in m and ("max position size" in m or "exposure" in m) for m in res.get("skipped", []))
bought_again = any(b["ticker"] == TK for b in res.get("buys", []))
check("T2 no re-buy at max position size", (skipped_max or not bought_again),
      next((m for m in res.get("skipped", []) if TK in m), "n/a"))

# ============================================================
# TEST 3: SELL LADDER -> FULL CLOSE + realized P&L
# ============================================================
wait_orders_clear(TK)
pos = positions_map()
cur_price = pos.get(TK, {}).get("current_price")
if cur_price:
    s = db()
    ps = s.query(PositionState).filter(PositionState.ticker == TK, PositionState.status == "open").first()
    ps.original_qty = pos[TK]["qty"]      # sync to actual filled qty
    ps.avg_entry_price = cur_price / 1.05  # ~5% gain -> fires both 0.02 and 0.04
    s.commit()
    s.close()
    res = run_strategy()
    sells = [x for x in res.get("sells", []) if x["ticker"] == TK]
    check("T3 sell order placed for qualifying tranches", len(sells) >= 1,
          f"{len(sells)} sell order(s): {[x['reason'] for x in sells]} errors={res.get('errors')}")
    realized_ok = all(x.get("realized_pnl", 0) > 0 for x in sells)
    check("T3 realized P&L positive on sell", realized_ok and sells, str([x.get("realized_pnl") for x in sells]))
    time.sleep(2)
    s = db()
    ps = s.query(PositionState).filter(PositionState.ticker == TK).order_by(PositionState.opened_at.desc()).first()
    s.close()
    check("T3 position_state closed + closed_at set",
          ps.status == "closed" and ps.closed_at is not None,
          f"status={ps.status}, tranches={ps.tranches_executed}")
    check("T3 both tranches recorded as executed", sorted(ps.tranches_executed or []) == [0, 1],
          str(ps.tranches_executed))
    closed = api("GET", "/positions/closed").json()
    check("T3 appears in closed positions w/ realized P&L",
          any(c["ticker"] == TK and c["realized_pnl"] > 0 for c in closed),
          str([(c["ticker"], c["realized_pnl"]) for c in closed]))
    summ = api("GET", "/pnl/summary").json()
    check("T3 pnl summary closed_count incremented", summ["closed_count"] >= 1, str(summ))
    sell_trades = [t for t in api("GET", f"/trades?ticker={TK}").json() if t["side"] == "sell"]
    check("T3 sell trades carry realized_pnl",
          sell_trades and sell_trades[0].get("realized_pnl") is not None,
          str([t.get("realized_pnl") for t in sell_trades[:3]]))
else:
    check("T3 sell ladder (skipped - no price)", False, "no current_price for F")

# ============================================================
# TEST 4: GLOBAL EXPOSURE CAP enforced independent of strategy
# ============================================================
# re-arm F to buy, but choke total exposure room to ~$0
pos = positions_map()
total_exp = sum(p["market_value"] for p in pos.values())
s = db()
st = s.query(SystemState).get(1)
st.max_total_exposure_usd = round(total_exp + 1, 2)
s.commit()
s.close()
set_params(TK, buy_threshold_stddev=-5.0, sell_gain_steps=[0.02, 0.04],
           sell_tranche_pct=0.5, max_position_size_usd=200.0)
res = run_strategy()
exp_skip = any(TK in m and "exposure" in m for m in res.get("skipped", []))
no_buy = not any(b["ticker"] == TK for b in res.get("buys", []))
check("T4 exposure cap blocks new buy", exp_skip or no_buy,
      next((m for m in res.get("skipped", []) if TK in m), "no F skip line"))
# restore exposure
s = db(); st = s.query(SystemState).get(1); st.max_total_exposure_usd = 10000.0; s.commit(); s.close()

# ============================================================
# TEST 5: MAX DAILY LOSS -> auto-engage kill switch + alert
# ============================================================
eq = api("GET", "/account").json()["equity"]
s = db()
st = s.query(SystemState).get(1)
st.kill_switch_engaged = False
st.day_start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
st.day_start_equity = eq + 1000.0   # pretend we started $1000 higher -> $1000 loss
st.max_daily_loss_usd = 100.0       # breach threshold
s.commit()
s.close()
res = run_strategy()
st_after = api("GET", "/system/state").json()
check("T5 daily-loss auto-engaged kill switch", st_after["kill_switch_engaged"],
      st_after.get("kill_switch_reason"))
check("T5 strategy halted after auto-kill", res.get("halted") is True, str(res.get("halted")))
alerts = api("GET", "/alerts").json()
check("T5 critical kill_switch alert logged",
      any(a["type"] == "kill_switch" and a["severity"] == "critical" for a in alerts),
      next((a["message"] for a in alerts if a["type"] == "kill_switch"), "none"))

# ============================================================
# TEST 6: MANUAL KILL SWITCH blocks new orders
# ============================================================
api("POST", "/system/kill-switch", json={"engaged": True, "reason": "e2e manual halt"})
set_params(TK, buy_threshold_stddev=-5.0)
res = run_strategy()
check("T6 manual kill switch halts strategy", res.get("halted") is True
      and not any(b["ticker"] == TK for b in res.get("buys", [])), str(res.get("halted")))
api("POST", "/system/kill-switch", json={"engaged": False})

# ============================================================
# TEST 7: SUGGESTION ENGINE w/ synthetic history -> approve applies
# ============================================================
s = db()
# clear any prior synthetic
s.query(Trade).filter(Trade.ticker == SG, Trade.order_id == "SYNTH").delete()
s.query(Suggestion).filter(Suggestion.ticker == SG).delete()
s.commit()
base = datetime.now(timezone.utc)
# buys at 100, later prices much lower -> avg further drop < -3% => suggest RAISE buy_threshold
synth = [
    ("buy", 100.0), ("buy", 99.0), ("sell", 90.0), ("buy", 95.0), ("sell", 88.0),
]
for i, (side, price) in enumerate(synth):
    s.add(Trade(ticker=SG, side=side, quantity=1.0, price=price, order_id="SYNTH",
                trigger_reason="synthetic", params_snapshot={},
                timestamp=base + timedelta(minutes=i)))
s.commit()
pre = s.query(Parameters).get(SG).buy_threshold_stddev
s.close()
api("POST", "/suggestions/generate")
sugg = [x for x in api("GET", "/suggestions").json() if x["ticker"] == SG and x["status"] == "pending"]
check("T7 suggestion generated from trade history", len(sugg) >= 1,
      sugg[0]["rationale"] if sugg else "none")
if sugg:
    sid = sugg[0]["id"]
    new_val = sugg[0]["suggested_value"]
    ap = api("POST", f"/suggestions/{sid}/approve")
    check("T7 approve returns 200", ap.status_code == 200, ap.text[:120])
    s = db()
    post = s.query(Parameters).get(SG).buy_threshold_stddev
    s.close()
    check("T7 approval applied to parameters", abs(post - new_val) < 1e-6,
          f"{pre} -> {post} (suggested {new_val})")

# ============================================================
# CLEANUP
# ============================================================
print("\n--- cleanup ---")
# liquidate any leftover F shares on the paper account
try:
    from alpaca_service import get_service
    svc = get_service("paper")
    try:
        svc.trading.cancel_orders()  # cancel any open orders holding shares
        time.sleep(2)
    except Exception:
        pass
    pos = positions_map()
    if TK in pos and pos[TK]["qty"] > 0:
        svc.submit_sell_qty(TK, pos[TK]["qty"])
        print(f"liquidated leftover {TK} {pos[TK]['qty']} shares")
except Exception as e:
    print("liquidation note:", e)

s = db()
# remove synthetic data + suggestions + restore AAPL param
s.query(Trade).filter(Trade.ticker == SG, Trade.order_id == "SYNTH").delete()
s.query(Suggestion).filter(Suggestion.ticker == SG).delete()
ap = s.query(Parameters).get(SG)
ap.buy_threshold_stddev = 2.0
s.commit()
s.close()
# remove F from watchlist entirely (also drops its parameters + position_state)
api("DELETE", f"/watchlist/{TK}")
api("POST", "/alerts/acknowledge-all")
reset_clean_state()
print("cleanup done; mode=paper, kill switch off, limits restored, F removed, AAPL param reset")

# ============================================================
# REPORT
# ============================================================
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"\n=== RESULT: {passed}/{total} checks passed ===")
if passed != total:
    print("FAILURES:")
    for name, ok, detail in results:
        if not ok:
            print(f"  - {name}: {detail}")
    sys.exit(1)
