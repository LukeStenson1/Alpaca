"""
Backend integration tests for the trading dashboard.
Targets the public REACT_APP_BACKEND_URL with /api prefix.
"""
import os
import time
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

TEST_TICKER = "NVDA"  # used for watchlist CRUD and force-buy


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------- system / account ----------------
class TestSystemAndAccount:
    def test_root(self, client):
        r = client.get(f"{API}/")
        assert r.status_code == 200

    def test_system_state(self, client):
        r = client.get(f"{API}/system/state")
        assert r.status_code == 200
        d = r.json()
        assert d["trading_mode"] == "paper"
        assert "kill_switch_engaged" in d
        assert "max_daily_loss_usd" in d
        assert "max_total_exposure_usd" in d
        assert "scheduler_enabled" in d

    def test_account(self, client):
        r = client.get(f"{API}/account")
        assert r.status_code == 200
        d = r.json()
        assert d["connected"] is True, f"Alpaca not connected: {d}"
        assert d["mode"] == "paper"
        for k in ("equity", "cash", "buying_power", "today_pl"):
            assert k in d

    def test_positions(self, client):
        r = client.get(f"{API}/positions")
        assert r.status_code == 200
        d = r.json()
        assert "positions" in d
        assert isinstance(d["positions"], list)


# ---------------- watchlist + parameters ----------------
class TestWatchlistCRUD:
    def test_seeded_list(self, client):
        r = client.get(f"{API}/watchlist")
        assert r.status_code == 200
        tickers = [w["ticker"] for w in r.json()]
        for t in ("AAPL", "MSFT", "SPY"):
            assert t in tickers
        # Each row must include parameters
        for w in r.json():
            assert w["parameters"] is not None
            assert "buy_threshold_stddev" in w["parameters"]

    def test_add_update_delete(self, client):
        # Cleanup if already present
        client.delete(f"{API}/watchlist/{TEST_TICKER}")

        # POST add
        r = client.post(f"{API}/watchlist", json={"ticker": TEST_TICKER.lower()})
        assert r.status_code == 200
        assert r.json()["ticker"] == TEST_TICKER

        # Verify in list + auto-created params
        r = client.get(f"{API}/watchlist")
        item = next((w for w in r.json() if w["ticker"] == TEST_TICKER), None)
        assert item is not None
        assert item["parameters"] is not None

        # PUT toggle active false
        r = client.put(f"{API}/watchlist/{TEST_TICKER}", json={"active": False})
        assert r.status_code == 200
        assert r.json()["active"] is False

        # DELETE
        r = client.delete(f"{API}/watchlist/{TEST_TICKER}")
        assert r.status_code == 200
        r = client.get(f"{API}/watchlist")
        assert TEST_TICKER not in [w["ticker"] for w in r.json()]

    def test_update_parameters_sort_sell_steps(self, client):
        payload = {
            "buy_threshold_stddev": 2.5,
            "lookback_days": 25,
            "sell_tranche_pct": 0.2,
            "sell_gain_steps": [0.30, 0.05, 0.10],
            "max_position_size_usd": 1500.0,
        }
        r = client.put(f"{API}/parameters/AAPL", json=payload)
        assert r.status_code == 200
        d = r.json()
        assert d["buy_threshold_stddev"] == 2.5
        assert d["lookback_days"] == 25
        assert d["sell_gain_steps"] == sorted(payload["sell_gain_steps"])
        # restore
        client.put(f"{API}/parameters/AAPL", json={
            "buy_threshold_stddev": 2.0, "lookback_days": 30,
            "sell_tranche_pct": 0.25,
            "sell_gain_steps": [0.05, 0.10, 0.20, 0.30],
            "max_position_size_usd": 1000.0,
        })


# ---------------- force buy + trade logging ----------------
class TestForceBuyFlow:
    def test_force_buy_and_log(self, client):
        # Use SPY since it's high liquidity and seeded
        ticker = "SPY"
        # set threshold deeply negative to force buy
        r = client.put(f"{API}/parameters/{ticker}", json={"buy_threshold_stddev": -5.0})
        assert r.status_code == 200

        try:
            trades_before = client.get(f"{API}/trades?ticker={ticker}").json()
            r = client.post(f"{API}/strategy/run")
            assert r.status_code == 200
            result = r.json()
            print("strategy result:", result)
            assert result.get("halted") in (False, None)

            buys = result.get("buys", [])
            # Soft assertion - may fail if market closed or other rails kick in
            if not buys:
                pytest.skip(f"No buys produced; full result={result}")
            assert any(b.get("ticker") == ticker for b in buys), f"No buy for {ticker} in {buys}"

            # Wait a moment for trade row commit
            time.sleep(2)
            trades_after = client.get(f"{API}/trades?ticker={ticker}").json()
            assert len(trades_after) > len(trades_before)
            t = trades_after[0]
            assert t["side"] == "buy"
            assert t["trigger_reason"]
            assert t["params_snapshot"]
        finally:
            # always reset threshold
            client.put(f"{API}/parameters/{ticker}", json={"buy_threshold_stddev": 2.0})


