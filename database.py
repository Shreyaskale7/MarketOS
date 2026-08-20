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
# Create folders — handle both local and production paths
_base = "/data" if os.path.exists("/data") else "."
for folder in [
    f"{_base}/data", f"{_base}/data/raw",
    f"{_base}/data/processed", f"{_base}/data/models",
    "outputs", "logs"
]:
    os.makedirs(folder, exist_ok=True)

# ── Database connection ───────────────────────────────────────────
# In production (Docker), DATABASE_URL is set by docker-compose.
# Locally falls back to data/marketos.db (SQLite)
_db_path = os.getenv("DATABASE_URL")
if _db_path and _db_path.startswith("postgres://"):
    _db_path = _db_path.replace("postgres://", "postgresql://", 1)

if not _db_path:
    _db_path = "sqlite:///data/marketos.db"
DATABASE_URL = _db_path
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args
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
# MULTI-TENANCY & COMPLIANCE TABLES
# ─────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    uuid          = Column(String(36), unique=True, index=True)
    email         = Column(String(120), unique=True, index=True)
    password_hash = Column(String(255))
    created_at    = Column(DateTime, default=datetime.utcnow)
    is_active     = Column(Boolean, default=True)
    # SaaS tiering — free vs pro. No billing provider wired yet (§ below);
    # plan_expires_at lets a future Stripe webhook set a real expiry instead
    # of trusting the plan string forever.
    plan             = Column(String(20), default="free")   # "free" | "pro"
    plan_expires_at  = Column(DateTime, nullable=True)
    stripe_customer_id = Column(String(80), nullable=True)


class UserRiskProfile(Base):
    __tablename__ = "user_risk_profiles"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, index=True)  # FK to users.id
    age              = Column(Integer)
    income_bracket   = Column(String(50))
    investment_horizon = Column(String(50))  # e.g., <1Y, 1-3Y, 3-5Y, >5Y
    drawdown_tolerance = Column(String(50))  # e.g., Low, Medium, High
    risk_score       = Column(Integer)       # 1 to 100
    risk_label       = Column(String(50))    # Conservative, Moderate, Aggressive
    assessed_at      = Column(DateTime, default=datetime.utcnow)


class UserPortfolio(Base):
    __tablename__ = "user_portfolios"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, index=True)
    horizon          = Column(String(20))
    risk_label       = Column(String(50))
    portfolio_json   = Column(Text)          # Stores the allocated positions & weights
    generated_at     = Column(DateTime, default=datetime.utcnow)
    execution_status = Column(String(50))    # e.g., PENDING, EXECUTED, PAPER_TRADE


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────
import threading
_init_lock = threading.Lock()
_tables_created = False

def init_database():
    """Creates all tables. Safe to call multiple times."""
    ensure_tables_exist()
    print("Database initialised — all tables ready.")

def get_session():
    """Returns a new database session."""
    return SessionLocal()

def _migrate_users_table():
    """
    create_all(checkfirst=True) only creates MISSING TABLES — it never adds
    columns to a table that already exists. On a pre-existing database (the
    shipped data/marketos.db, or any already-deployed instance) the new
    plan / plan_expires_at / stripe_customer_id columns on User would
    otherwise be silently absent and every query would raise "no such
    column". This adds them if missing, on both SQLite and Postgres.
    """
    from sqlalchemy import inspect as _inspect, text as _text
    existing = {c["name"] for c in _inspect(engine).get_columns("users")}
    wanted = {
        "plan":               "VARCHAR(20) DEFAULT 'free'",
        "plan_expires_at":    "TIMESTAMP",
        "stripe_customer_id": "VARCHAR(80)",
    }
    with engine.begin() as conn:
        for col, ddl_type in wanted.items():
            if col not in existing:
                conn.execute(_text(f"ALTER TABLE users ADD COLUMN {col} {ddl_type}"))
                print(f"  [migration] users.{col} added")


def ensure_tables_exist():
    """
    Called at the start of every pipeline run.
    Creates tables if they don't exist yet.
    Prevents 'no such table' errors.
    """
    global _tables_created
    if _tables_created:
        return
    with _init_lock:
        if not _tables_created:
            Base.metadata.create_all(engine, checkfirst=True)
            try:
                _migrate_users_table()
            except Exception as exc:
                print(f"  [migration] users table migration skipped: {exc}")
            _tables_created = True

# Auto-create tables when this module is imported
# This ensures tables always exist before any query runs
ensure_tables_exist()


if __name__ == "__main__":
    init_database()
    print("Tables created successfully.")
    print("Database location: data/marketos.db")
