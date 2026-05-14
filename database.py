# database.py
# MarketOS — Database Schema
# FIXED: Creates all folders and tables automatically on import

import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Float, String,
    Date, Integer, Text, Boolean, DateTime
)
from sqlalchemy.orm import declarative_base, sessionmaker

# ── Create ALL required folders before anything else ─────────────
for folder in ["data", "data/raw", "data/processed", "data/models",
               "outputs", "logs"]:
    os.makedirs(folder, exist_ok=True)

# ── Database connection ───────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/marketos.db")
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}  # needed for SQLite
)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ─────────────────────────────────────────────────────────────────
# TABLE 1: Daily stock prices
# ─────────────────────────────────────────────────────────────────
class DailyPrice(Base):
    __tablename__ = "daily_prices"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    date         = Column(Date,    nullable=False, index=True)
    ticker       = Column(String(30), nullable=False, index=True)
    company_name = Column(String(100))
    sector       = Column(String(80),  index=True)
    subsector    = Column(String(80),  index=True)
    open_price   = Column(Float, default=0.0)
    high_price   = Column(Float, default=0.0)
    low_price    = Column(Float, default=0.0)
    close_price  = Column(Float, default=0.0)
    volume       = Column(Float, default=0.0)
    daily_return = Column(Float, default=0.0)
    nifty_weight = Column(Float, default=0.0)


# ─────────────────────────────────────────────────────────────────
# TABLE 2: Macro variables
# ─────────────────────────────────────────────────────────────────
class MacroData(Base):
    __tablename__ = "macro_data"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    date            = Column(Date, nullable=False, index=True, unique=True)
    repo_rate       = Column(Float, default=6.5)
    usdinr          = Column(Float, default=83.0)
    brent_crude     = Column(Float, default=80.0)
    india_vix       = Column(Float, default=15.0)
    fii_net_crore   = Column(Float, default=0.0)
    dii_net_crore   = Column(Float, default=0.0)
    cpi_yoy         = Column(Float, default=5.0)
    gdp_growth      = Column(Float, default=6.0)
    gst_collections = Column(Float, default=150000.0)
    iip_growth      = Column(Float, default=4.0)
    nifty_close     = Column(Float, default=0.0)
    sensex_close    = Column(Float, default=0.0)
    nifty_return    = Column(Float, default=0.0)
    nasdaq_close    = Column(Float, default=0.0)
    sp500_close     = Column(Float, default=0.0)
    gold_close      = Column(Float, default=0.0)


# ─────────────────────────────────────────────────────────────────
# TABLE 3: Sector performance
# ─────────────────────────────────────────────────────────────────
class SectorPerformance(Base):
    __tablename__ = "sector_performance"
    id                         = Column(Integer, primary_key=True, autoincrement=True)
    date                       = Column(Date, nullable=False, index=True)
    sector                     = Column(String(80), index=True)
    subsector                  = Column(String(80), index=True)
    sector_return_pct          = Column(Float, default=0.0)
    sector_contribution_pct    = Column(Float, default=0.0)
    subsector_return_pct       = Column(Float, default=0.0)
    subsector_contribution_pct = Column(Float, default=0.0)
    top_company                = Column(String(100))
    primary_macro_driver       = Column(String(50))
    macro_alignment            = Column(String(30))
    regime_label               = Column(String(50))


# ─────────────────────────────────────────────────────────────────
# TABLE 4: Trained model versions
# ─────────────────────────────────────────────────────────────────
class ModelVersion(Base):
    __tablename__ = "model_versions"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    version          = Column(String(60), unique=True)
    trained_date     = Column(Date)
    training_start   = Column(Date)
    training_end     = Column(Date)
    subsector        = Column(String(80))
    r_squared        = Column(Float, default=0.0)
    mae              = Column(Float, default=0.0)
    directional_acc  = Column(Float, default=0.0)
    feature_weights  = Column(Text)
    feature_names    = Column(Text)
    n_samples        = Column(Integer, default=0)
    is_active        = Column(Boolean, default=True)
    notes            = Column(Text)


# ─────────────────────────────────────────────────────────────────
# TABLE 5: Daily AI insights
# ─────────────────────────────────────────────────────────────────
class DailyInsight(Base):
    __tablename__ = "daily_insights"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    date           = Column(Date, nullable=False, index=True, unique=True)
    what_text      = Column(Text)
    why_text       = Column(Text)
    implication    = Column(Text)
    regime_context = Column(Text)
    full_insight   = Column(Text)
    regime_label   = Column(String(50))
    regime_score   = Column(Integer, default=0)
    nifty_return   = Column(Float, default=0.0)
    top_sector     = Column(String(80))
    model_version  = Column(String(60))
    generated_at   = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────
