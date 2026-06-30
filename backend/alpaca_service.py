import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

PAPER_KEY = os.environ.get("ALPACA_API_KEY_PAPER")
PAPER_SECRET = os.environ.get("ALPACA_SECRET_KEY_PAPER")
LIVE_KEY = os.environ.get("ALPACA_API_KEY_LIVE")
LIVE_SECRET = os.environ.get("ALPACA_SECRET_KEY_LIVE")

_cache = {}


class AlpacaService:
    def __init__(self, mode="paper"):
        self.mode = mode
        if mode == "live":
            self.key, self.secret = LIVE_KEY, LIVE_SECRET
        else:
            self.key, self.secret = PAPER_KEY, PAPER_SECRET
        self.trading = TradingClient(self.key, self.secret, paper=(mode != "live"))
        self.data = StockHistoricalDataClient(self.key, self.secret)

    # ---------- account / positions ----------
    def get_account(self):
        a = self.trading.get_account()
        return {
            "equity": float(a.equity),
            "last_equity": float(a.last_equity),
            "cash": float(a.cash),
            "buying_power": float(a.buying_power),
            "portfolio_value": float(a.portfolio_value),
            "status": str(a.status),
        }

    def get_positions(self):
        out = []
        for p in self.trading.get_all_positions():
            out.append({
                "ticker": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "cost_basis": float(p.cost_basis),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
            })
        return out

    def get_position(self, ticker):
        for p in self.get_positions():
            if p["ticker"] == ticker:
                return p
        return None

    # ---------- market data ----------
    def get_daily_closes(self, ticker, lookback_days):
        start = datetime.now(timezone.utc) - timedelta(days=lookback_days * 2 + 10)
        req = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame.Day,
            start=start,
            feed=DataFeed.IEX,
        )
        bars = self.data.get_stock_bars(req)
        data = bars.data.get(ticker, [])
        closes = [float(b.close) for b in data]
        return closes[-lookback_days:] if len(closes) > lookback_days else closes

    def get_latest_price(self, ticker):
        req = StockLatestTradeRequest(symbol_or_symbols=ticker, feed=DataFeed.IEX)
        res = self.data.get_stock_latest_trade(req)
        return float(res[ticker].price)

    def get_daily_bars(self, ticker, days):
        """Return up to `days` most recent daily bars as dicts with close/high/low."""
        start = datetime.now(timezone.utc) - timedelta(days=int(days * 1.6) + 15)
        req = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame.Day,
            start=start,
            feed=DataFeed.IEX,
        )
        bars = self.data.get_stock_bars(req)
        data = bars.data.get(ticker, [])
        rows = [{"close": float(b.close), "high": float(b.high), "low": float(b.low)} for b in data]
        return rows[-days:] if len(rows) > days else rows

    # ---------- orders ----------
    def submit_buy_notional(self, ticker, notional):
        req = MarketOrderRequest(
            symbol=ticker,
            notional=round(notional, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        o = self.trading.submit_order(req)
        return {"id": str(o.id), "status": str(o.status), "qty": float(o.qty or 0)}

    def submit_buy_limit(self, ticker, qty, limit_price):
        """Limit BUY. Alpaca requires integer qty for limit orders."""
        req = LimitOrderRequest(
            symbol=ticker,
            qty=int(qty),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=round(float(limit_price), 2),
        )
        o = self.trading.submit_order(req)
        return {"id": str(o.id), "status": str(o.status), "qty": float(o.qty or 0)}

    def get_open_orders(self, ticker=None):
        kwargs = {"status": QueryOrderStatus.OPEN}
        if ticker:
            kwargs["symbols"] = [ticker]
        return self.trading.get_orders(filter=GetOrdersRequest(**kwargs))

    def cancel_all_orders(self):
        try:
            self.trading.cancel_orders()
        except Exception:
            pass

    def submit_sell_qty(self, ticker, qty):
        req = MarketOrderRequest(
            symbol=ticker,
            qty=round(qty, 6),
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        o = self.trading.submit_order(req)
        return {"id": str(o.id), "status": str(o.status), "qty": float(o.qty or 0)}

    def cancel_order(self, order_id):
        self.trading.cancel_order_by_id(order_id)

    def get_clock(self):
        c = self.trading.get_clock()
        return {"is_open": bool(c.is_open), "next_open": str(c.next_open), "next_close": str(c.next_close)}

    def get_asset(self, symbol):
        """Validate/lookup a tradable equity. Raises if the symbol does not exist."""
        a = self.trading.get_asset(symbol.upper())
        return {
            "symbol": a.symbol,
            "name": a.name,
            "tradable": bool(a.tradable),
            "exchange": str(a.exchange),
            "status": str(a.status),
            "fractionable": bool(getattr(a, "fractionable", False)),
        }


def get_service(mode="paper"):
    if mode not in _cache:
        _cache[mode] = AlpacaService(mode)
    return _cache[mode]
