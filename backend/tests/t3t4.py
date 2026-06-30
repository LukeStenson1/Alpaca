import sys
from datetime import datetime, timezone, timedelta
import requests
sys.path.insert(0, "/app/backend")
from database import SessionLocal
from models import Parameters, PositionState, Trade, SystemState
import strategy
from alpaca_service import get_service

BASE = "http://localhost:8001/api"
svc = get_service("paper")
out = []
def chk(n, c, d=""):
    out.append((n, bool(c))); print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f" — {d}" if d else ""))
def db(): return SessionLocal()

now = datetime.now(timezone.utc)

# ---- T3 STOP-LOSS: full code path with stubbed order (market closed -> stub fill) ----
orig_sell = svc.submit_sell_qty
svc.submit_sell_qty = lambda tk, qty: {"id": "TEST-STOP", "status": "accepted", "qty": qty}
s = db()
s.query(PositionState).filter(PositionState.ticker == "AAPL").delete()
s.query(Trade).filter(Trade.order_id == "TEST-STOP").delete()
ps = PositionState(ticker="AAPL", original_qty=3.0, avg_entry_price=300.0,
                   tranches_executed=[], opened_at=now, status="open")
s.add(ps)
p = s.query(Parameters).get("AAPL"); p.stop_loss_pct = 0.10; s.commit()
fab = {"ticker": "AAPL", "qty": 3.0, "avg_entry_price": 300.0, "current_price": 300.0 * 0.85,
       "market_value": 3.0 * 255, "cost_basis": 900, "unrealized_pl": -135, "unrealized_plpc": -0.15}
summ = {"sells": [], "errors": []}
snap = strategy._params_snapshot(p)
stopped = strategy._check_stop_loss(s, svc, "AAPL", p, snap, ps, fab, summ)
s.commit(); s.refresh(ps)
chk("T3 stop-loss fires when price <= entry*(1-stop)", stopped and summ["sells"][0].get("stop_loss"), str(summ["sells"])[:110])
chk("T3 realized loss recorded (~-135)", abs((ps.realized_pnl or 0) - (-135)) < 1, f"realized={ps.realized_pnl}")
chk("T3 position closed", ps.status == "closed" and ps.closed_at is not None, ps.status)
st = [t for t in requests.get(BASE + "/trades?ticker=AAPL").json()
      if t["side"] == "sell" and "STOP-LOSS" in (t["trigger_reason"] or "")]
chk("T3 stop-loss trade logged", len(st) >= 1, st[0]["trigger_reason"][:80] if st else "none")
svc.submit_sell_qty = orig_sell
# leave AAPL closed (closed_at=now) for the cooldown test
s.commit(); s.close()

# ---- T4 COOLDOWN: recent close should block re-entry ----
s = db(); p = s.query(Parameters).get("AAPL")
p.cooldown_days = 30; p.stop_loss_pct = 0.0; p.buy_threshold_stddev = -5.0; s.commit(); s.close()
res = requests.post(BASE + "/strategy/run").json()
line = next((m for m in res["skipped"] if m.startswith("AAPL")), "")
chk("T4 cooldown blocks re-entry", "cooldown" in line and not any(b["ticker"] == "AAPL" for b in res["buys"]), line[:110])

# ---- cleanup ----
s = db()
s.query(Trade).filter(Trade.order_id == "TEST-STOP").delete()
s.query(PositionState).delete()
for tk in ["AAPL", "MSFT", "SPY"]:
    pp = s.query(Parameters).get(tk)
    if pp:
        pp.buy_threshold_stddev = 2.0; pp.stop_loss_pct = 0.0; pp.cooldown_days = 7
        pp.allow_downtrend_buys = False; pp.use_volatility_sizing = False; pp.use_52w_range = False
s.commit(); s.close()
requests.post(BASE + "/alerts/acknowledge-all")
passed = sum(1 for _, ok in out if ok)
print(f"\n=== {passed}/{len(out)} passed ===")