# TABLE 6: Forward forecasts
# ─────────────────────────────────────────────────────────────────
class ForwardForecast(Base):
    __tablename__ = "forward_forecasts"
    id                 = Column(Integer, primary_key=True, autoincrement=True)
    generated_date     = Column(Date, index=True)
    forecast_horizon   = Column(String(20))
    target_date        = Column(String(20))
    sector             = Column(String(80))
    subsector          = Column(String(80))
    base_case_return   = Column(Float, default=0.0)
    bull_case_return   = Column(Float, default=0.0)
    bear_case_return   = Column(Float, default=0.0)
    confidence_score   = Column(Float, default=0.0)
    opportunity_score  = Column(Float, default=5.0)
    primary_catalyst   = Column(String(250))
    risk_factor        = Column(String(250))
    model_version      = Column(String(60))


# ─────────────────────────────────────────────────────────────────
# TABLE 7: Sector growth analytics
# ─────────────────────────────────────────────────────────────────
class SectorGrowthAnalytics(Base):
    __tablename__ = "sector_growth_analytics"
    id                    = Column(Integer, primary_key=True, autoincrement=True)
    computed_date         = Column(Date)
    sector                = Column(String(80))
    subsector             = Column(String(80))
    period                = Column(String(20))
    total_return_pct      = Column(Float, default=0.0)
    annualised_return_pct = Column(Float, default=0.0)
    volatility_pct        = Column(Float, default=0.0)
    sharpe_ratio          = Column(Float, default=0.0)
    max_drawdown_pct      = Column(Float, default=0.0)
    best_month_pct        = Column(Float, default=0.0)
    worst_month_pct       = Column(Float, default=0.0)
    positive_months_pct   = Column(Float, default=0.0)
    beta_to_nifty         = Column(Float, default=0.0)
    correlation_to_nifty  = Column(Float, default=0.0)
    avg_contribution_pct  = Column(Float, default=0.0)


# ─────────────────────────────────────────────────────────────────
# TABLE 8: Prediction accuracy tracking
# ─────────────────────────────────────────────────────────────────
class PredictionAccuracy(Base):
    __tablename__ = "prediction_accuracy"
    id                = Column(Integer, primary_key=True, autoincrement=True)
    forecast_id       = Column(Integer, default=0)
    sector            = Column(String(80))
    horizon           = Column(String(20))
    predicted_return  = Column(Float, default=0.0)
    actual_return     = Column(Float, default=0.0)
    direction_correct = Column(Boolean, default=False)
    error_pct         = Column(Float, default=0.0)
    evaluated_date    = Column(Date)


# ─────────────────────────────────────────────────────────────────
# TABLE 9: Backtest result cache
# ─────────────────────────────────────────────────────────────────
class BacktestCache(Base):
    __tablename__ = "backtest_cache"
    id                        = Column(Integer, primary_key=True, autoincrement=True)
    cache_key                 = Column(String(80), unique=True, nullable=False, index=True)
    # cache_key format: "backtest_{lookback_years}yr_{anchor_date}"
    # e.g. "backtest_3yr_2022-01-03"  (anchor = first trading day of the lookback)
    anchor_date               = Column(Date, nullable=False)
    # anchor_date = the earliest trading day in the backtest window.
    # This is fixed regardless of today's pipeline_date.
    lookback_years            = Column(Integer, default=3)
    generated_date            = Column(Date)           # when was this cache entry created
    metrics_json              = Column(Text)           # JSON dump of results["metrics"]
    equity_curve_json         = Column(Text)           # JSON dump of results["equity_curve"]
    period_returns_json       = Column(Text)           # JSON dump of results["period_returns"]
    n_periods                 = Column(Integer, default=0)
    status                    = Column(String(20), default="ok")
    consistency_warnings_json = Column(Text)


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────
def init_database():
    """Creates all tables. Safe to call multiple times."""
    Base.metadata.create_all(engine)
    print("Database initialised — all tables ready.")


def get_session():
    """Returns a new database session."""
    return SessionLocal()


def ensure_tables_exist():
    """
    Called at the start of every pipeline run.
    Creates tables if they don't exist yet.
    Prevents 'no such table' errors.
    """
    Base.metadata.create_all(engine)


# Auto-create tables when this module is imported
# This ensures tables always exist before any query runs
ensure_tables_exist()


if __name__ == "__main__":
    init_database()
    print("Tables created successfully.")
    print("Database location: data/marketos.db")
