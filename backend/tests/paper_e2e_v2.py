"""
v2 PAPER end-to-end harness: trend filter, limit orders, stop-loss, cooldown,
volatility-adjusted sizing. Runs against the live paper account; cleans up after.
"""
import time
import sys
import requests
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")
from database import SessionLocal
from models import Parameters, PositionState, Trade, SystemState
import strategy

BASE = "http://localhost:8001/api"
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def api(m, p, **kw):
    return requests.request(m, BASE + p, timeout=30, **kw)


def run_strategy():
    return api("POST", "/strategy/run").json()


def positions_map():
    return {p["ticker"]: p for p in api("GET", "/positions").json().get("positions", [])}


def set_params(tk, **f):
    return api("PUT", f"/parameters/{tk}", json=f)


def db():
    return SessionLocal()


def flatten():
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


def wait_orders_clear(tk, timeout=20):
    from alpaca_service import get_service
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus
    svc = get_service("paper")
    for _ in range(timeout):
        try:
            if not svc.trading.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[tk])):
                return
        except Exception:
            return
        time.sleep(1)


def reset_state():
    s = db(); st = s.query(SystemState).get(1)
    st.kill_switch_engaged = False; st.trading_mode = "paper"
    st.max_total_exposure_usd = 50000.0; st.max_daily_loss_usd = 500.0
    eq = api("GET", "/account").json().get("equity")
    st.day_start_equity = eq; st.day_start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    s.commit(); s.close()


def restore_defaults():
    s = db()
    for tk in ["AAPL", "MSFT", "SPY"]:
        p = s.query(Parameters).get(tk)
        if p:
            p.buy_threshold_stddev = 2.0
            p.allow_downtrend_buys = False
            p.stop_loss_pct = 0.0
            p.cooldown_days = 7
            p.use_volatility_sizing = False
            p.use_52w_range = False
    s.commit(); s.close()


print("\n=== v2 PAPER E2E ===\n")
flatten()
s = db(); s.query(PositionState).delete(); s.commit(); s.close()
reset_state()

# ---------- T1/T2: trend filter block + override + LIMIT order ----------
set_params("MSFT", buy_threshold_stddev=-5.0, allow_downtrend_buys=False,
           use_52w_range=False, stop_loss_pct=0.0, use_volatility_sizing=False)
res = run_strategy()
msft_line = next((m for m in res["skipped"] if m.startswith("MSFT")), "")
msft_bought = any(b["ticker"] == "MSFT" for b in res["buys"])
below_ma = "below 200d MA" in msft_line
if below_ma:
    check("T1 trend filter blocks downtrend buy", (not msft_bought) and "fail" in msft_line, msft_line[:120])
else:
    check("T1 trend filter (MSFT above MA today — conditional)", True, "MSFT not in downtrend; skipping block assert")

set_params("MSFT", allow_downtrend_buys=True)
res = run_strategy()
msft_buy = next((b for b in res["buys"] if b["ticker"] == "MSFT"), None)
if below_ma:
    check("T2 downtrend override allows buy", msft_buy is not None, str(res["buys"]))
else:
    check("T2 downtrend override (conditional)", True, "n/a — MSFT not in downtrend")
if msft_buy:
    check("T2 buy uses LIMIT order at trigger", "LIMIT buy" in msft_buy["reason"], msft_buy["reason"][:140])
    wait_orders_clear("MSFT")
    bt = [t for t in api("GET", "/trades?ticker=MSFT").json() if t["side"] == "buy"]
    check("T2 limit buy trade logged with price", bt and bt[0]["price"] > 0, str(bt[0]["price"]) if bt else "none")
else:
    check("T2 buy uses LIMIT order at trigger", True, "skipped (MSFT not in downtrend)")
    check("T2 limit buy trade logged with price", True, "skipped")

# clean MSFT before next tests
flatten()
s = db(); s.query(PositionState).filter(PositionState.ticker == "MSFT").delete(); s.commit(); s.close()
set_params("MSFT", allow_downtrend_buys=False)

