from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey
)
from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Watchlist(Base):
    __tablename__ = "watchlist"
    ticker = Column(String, primary_key=True)
    date_added = Column(DateTime, default=utcnow)
    active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    sector = Column(String, nullable=True)
    name = Column(String, nullable=True)  # company name from Alpaca asset lookup


class Parameters(Base):
    __tablename__ = "parameters"
    ticker = Column(String, ForeignKey("watchlist.ticker"), primary_key=True)
    buy_threshold_stddev = Column(Float, default=2.0)
    lookback_days = Column(Integer, default=150)
    sell_tranche_pct = Column(Float, default=0.25)
    sell_gain_steps = Column(JSON, default=lambda: [0.05, 0.10, 0.20, 0.30])
    max_position_size_usd = Column(Float, default=1000.0)
    # --- v2 risk / valuation additions ---
    stop_loss_pct = Column(Float, default=0.0)          # 0 disables stop-loss
    max_hold_days = Column(Integer, nullable=True)       # None disables staleness flag
    use_volatility_sizing = Column(Boolean, default=False)
    use_52w_range = Column(Boolean, default=False)
    range_pct = Column(Float, default=0.15)              # buy only in bottom X of 52w range
    allow_downtrend_buys = Column(Boolean, default=False)  # override 200d MA trend filter
    cooldown_days = Column(Integer, default=7)           # re-entry cooldown after a close
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, index=True)
    side = Column(String)  # buy / sell
    quantity = Column(Float)
    price = Column(Float)
    timestamp = Column(DateTime, default=utcnow, index=True)
    order_id = Column(String, nullable=True)
    trigger_reason = Column(Text)
    params_snapshot = Column(JSON, nullable=True)
    realized_pnl = Column(Float, nullable=True)  # set on sell tranches


class PositionState(Base):
    """Tracks tranche execution state for an open strategy position."""
    __tablename__ = "position_states"
    ticker = Column(String, primary_key=True)
    original_qty = Column(Float, default=0.0)
    avg_entry_price = Column(Float, default=0.0)
    tranches_executed = Column(JSON, default=lambda: [])  # list of step indices already sold
    opened_at = Column(DateTime, default=utcnow)
    closed_at = Column(DateTime, nullable=True)
    realized_pnl = Column(Float, default=0.0)
    entry_order_id = Column(String, nullable=True)  # limit buy order id, for fill reconciliation
    status = Column(String, default="open")  # open / closed


class Suggestion(Base):
    __tablename__ = "suggestions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, index=True)
    suggested_param = Column(String)
    current_value = Column(Float)
    suggested_value = Column(Float)
    rationale = Column(Text)
    status = Column(String, default="pending")  # pending / approved / rejected
    created_at = Column(DateTime, default=utcnow)


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=utcnow, index=True)
    equity = Column(Float)
    cash = Column(Float)
    buying_power = Column(Float)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String)  # kill_switch / order_failure / mode_switch / safety / info
    severity = Column(String, default="info")  # info / warning / critical
    message = Column(Text)
    created_at = Column(DateTime, default=utcnow, index=True)
    acknowledged = Column(Boolean, default=False)


class SystemState(Base):
    """Singleton row (id=1) holding global toggles and safety limits."""
    __tablename__ = "system_state"
    id = Column(Integer, primary_key=True)
    kill_switch_engaged = Column(Boolean, default=False)
    kill_switch_reason = Column(Text, nullable=True)
    trading_mode = Column(String, default="paper")  # paper / live
    max_daily_loss_usd = Column(Float, default=500.0)
    max_total_exposure_usd = Column(Float, default=10000.0)
    day_start_equity = Column(Float, nullable=True)
    day_start_date = Column(String, nullable=True)  # YYYY-MM-DD
    scheduler_enabled = Column(Boolean, default=True)
    # --- v2 long-term additions ---
    schedule_frequency = Column(String, default="daily")   # daily / weekly
    schedule_timing = Column(String, default="before_open")  # before_open / after_close
    baseline_volatility = Column(Float, default=0.02)      # for volatility-adjusted sizing
    benchmark_ticker = Column(String, default="SPY")
    rebalance_threshold_pct = Column(Float, default=0.20)  # flag if a position exceeds this share
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
