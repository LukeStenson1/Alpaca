# PRD — Personal Mean-Reversion Trading Dashboard

## Problem Statement (original)
Single-user trading dashboard: editable watchlist; Alpaca paper/live (env-toggled) for price data + orders;
mean-reversion buys (price <= rolling_mean − N·stddev); scale-out sell ladder (sell tranche % at each gain step,
trailing exit floor up); every trade tracked with trigger_reason + params_snapshot; periodic rule-based suggestion
engine proposes threshold changes (PENDING, manual approve/reject, no auto-apply); dashboard pages
(Overview, Watchlist, Trade History, Suggestions, Settings); manual kill switch; safety rails before live.

## User & choices
- Single user, no auth/signup.
- DB: **SQLite** (SQLAlchemy). File: /app/backend/trading.db
- Alpaca **paper** keys provided & connected (~$100k equity). Live keys stored but app locked to paper until "CONFIRM LIVE".
- No email — alerts surfaced in-dashboard only.
- Scheduler: both APScheduler (every 20 min) + manual "Run Strategy Now".

## Architecture
- Backend: FastAPI + SQLAlchemy(SQLite) + APScheduler + alpaca-py. All routes under /api.
  - models.py: watchlist, parameters, trades, position_states, suggestions, account_snapshots, alerts, system_state(singleton)
  - alpaca_service.py: paper/live client factory, account/positions/orders/daily bars(IEX)/latest price/clock
  - strategy.py: mean-reversion buy (notional sizing), scale-out sell ladder w/ tranche tracking, day baseline,
    daily-loss auto-kill, per-ticker max size + global exposure caps, alert logging
  - suggestions.py: rule-based, explainable suggestions + apply
  - scheduler.py: 20-min strategy job + weekly suggestion job
- Frontend: React (CRA) + Tailwind + recharts + lucide. Swiss/high-contrast "Terminal" theme, font-mono for data.
  Pages: Overview, Watchlist, Trade History, Suggestions, Settings. Persistent header kill switch + alerts bell + mode badge.

## Implemented (2026-06-30)
- ✅ All data-model tables + seed (AAPL/MSFT/SPY) + singleton system_state
- ✅ Alpaca paper integration (account/positions/orders/bars) — connected & verified
- ✅ Buy + sell strategy logic, manual + scheduled runs
- ✅ Safety rails: per-ticker max size, global exposure cap, max-daily-loss auto kill switch, order-failure alerts
- ✅ Kill switch (manual halt) + halted banner
- ✅ Rule-based suggestion engine + approve/reject (manual apply only)
- ✅ Settings: paper/live toggle with typed "CONFIRM LIVE", safety limits, scheduler toggle
- ✅ Full dashboard UI; 15/15 backend tests + frontend e2e passed

## Backlog / Next
- P1: Sell-ladder live validation needs a profitable position to fully exercise (logic unit-correct; not e2e-triggered).
- P1: Email/SMS alerting (deferred per user).
- P2: Realized P&L per closed position; suggestion engine richer heuristics with more trade volume.
- P2: Auth/lock screen if ever exposed publicly.
- Reminder: extensive paper testing before any live use.

## Update (2026-06-30, session 2)
- ✅ Sell ladder validated LIVE on paper: real paper sell order fired (tranche 1/4 at +6.7%), tranche tracked
     (no double-sell), realized P&L $15.68 logged. SPY tracking state afterward reset to reflect real holdings.
- ✅ Realized P&L per closed position added:
     - models: PositionState.realized_pnl + closed_at; Trade.realized_pnl
     - strategy: accumulates realized on each sell tranche; sets closed_at on full close
     - API: GET /api/positions/closed, GET /api/pnl/summary; realized_pnl in /api/trades
     - server._migrate(): additive SQLite ALTER for new columns
     - UI: Overview "Realized P&L" stat + "Closed Positions" table; Trade History realized-P&L column
- Email/SMS alerting kept DEFERRED per user (dashboard alerts only).

## Update (2026-06-30, session 3) — Extensive paper testing
- Built /app/backend/tests/paper_e2e.py: 21-check live paper harness (flattens account first, cleans up after).
- RESULT: 21/21 passing. Covers: forced buy + trade log + position_state; no re-buy at per-ticker cap;
  multi-tranche sell -> FULL CLOSE + realized P&L + closed-position record + pnl summary; global exposure cap;
  max-daily-loss auto-engaging kill switch + critical alert; manual kill switch halt; suggestion engine
  generate + approve applies to parameters.
- BUG FOUND & FIXED: when price clears multiple sell steps in one run, placing sequential market sells
  triggered Alpaca "insufficient qty / wash trade" rejects (shares held by the first order). Fixed in
  strategy._evaluate_sells by AGGREGATING all qualifying tranches into a SINGLE sell order
  (reason e.g. "tranches 1, 2 of 4 at +X% gain"). Verified via the harness (full close in one run).
- Account left flat & clean; mode=paper; live still gated behind typed "CONFIRM LIVE".
