
<div align="center">

# 📊 MarketOS
### Institutional-Grade Market Intelligence System for Indian Equities

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-D71F00?style=flat)](https://www.sqlalchemy.org/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-ML-F7931E?style=flat&logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
[![Flask](https://img.shields.io/badge/Flask-REST%20API-000000?style=flat&logo=flask)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

*A production-grade, end-to-end financial intelligence pipeline — from raw market data to ML-driven portfolio allocation and AI-generated insights — built entirely in Python.*

[Features](#-features) · [Architecture](#-architecture) · [Setup](#-quick-start) · [CLI Commands](#-cli-reference) · [API](#-rest-api) · [Dashboard](#-dashboard)

</div>

---

## What Is This?

MarketOS is a self-contained market intelligence engine that runs every trading day, automatically pulling live data for **130 NSE-listed companies** across **7 sectors and 28 subsectors**, computing macro regime classification, generating ML-driven forward return forecasts (1M / 3M / 6M / 12M), constructing a risk-adjusted portfolio, and producing AI-narrated insights — all without any human intervention after the first setup.

It is not a trading bot. It is an **analytical intelligence layer** — the kind of system that sits upstream of a trading desk's decision-making process.

```
Raw Market Data (yfinance)
        │
        ▼
  9-Stage Daily Pipeline
        │
        ├─► Macro Regime Classification  (5-factor weighted scorer)
        ├─► Sector Attribution Engine    (normalized to NIFTY return)
        ├─► Alpha Signal Engine          (4-signal composite score)
        ├─► ML Forecast Engine           (RF + Ridge, 3 trained horizons)
        ├─► Portfolio Construction       (inverse-vol, Sharpe-scored)
        ├─► Risk Management              (VIX / drawdown / regime rules)
        ├─► Walk-Forward Backtest        (cached, anti-look-ahead)
        ├─► Performance Analytics        (MAE, directional accuracy, IR)
        └─► AI Insight Generation        (LLM + anti-hallucination prefix)
                │
                ▼
     REST API  +  Interactive Dashboard
```

---

## ✨ Features

### Data & Infrastructure
- **10-year historical data** pulled from yfinance, stored in SQLite via SQLAlchemy ORM
- **9-table database schema** — prices, macro, sectors, models, insights, forecasts, backtest cache, prediction accuracy, growth analytics
- **Single source of truth** — `pipeline_utils.py` enforces one authoritative pipeline date and NIFTY return across all 19 modules
- **Duplicate-close detection** — rejects stale intraday data before it contaminates any engine
- **NSE market calendar** — knows every 2025–2026 trading holiday, adjusts engine mode (FULL / PARTIAL / WEEKEND) accordingly

### Macro Intelligence
- **5-factor regime classifier** — VIX (30%), FII flows (25%), USD/INR (15%), Brent Crude (15%), Repo Rate (15%)
- **Composite regime score** on a -1.0 to +1.0 continuous scale, mapped to labels: BULL_RUN / MILD_BULLISH / NEUTRAL / MILD_BEARISH / BEARISH / RISK_OFF
- **Sector macro moderation** — each of the 7 sectors labelled MACRO_ALIGNED or MACRO_DIVERGENT based on actual vs expected return direction
- **Live macro variables** — USD/INR, Brent Crude, India VIX, NIFTY, NASDAQ, S&P 500, Gold (via yfinance) + RBI repo rate, CPI, IIP, GST (manually patched from official releases)

### Alpha & Portfolio Engine
- **4-signal alpha score** per subsector: Momentum (40%) + Mean Reversion (20%) + Volatility Breakout (20%) + Macro Alignment (20%)
- **Regime-aware exclusion threshold** — drops to 0.52 in BEARISH regimes so more sectors qualify for portfolio inclusion
- **Inverse-volatility position sizing** with sector concentration caps, top-3 caps, and correlation-based de-duplication
- **Risk rules layer** — VIX spike, sector drawdown stop-loss, portfolio drawdown hard limit, regime exposure factor all fire before final weights are output

### ML Forecast Engine
- **Random Forest + Ridge ensemble** trained separately for 1M, 3M, and 6M horizons
- **Sector-specific feature sets** — IT models use NASDAQ lag + USD/INR features; Energy models use crude lag features; Banks use rate momentum + FII lag
- **TimeSeriesSplit cross-validation** — no look-ahead leakage in training
- **Soft-cap output compression** — values beyond cap are compressed 30%, preserving relative ranking without hard clipping
- **Bull / Base / Bear scenario** output per subsector per horizon with confidence score and opportunity score (1–10)

### Backtesting & Performance
- **Walk-forward backtest** — monthly rebalancing, 6-month training window, weight-jump limiter (±10% per step)
- **Transaction cost model** — 0.15% cost + 0.05% slippage per trade, turnover filters to avoid over-trading
- **Anchor-date cache** — backtest results cached by fixed historical window, not today's date, so cache stays valid across daily runs
- **Forecast accuracy tracker** — evaluates matured forecasts (direction correct? MAE? RMSE?) and stores results in DB; triggers retraining alert at <55% directional accuracy

### AI Insights
- **Anti-hallucination prefix** — injects verified macro facts (exact NIFTY return, crude price, VIX, repo rate) into the LLM prompt before generation
- **Insight realism filter** — post-processes output to replace fabricated precise figures ("EBITDA +10%") with qualitative language
- **Dual LLM fallback** — tries Groq (llama-3.1-8b) first, falls back to Gemini (gemini-1.5-flash), then uses a structured template if both fail
- **Hindi language mode** available for regional accessibility

### API & Dashboard
- **13-endpoint Flask REST API** — status, macro, alpha, portfolio, forecasts, backtest, performance, insights, pipeline triggers
- **Dark terminal dashboard** — live NIFTY ticker, macro KPI cards, alpha signal table, portfolio donut chart, equity curve overlay, AI insight log
- **60-second auto-refresh** — dashboard polls the API and updates all panels without page reload
- **Async pipeline trigger** — "Run Pipeline" button in dashboard fires the 9-stage pipeline in a background thread and polls for completion

---

## 🏗 Architecture

### Module Map

```
marketos/
│
├── main.py                  # Master orchestrator — 9-stage pipeline, CLI, scheduler
├── database.py              # SQLAlchemy ORM — 9 tables, auto-creates on import
├── classification.py        # 7 sectors · 28 subsectors · 130 companies · NIFTY weights
├── pipeline_utils.py        # ★ Single source of truth — date, NIFTY, validation guards
│
├── data_loader.py           # yfinance fetcher — 10yr history, freshness checks, DB write
├── market_calendar.py       # NSE holiday calendar — trading session & engine mode detection
│
├── macro_engine.py          # Macro data loader, 5-factor regime classifier, sector moderation
├── contribution_engine.py   # NIFTY attribution — weighted sector/subsector contributions
│
├── alpha_engine.py          # 4-signal alpha scorer — momentum, mean-rev, vol, macro
├── ml_forecast_engine.py    # RF + Ridge ML — 1M/3M/6M horizon models, sanity validation
├── model_trainer.py         # GBM + RF + Ridge trainer — sector-specific feature engineering
├── forward_engine.py        # Sector growth analytics, opportunity scoring, catalyst library
│
├── portfolio_engine.py      # Inverse-vol portfolio construction — weights, Sharpe scoring
├── risk_engine.py           # VIX / drawdown / vol-spike / regime risk rules
├── backtest_engine.py       # Walk-forward backtest — transaction costs, cache, IR
│
├── performance_engine.py    # MAE, RMSE, direction accuracy, Sharpe, max drawdown
├── feedback_evaluator.py    # Matured forecast evaluator — actual vs predicted
│
├── marketos_api.py          # Flask REST API — 13 endpoints, async job handling
└── marketos_dashboard.html  # Dark terminal dashboard — Chart.js, live polling
```

### Database Schema (9 Tables)

| Table | Purpose |
|-------|---------|
| `daily_prices` | OHLCV + daily return for all 130 tickers |
| `macro_data` | Daily macro snapshot — 16 variables per row |
| `sector_performance` | Daily sector/subsector attribution results |
| `model_versions` | Trained model registry — R², MAE, feature weights |
| `daily_insights` | AI-generated narrative, regime label, NIFTY return |
| `forward_forecasts` | ML forecast output — base/bull/bear per sector per horizon |
| `sector_growth_analytics` | Annualised returns, vol, Sharpe, drawdown, beta per period |
| `prediction_accuracy` | Evaluated matured forecasts — directional accuracy, error |
| `backtest_cache` | Walk-forward results cached by anchor date |

### Market Coverage

| Sector | NIFTY Weight | Subsectors | Companies |
|--------|-------------|-----------|---------|
| Banking & Financial Services | 38% | 5 | 28 |
| IT & Technology | 15% | 4 | 17 |
| Consumer Goods & Retail | 10% | 4 | 20 |
| Energy & Oil & Gas | 13% | 4 | 18 |
| Infrastructure & Real Estate | 7% | 4 | 19 |
| Automobiles | 7% | 4 | 15 |
| Pharmaceuticals | 5% | 3 | 13 |
| **Total** | **~95%** | **28** | **130** |

---

## ⚡ Quick Start

### Prerequisites

- Python 3.10+
- ~2 GB disk space (for 10-year historical data)
- Free API key from [Groq](https://console.groq.com) (recommended) or [Google AI Studio](https://aistudio.google.com)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/marketos.git
cd marketos

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
pip install flask flask-cors    # For the REST API and dashboard
```

### Configure API Keys

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here   # optional fallback
```

Then update `main.py` to load from environment:

```python
import os
from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
```

> **Note:** Get a free Groq key at [console.groq.com](https://console.groq.com) — no credit card needed, 14,400 requests/day free.

### First-Time Setup

```bash
# Downloads 10 years of data + trains all models
# Takes 30–90 minutes depending on internet speed
python main.py --setup

# Train ML horizon models (1M / 3M / 6M) on full 10-year history
python main.py --train-ml
```

### Run the Pipeline

```bash
# Run the full 9-stage daily pipeline
python main.py --daily
```

That's it. The pipeline auto-detects the market session, validates data quality, runs all 9 stages, and saves output to `outputs/marketos_daily_YYYY-MM-DD.json`.

---

## 🖥 Dashboard

### Start the API server

```bash
# In terminal 1 — start the REST API
python marketos_api.py
# API available at http://localhost:5001
```

### Open the dashboard

Open `marketos_dashboard.html` in any browser. No web server needed — it's a self-contained file that calls the local API.

**Dashboard sections:**

| Section | What it shows |
|---------|--------------|
| Dashboard | Live NIFTY, macro KPIs, top alpha signals, portfolio allocation, performance metrics, latest AI insight |
| Macro Regime | All 12 macro variables, regime classification, 30-day sector performance |
| Alpha Signals | Full ranked alpha table — all 28 subsectors with momentum / mean-rev / vol / macro breakdown |
| Portfolio | Allocation donut chart, expected returns, risk constraint panel |
| Forecasts | Bear / Base / Bull cards per subsector per horizon, filterable by 1M / 3M / 6M |
| Backtest | Walk-forward equity curve (Portfolio vs NIFTY), Sharpe, drawdown, win rate, alpha |
| Performance | Directional accuracy, MAE, RMSE, sector hit ratios |
| AI Insights | Full chronological log of daily AI narratives |

---

## 🔧 CLI Reference

```bash
python main.py --setup              # First-time setup: downloads data, trains models
python main.py --daily              # Run full 9-stage daily pipeline
python main.py --train-ml [years]   # Train ML horizon models (default: 10 years)
python main.py --retrain-ml         # Rolling retrain on 3-year window
python main.py --backtest [years]   # Walk-forward backtest (default: 3 years)
python main.py --backtest 5 --force # Backtest, bypass cache, force recompute
python main.py --performance        # Show forecast accuracy analytics
python main.py --portfolio          # Build today's portfolio allocation
python main.py --validate-ml        # Sanity-check current ML forecast output
python main.py --diagnose           # DB summary — row counts, date ranges, schema check
python main.py --schedule           # Start automated daily scheduler (APScheduler)
python main.py --date 2025-10-15    # Run pipeline for a specific past date
```

### Automated Scheduler

```bash
python main.py --schedule
```

Runs indefinitely with the following schedule (IST):

| Time | Days | Job |
|------|------|-----|
| 4:30 PM | Mon–Fri | Fetch latest market data |
| 7:00 PM | Mon–Fri | Full daily pipeline |
| 1st of month, 9 PM | — | Full model retraining |
| Saturday 8 AM | — | Weekly ML forecast validation |
| Sunday 10 AM | — | Sector growth analytics refresh |

---

## 🌐 REST API

Base URL: `http://localhost:5001/api`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/healthcheck` | API server health |
| GET | `/status` | Pipeline date, NIFTY data, regime label |
| GET | `/macro` | All macro variables + regime classification |
| GET | `/alpha` | Alpha scores for all 28 subsectors |
| GET | `/portfolio?horizon=3M` | Portfolio allocation (1M / 3M / 6M) |
| GET | `/forecasts` | Forward forecasts from DB |
| GET | `/performance?lookback_days=365` | Directional accuracy, MAE, Sharpe |
| GET | `/backtest?years=3` | Walk-forward backtest results |
| GET | `/insights?limit=5` | Latest AI-generated daily insights |
| GET | `/sectors` | Full sector / subsector classification tree |
| GET | `/sector-performance?days=30` | Historical sector returns |
| POST | `/run/fetch` | Trigger data fetch (async background job) |
| POST | `/run/daily` | Trigger full daily pipeline (async) |
| GET | `/run/status` | Check if a background job is running |

### Example Response — `/api/status`

```json
{
  "status": "ok",
  "pipeline_date": "2026-05-12",
  "is_trading_day": true,
  "engine_mode": "FULL",
  "nifty": {
    "level": 23379.55,
    "return_pct": -1.832,
    "points": -436.30,
    "is_valid": true
  },
  "regime_label": "BEARISH",
  "regime_score": -4,
  "job_running": false
}
```

---

## 📈 Sample Pipeline Output

```
=================================================================
  MARKETOS DAILY PIPELINE  —  2026-05-12
  Engine Mode: FULL  |  Data Quality: VALID
=================================================================

NIFTY 50: 23,379.55 | -1.832% | -436.30 pts
Attribution: -3.125% raw → normalized to -1.832% ✓
Coverage: 126/127 tickers

SECTOR CONTRIBUTIONS
──────────────────────────────────────────────────────
Banking & Financial Services    38%    -1.49%    -0.567%   ▼
IT & Technology                 15%    -2.16%    -0.324%   ▼
Energy & Oil & Gas              13%    -2.06%    -0.268%   ▼
Infrastructure & Real Estate     7%    -3.20%    -0.224%   ▼

MACRO REGIME: BEARISH | Score: -4/10
  VIX: 19.3 (MODERATE)  |  Crude: $107.9 SPIKING (+3.5%)
  USD/INR: ₹95.62 (WEAKENING +1.26%)  |  FII: ₹-4,643 Cr

TOP ALPHA SIGNALS (28 subsectors scored)
  Rank  Subsector                      Alpha   Status
  1     Renewable Energy               0.709   PASS
  2     Paints & Building Materials    0.624   PASS
  3     Power Generation & Utilities   0.615   PASS
  4     PSU Banks                      0.601   PASS

PORTFOLIO (3M horizon, BEARISH regime — 65% exposure)
  Private Banks                  14.6%   Expected: +20.5%
  Power Generation & Utilities   14.2%   Expected: +25.1%
  PSU Banks                      10.6%   Expected: +32.6%
  Healthcare & Hospitals         10.5%   Expected: +30.0%
```

---

## 🤖 How the ML Engine Works

### Training

For each of the 28 subsectors, three separate models are trained (1M, 3M, 6M):

```
Historical daily returns (10 years)
        │
        ▼
Feature Engineering (sector-specific)
  ├─ Macro lags: VIX, crude, USD/INR, FII flows, repo rate
  ├─ Price momentum: 5d, 10d, 21d, 63d rolling returns
  ├─ Volatility: 21d / 63d vol ratio
  ├─ Sector-specific: IT → NASDAQ lag; Banks → rate momentum + FII lag;
  │                   Energy → crude lag; Pharma → USD/INR lag
  └─ Forward target: cumulative return over N trading days
        │
        ▼
TimeSeriesSplit cross-validation (no look-ahead)
        │
        ├─► Random Forest (200 estimators)
        └─► Ridge Regression (L2 regularized)
              │
              ▼
        Weighted ensemble prediction
              │
              ▼
  Soft-cap compression + regime scaling
              │
              ▼
  Bull / Base / Bear case output with confidence score
```

### Inference (Daily)

```python
macro_data = fetch_live_macro_data()           # today's verified macro snapshot
regime     = classify_macro_regime(macro_data) # 5-factor regime score
forecasts  = generate_ml_forecasts(macro_data, regime)

# Output per subsector:
# {"PSU Banks": {"1M": {"base_case_return_pct": +13.9,
#                        "bull_case_return_pct": +16.7,
#                        "bear_case_return_pct": +11.2,
#                        "confidence_score": 0.60,
#                        "opportunity_score": 7.7}}}
```

---

## 🔁 Data Integrity Design

MarketOS has several layers of protection against bad data corrupting the pipeline:

| Guard | What it catches |
|-------|----------------|
| Duplicate-close detection | Two consecutive identical NIFTY closes → stale intraday data |
| ±5% plausibility check | NIFTY return ≥ 5% → almost certainly a data error, marks `is_valid=False` |
| Attribution consistency check | If `raw_attribution` differs from `NIFTY_return` by >5% → logs LOW confidence |
| Stale data block | If DB date < last trading day on a trading day → pipeline aborts |
| Market calendar gate | Non-trading days → alpha/portfolio/risk engines suppressed automatically |
| Anti-hallucination LLM prefix | Injects verified macro facts before LLM generation to prevent contradictions |
| Insight realism filter | Post-processes LLM output, strips fabricated EBITDA/GRM precise figures |

---

## ⚙️ Configuration

Update manual macro variables in `main.py` after each official data release:

```python
CURRENT_REPO_RATE   = 6.25    # RBI MPC — update after each policy meeting
CURRENT_GDP         = 6.4     # MoSPI advance estimate — update quarterly
CURRENT_CPI         = 4.8     # MoSPI — update monthly
CURRENT_IIP         = 5.2     # MoSPI — update monthly
CURRENT_GST         = 187000  # GSTN — update monthly (₹ Crore)
```

---

## 📦 Requirements

```
yfinance>=0.2.36
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
sqlalchemy>=2.0.0
anthropic>=0.25.0
apscheduler>=3.10.0
requests>=2.31.0
python-dotenv>=1.0.0
flask>=3.0.0
flask-cors>=4.0.0
```

---

## 🗺 Roadmap

- [ ] Move API keys fully to `.env` (python-dotenv)
- [ ] Add authentication to POST endpoints (X-API-Key header)
- [ ] Alembic for database migrations
- [ ] Combined stress-test rule (VIX + drawdown compounding)
- [ ] Subsector-level macro sensitivity differentiation
- [ ] Live NIFTY weight validation against NSE index feed
- [ ] Unit tests for core engines (pytest)
- [ ] Docker container for one-command deployment
- [ ] Telegram / WhatsApp daily alert bot

---

## ⚠️ Disclaimer

MarketOS is an educational and research project. It is **not** financial advice and **not** a trading system. All forward return projections are model outputs based on historical patterns and may not reflect future market conditions. Do not make investment decisions based on this system's output.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Built by **Shreyas Kale** · RVCE Bengaluru · B.E. Computer Science (Data Science)

*If this project helped you or you found it interesting, please ⭐ the repo.*

</div>

