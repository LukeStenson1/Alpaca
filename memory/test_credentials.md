# Test Credentials

## Authentication
This is a single-user personal app — **no login / no auth**. The dashboard is open at the root URL.

## Alpaca (paper) — configured in /app/backend/.env
- ALPACA_ENV defaults to `paper`
- Paper account is connected (equity ~$100,000)
- Live keys are stored but app is locked to PAPER until user types "CONFIRM LIVE" in Settings.

## Notes for testing
- To FORCE a buy on a ticker (for testing order placement), set its `buy_threshold_stddev` to a negative
  value (e.g. -5) via `PUT /api/parameters/{ticker}`. This makes the buy trigger price sit far above the
  current price so a buy fires on the next strategy run. Reset it to ~2.0 afterward.
- Strategy runs automatically every 20 min; a manual "Run Strategy Now" button is on Overview
  (`POST /api/strategy/run`).