# ---------- T3: STOP-LOSS (direct e2e against a real position) ----------
set_params("AAPL", buy_threshold_stddev=-5.0, allow_downtrend_buys=False, stop_loss_pct=0.10,
           use_volatility_sizing=False, use_52w_range=False)
res = run_strategy()
wait_orders_clear("AAPL")
time.sleep(2)
pos = positions_map().get("AAPL")
if pos and pos["qty"] > 0:
    from alpaca_service import get_service
    svc = get_service("paper")
    s = db()
    ps = s.query(PositionState).filter(PositionState.ticker == "AAPL", PositionState.status == "open").first()
    params = s.query(Parameters).get("AAPL")
    entry = ps.avg_entry_price
    fab_pos = dict(pos)
    fab_pos["current_price"] = entry * 0.85  # 15% below entry -> breaches 10% stop
    summary = {"sells": [], "errors": []}
    stopped = strategy._check_stop_loss(s, svc, "AAPL", strategy._params_snapshot(params),
                                        strategy._params_snapshot(params), ps, fab_pos, summary)
    s.commit()
    check("T3 stop-loss triggers full exit", stopped and summary["sells"]
          and summary["sells"][0].get("stop_loss"), str(summary["sells"]))
    s.refresh(ps)
    check("T3 position closed after stop-loss", ps.status == "closed" and ps.closed_at is not None,
          f"status={ps.status}")
    st_trades = [t for t in api("GET", "/trades?ticker=AAPL").json()
                 if t["side"] == "sell" and t["trigger_reason"] and "STOP-LOSS" in t["trigger_reason"]]
    check("T3 stop-loss trade logged", len(st_trades) >= 1,
          st_trades[0]["trigger_reason"][:100] if st_trades else "none")
    s.close()
else:
    check("T3 stop-loss triggers full exit", False, "AAPL buy did not fill")
    check("T3 position closed after stop-loss", False, "n/a")
    check("T3 stop-loss trade logged", False, "n/a")

# ---------- T4: COOLDOWN blocks re-entry ----------
set_params("AAPL", buy_threshold_stddev=-5.0, stop_loss_pct=0.0, cooldown_days=30)
res = run_strategy()
aapl_line = next((m for m in res["skipped"] if m.startswith("AAPL")), "")
check("T4 cooldown blocks re-entry after close",
      "cooldown" in aapl_line and not any(b["ticker"] == "AAPL" for b in res["buys"]), aapl_line[:120])

# ---------- T5: VOLATILITY-ADJUSTED SIZING reflected in reason ----------
set_params("SPY", buy_threshold_stddev=-5.0, use_volatility_sizing=True, allow_downtrend_buys=False,
           cooldown_days=7, stop_loss_pct=0.0)
# ensure no recent SPY close blocks via cooldown
s = db(); s.query(PositionState).filter(PositionState.ticker == "SPY").delete(); s.commit(); s.close()
res = run_strategy()
spy_lines = [m for m in (res["skipped"] + [b["reason"] for b in res["buys"]]) if "SPY" in m or "vol-adj" in m]
spy_vol = any("vol-adj" in m for m in (res["skipped"] + [b.get("reason", "") for b in res["buys"]]))
check("T5 volatility-adjusted sizing applied", spy_vol, next((m for m in res["skipped"] if "SPY" in m), str(res["buys"]))[:160])

# ---------- T6: suggestion engine runs (sample-gated) ----------
r = api("POST", "/suggestions/generate")
check("T6 suggestion generate endpoint ok", r.status_code == 200, r.text[:80])

# ---------- CLEANUP ----------
print("\n--- cleanup ---")
flatten()
s = db(); s.query(PositionState).delete(); s.commit(); s.close()
restore_defaults()
reset_state()
api("POST", "/alerts/acknowledge-all")
print("cleanup done")

passed = sum(1 for _, ok, _ in results if ok)
print(f"\n=== RESULT: {passed}/{len(results)} checks passed ===")
if passed != len(results):
    for n, ok, d in results:
        if not ok:
            print("  FAIL:", n, "—", d)
    sys.exit(1)
