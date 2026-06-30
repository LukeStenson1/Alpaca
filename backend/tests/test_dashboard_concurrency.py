"""
Backend pytest covering:
- Health / connectivity
- The 5 Alpaca-backed dashboard endpoints under concurrent load (regression check)
- Sidebar / nav supporting endpoints (research, settings, history)
- Influencer endpoints (scan should return HTTP 400 — YouTube key not configured)
"""
import os
import time
import concurrent.futures as cf

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # fall back to frontend .env when invoked directly
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------- health ----------------
def test_root(session):
    r = session.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_system_state(session):
    r = session.get(f"{API}/system/state", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "trading_mode" in d and "kill_switch_engaged" in d


# ---------------- concurrency regression ----------------
DASH_ENDPOINTS = [
    "/account", "/positions", "/portfolio/flags",
    "/portfolio/sectors", "/portfolio/benchmark",
]


def _hit(path):
    t0 = time.time()
    r = requests.get(f"{API}{path}", timeout=20)
    return path, r.status_code, time.time() - t0


@pytest.mark.parametrize("path", DASH_ENDPOINTS)
def test_dashboard_endpoint_ok(session, path):
    r = session.get(f"{API}{path}", timeout=20)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"


def test_dashboard_concurrent_load():
    """3 rounds, 5 endpoints fired in parallel — must not 502/timeout."""
    failures = []
    slow = []
    for round_no in range(3):
        with cf.ThreadPoolExecutor(max_workers=len(DASH_ENDPOINTS)) as ex:
            futs = [ex.submit(_hit, p) for p in DASH_ENDPOINTS]
            for f in cf.as_completed(futs):
                path, code, dur = f.result()
                if code != 200:
                    failures.append((round_no, path, code))
                if dur > 5.0:
                    slow.append((round_no, path, round(dur, 2)))
    assert not failures, f"Non-200 responses: {failures}"
    # informational
    if slow:
        print(f"slow responses (>5s): {slow}")


# ---------------- nav-supporting endpoints ----------------
def test_watchlist_list(session):
    r = session.get(f"{API}/watchlist", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_trades_list(session):
    r = session.get(f"{API}/trades", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_reports_pnl(session):
    r = session.get(f"{API}/reports/pnl?period=month", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("period") == "month" and "rows" in d


def test_strategy_config(session):
    r = session.get(f"{API}/strategy/config", timeout=15)
    assert r.status_code == 200
    assert "buy_threshold_stddev" in r.json()


def test_alerts(session):
    r = session.get(f"{API}/alerts", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------------- watchlist CRUD ----------------
def test_watchlist_add_update_delete(session):
    # cleanup if exists
    session.delete(f"{API}/watchlist/TSLA", timeout=15)

    r = session.get(f"{API}/watchlist/validate?ticker=TSLA", timeout=15)
    assert r.status_code == 200 and r.json().get("valid") is True

    r = session.post(f"{API}/watchlist", json={"ticker": "TSLA", "conviction": 4,
                                               "thesis": "TEST_ thesis"}, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["ticker"] == "TSLA"

    r = session.put(f"{API}/watchlist/TSLA", json={"conviction": 5, "sector": "Auto"}, timeout=15)
    assert r.status_code == 200 and r.json()["conviction"] == 5

    # verify GET
    r = session.get(f"{API}/watchlist", timeout=15)
    rec = next((w for w in r.json() if w["ticker"] == "TSLA"), None)
    assert rec and rec["conviction"] == 5 and rec["sector"] == "Auto"

    r = session.delete(f"{API}/watchlist/TSLA", timeout=15)
    assert r.status_code == 200


# ---------------- influencer endpoints ----------------
def test_influencer_status(session):
    r = session.get(f"{API}/influencers/status", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "configured" in d and "youtube_key" in d
    # YouTube key NOT configured per problem statement -> scan should be blocked
    assert d["youtube_key"] is False
    assert d["configured"] is False


def test_influencer_channels_seeded(session):
    r = session.get(f"{API}/influencers/channels", timeout=15)
    assert r.status_code == 200
    chans = r.json()
    assert isinstance(chans, list) and len(chans) >= 2


def test_influencer_channel_add_toggle_delete(session):
    r = session.post(f"{API}/influencers/channels",
                     json={"query": "TEST_channel_handle", "name": "TEST_ Channel"}, timeout=15)
    assert r.status_code == 200
    cid = r.json()["id"]

    r = session.post(f"{API}/influencers/channels/{cid}/toggle", timeout=15)
    assert r.status_code == 200 and r.json()["active"] is False

    r = session.delete(f"{API}/influencers/channels/{cid}", timeout=15)
    assert r.status_code == 200


def test_influencer_scan_blocked(session):
    r = session.post(f"{API}/influencers/scan", timeout=15)
    # YouTube key not configured — must return 400 (this is EXPECTED, treat as pass)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"


# ---------------- settings: safety limits + mode ----------------
def test_set_mode_paper(session):
    r = session.post(f"{API}/system/mode", json={"mode": "paper"}, timeout=15)
    assert r.status_code == 200 and r.json()["trading_mode"] == "paper"


def test_set_live_requires_confirmation(session):
    r = session.post(f"{API}/system/mode",
                     json={"mode": "live", "confirmation": "WRONG"}, timeout=15)
    assert r.status_code == 400


def test_safety_limits_save(session):
    payload = {"max_daily_loss_usd": 500.0, "max_total_exposure_usd": 50000.0,
               "schedule_frequency": "daily", "baseline_volatility": 0.02,
               "benchmark_ticker": "SPY", "rebalance_threshold_pct": 0.20}
    r = session.put(f"{API}/system/safety-limits", json=payload, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["max_daily_loss_usd"] == 500.0 and d["benchmark_ticker"] == "SPY"


def test_kill_switch_toggle(session):
    r = session.post(f"{API}/system/kill-switch",
                     json={"engaged": True, "reason": "TEST_ regression"}, timeout=15)
    assert r.status_code == 200 and r.json()["kill_switch_engaged"] is True
    r = session.post(f"{API}/system/kill-switch", json={"engaged": False}, timeout=15)
    assert r.status_code == 200 and r.json()["kill_switch_engaged"] is False