# ---------------- kill switch ----------------
class TestKillSwitch:
    def test_kill_switch_halts(self, client):
        r = client.post(f"{API}/system/kill-switch", json={"engaged": True, "reason": "test"})
        assert r.status_code == 200
        assert r.json()["kill_switch_engaged"] is True

        r = client.post(f"{API}/strategy/run")
        assert r.status_code == 200
        d = r.json()
        assert d.get("halted") is True
        assert not d.get("buys") and not d.get("sells")

        # release
        r = client.post(f"{API}/system/kill-switch", json={"engaged": False})
        assert r.status_code == 200
        assert r.json()["kill_switch_engaged"] is False

        # alert logged
        alerts = client.get(f"{API}/alerts").json()
        assert any(a["type"] == "kill_switch" for a in alerts)


# ---------------- safety limits ----------------
class TestSafetyLimits:
    def test_safety_limits_update(self, client):
        before = client.get(f"{API}/system/state").json()
        new_dl = (before["max_daily_loss_usd"] or 500.0) + 1.0
        new_exp = (before["max_total_exposure_usd"] or 10000.0) + 100.0
        r = client.put(f"{API}/system/safety-limits", json={
            "max_daily_loss_usd": new_dl,
            "max_total_exposure_usd": new_exp,
            "scheduler_enabled": True,
        })
        assert r.status_code == 200
        d = r.json()
        assert d["max_daily_loss_usd"] == new_dl
        assert d["max_total_exposure_usd"] == new_exp
        assert d["scheduler_enabled"] is True
        # restore
        client.put(f"{API}/system/safety-limits", json={
            "max_daily_loss_usd": before["max_daily_loss_usd"],
            "max_total_exposure_usd": before["max_total_exposure_usd"],
            "scheduler_enabled": before["scheduler_enabled"],
        })


# ---------------- mode switch confirmation ----------------
class TestModeSwitch:
    def test_mode_switch_validations(self, client):
        # no confirmation
        r = client.post(f"{API}/system/mode", json={"mode": "live"})
        assert r.status_code == 400
        # wrong confirmation
        r = client.post(f"{API}/system/mode", json={"mode": "live", "confirmation": "WRONG"})
        assert r.status_code == 400
        # correct
        r = client.post(f"{API}/system/mode", json={"mode": "live", "confirmation": "CONFIRM LIVE"})
        assert r.status_code == 200
        assert r.json()["trading_mode"] == "live"
        # alert logged
        alerts = client.get(f"{API}/alerts").json()
        assert any(a["type"] == "mode_switch" for a in alerts)
        # back to paper
        r = client.post(f"{API}/system/mode", json={"mode": "paper"})
        assert r.status_code == 200
        assert r.json()["trading_mode"] == "paper"


# ---------------- trade filters ----------------
class TestTradeFilters:
    def test_ticker_filter(self, client):
        r = client.get(f"{API}/trades?ticker=AAPL")
        assert r.status_code == 200
        rows = r.json()
        for row in rows:
            assert row["ticker"] == "AAPL"

    def test_date_range(self, client):
        start = "2020-01-01T00:00:00"
        end = datetime.now(timezone.utc).isoformat().replace("+00:00", "")
        r = client.get(f"{API}/trades", params={"start": start, "end": end})
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------- suggestions ----------------
class TestSuggestions:
    def test_generate_and_list(self, client):
        r = client.post(f"{API}/suggestions/generate")
        assert r.status_code == 200
        assert "created" in r.json()

        r = client.get(f"{API}/suggestions?status=pending")
        assert r.status_code == 200
        pending = r.json()
        assert isinstance(pending, list)

        if pending:
            sid = pending[0]["id"]
            # reject path on the first one
            r = client.post(f"{API}/suggestions/{sid}/reject")
            assert r.status_code == 200
            assert r.json()["status"] == "rejected"


# ---------------- alerts ----------------
class TestAlerts:
    def test_alerts_and_ack(self, client):
        r = client.get(f"{API}/alerts")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

        r = client.post(f"{API}/alerts/acknowledge-all")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

        # unack count should be 0
        s = client.get(f"{API}/system/state").json()
        assert s["unacknowledged_alerts"] == 0
