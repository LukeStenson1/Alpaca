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
    conviction = Column(Integer, default=3)  # 1-5 manual conviction (influencer/quality)
    thesis = Column(Text, nullable=True)     # why you own it
    next_earnings_date = Column(String, nullable=True)  # YYYY-MM-DD (manual for now)


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


class InfluencerChannel(Base):
    """A YouTube channel to scan for stock ideas."""
    __tablename__ = "influencer_channels"
    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String)        # search query / handle used to resolve the channel
    name = Column(String)         # display name
    channel_id = Column(String, nullable=True)  # resolved YouTube channel id (cached)
    active = Column(Boolean, default=True)
    last_scanned_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class InfluencerIdea(Base):
    """A stock idea extracted by the LLM from an influencer's video."""
    __tablename__ = "influencer_ideas"
    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_name = Column(String)
    video_id = Column(String, index=True)
    video_title = Column(Text)
    video_url = Column(String)
    published_at = Column(String, nullable=True)
    ticker = Column(String, index=True)
    company = Column(String, nullable=True)
    signal = Column(String)        # bull / bear / neutral
    conviction = Column(Integer)   # 1-5 (LLM-assessed)
    thesis = Column(Text)
    action = Column(String)        # added / updated / advisory
    status = Column(String, default="pending")  # pending / dismissed
    created_at = Column(DateTime, default=utcnow)


class GlobalStrategy(Base):
    """Singleton (id=1) — one strategy config applied to ALL stocks."""
    __tablename__ = "global_strategy"
    id = Column(Integer, primary_key=True)
    buy_threshold_stddev = Column(Float, default=2.0)
    lookback_days = Column(Integer, default=150)
    sell_tranche_pct = Column(Float, default=0.25)
    sell_gain_steps = Column(JSON, default=lambda: [0.10, 0.20, 0.35, 0.50])
    max_position_size_usd = Column(Float, default=1000.0)
    stop_loss_pct = Column(Float, default=0.20)
    cooldown_days = Column(Integer, default=14)
    max_hold_days = Column(Integer, nullable=True)
    use_52w_range = Column(Boolean, default=True)
    range_pct = Column(Float, default=0.30)
    allow_downtrend_buys = Column(Boolean, default=False)
    use_volatility_sizing = Column(Boolean, default=True)
    # long-term / quality shift
    investing_style = Column(String, default="blended")  # longterm / blended / tactical
    min_conviction_to_buy = Column(Integer, default=3)   # only buy names rated >= this
    earnings_blackout_days = Column(Integer, default=5)  # don't buy within N days of earnings
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)



class Fundamentals(Base):
    """Cached FMP fundamentals per symbol (refreshed ~daily)."""
    __tablename__ = "fundamentals"
    symbol = Column(String, primary_key=True)
    pe_ratio = Column(Float, nullable=True)
    profit_margin = Column(Float, nullable=True)
    operating_margin = Column(Float, nullable=True)
    revenue_growth = Column(Float, nullable=True)
    earnings_growth = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    is_etf = Column(Boolean, default=False)
    error = Column(String, nullable=True)
    fetched_at = Column(DateTime, default=utcnow)
