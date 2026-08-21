<div align="center">

# 📊 MarketOS
### Sector-Level Market Intelligence for Indian Equities

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-D71F00?style=flat)](https://www.sqlalchemy.org/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-ML-F7931E?style=flat&logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
[![Flask](https://img.shields.io/badge/Flask-REST%20API-000000?style=flat&logo=flask)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

*A zero-cost pipeline from raw NSE price data to a Markowitz-optimised sector portfolio — macro regime classification, LLM sentiment, ML forecasting, and a measured walk-forward backtest, in one Python codebase.*

[Live demo](#-live-demo) · [What it does](#what-is-this) · [Measured results](#-measured-results-not-a-sales-pitch) · [Setup](#-quick-start) · [Architecture](#-architecture) · [Known limitations](#-known-limitations)

</div>

---

## 🌐 Live Demo

**[marketos-api.onrender.com/dashboard](https://marketos-api.onrender.com/dashboard)** — free-tier hosting, may take ~30s to wake up on first load.

Data refreshes automatically every weekday at 16:15 IST via a scheduled GitHub Actions job — see [Automation](#-automation--how-daily-refresh-works).

---

## What Is This?

MarketOS pulls daily price and macro data for **130 NSE-listed companies across 7 sectors and 28 subsectors**, decomposes the day's NIFTY move by contributor, classifies the macro regime, scores each subsector on a 5-factor composite, forecasts forward *relative-to-NIFTY* returns with a 4-model ML tournament, solves a constrained Markowitz portfolio, applies a mechanical risk overlay, and — critically — **measures the whole thing on a walk-forward backtest with realistic Indian transaction costs**, rather than just asserting it works.

No paid subscriptions: free Yahoo Finance data, free Groq LLM inference, a database that runs at zero cost on Render's free Postgres tier.

```
yfinance + Google News RSS
        │
        ▼
  10-Stage Daily Pipeline (main.py --daily)
        │
        ├─► Attribution         company → subsector → sector, reconciled to NIFTY
        ├─► Macro Regime        6-signal weighted classifier → BULLISH/NEUTRAL/BEARISH
        ├─► LLM Sentiment       Groq inference over live news headlines, per sector
        ├─► Alpha Signal v4     5-factor composite, ranks all 28 subsectors
        ├─► ML Forecast         RF + Ridge + XGBoost + LightGBM tournament, 1M/3M/6M/12M
        ├─► Markowitz MVO       SciPy SLSQP max-Sharpe, under concentration caps
        ├─► Risk Overlay        11 mechanical rules, monotonically exposure-reducing
        ├─► Walk-Forward        quarterly rebalance, full Indian cost stack
        ├─► Forecast Scoring    predicted vs. realised, once forecasts mature
        └─► AI Insight          LLM narrative, grounded by an anti-hallucination
                                fact-injection prefix (never invents a number)
                │
                ▼
     REST API (Flask)  +  Dashboard (marketos_dashboard.html)
```

A full build guide covering every design decision, alternative considered, and worked example is in **[MARKETOS_BUILD_BIBLE.pdf](MARKETOS_BUILD_BIBLE.pdf)**.

---

## 📏 Measured results — not a sales pitch

Every number below was read out of the live database, not estimated. The honest version, including the negative results:

| Window | Periods | Portfolio p.a. | NIFTY p.a. | Net alpha | Sharpe | Info Ratio |
|---|---|---|---|---|---|---|
| 5-year | 15 | 19.11% | 13.58% | **+5.53%** | 0.864 | 0.601 |
| 10-year | 35 (largest sample) | 11.89% | 11.87% | **+0.02%** | 0.375 | 0.021 |

*(pulled live from the deployed API — will drift as new data lands; the finding below is the point, not the exact decimals)*

**The honest finding:** over the longest window and the largest sample, this strategy's sector-rotation heuristic tracks NIFTY almost exactly rather than beating it. A shorter 5-year window looks better, but a result that changes sign depending on where you start the window is a textbook sign of a weak or unstable edge — that instability is documented, not hidden. See the **[build bible](MARKETOS_BUILD_BIBLE.pdf)**, Part 9, for the full backtest methodology, the honest negatives, and why the 3-year window was dropped from the dashboard entirely (n=7, negative Sharpe — too small a sample to support any conclusion).

**Important scope note:** the backtest tests the sector-selection/portfolio-construction logic, not the ML forecasting layer — those two have not yet been backtested together. That's the highest-value open item, not a hidden flaw.

---

## ✨ Core Features

### 1. Alpha Signal Engine v4
5-factor composite across 28 subsectors — momentum (30%), mean reversion (15%), volatility breakout (15%), macro alignment (20%), live sentiment (20%) — with a regime-aware exclusion threshold.

### 2. LLM Sentiment Pipeline
Live Google News RSS headlines per sector, scored via **Groq** (`GROQ_MODEL`, default `openai/gpt-oss-20b`) as strict JSON, with a hard clamp to [-1, +1] and graceful fallback to neutral on any API failure. Non-blocking on the API path (cached, refreshed in the background) so a cold cache can never hang a dashboard request — it used to, and that was the majority of "the dashboard broke" reports before it was fixed.

### 3. Markowitz Mean-Variance Optimisation
SciPy `SLSQP` maximises the Sharpe ratio over a 252-day covariance matrix, under a 20% per-name box bound, with sector/theme caps and a correlation penalty applied after the solve. Falls back to inverse-volatility weighting if the covariance matrix can't be built.

### 4. Walk-Forward Backtest
Quarterly rebalancing (63 trading days), 252-day training window, weights built strictly from data before each rebalance date. Prices a full Indian cost stack — STT, stamp duty, brokerage, exchange fees, SEBI fees, GST, and size-dependent slippage — not a flat estimate. Results are pre-computed out-of-band (`populate_backtest_cache.py`) rather than on-request, since computing one live exceeds a free-tier instance's memory budget.

### 5. ML Forecast Engine
A 4-way model tournament (Random Forest, Ridge, XGBoost, LightGBM) per subsector per horizon, top-3 ensembled, with a hard fallback to Ridge if the best candidate's cross-validated information coefficient is negative. Trained on **cross-sectional alpha** (subsector return minus NIFTY return over the identical forward window) — not absolute return — via `TimeSeriesSplit`, so nothing is ever trained on the future.

### 6. Zero-Cost, Automated Infrastructure
- **Database**: SQLite locally, Postgres in production (same code, `DATABASE_URL` env var switches it)
- **Backend**: Flask REST API, JWT auth with bcrypt password hashing
- **Frontend**: Self-contained HTML/CSS/JS dashboard, no build step, no framework
- **Daily automation**: a scheduled GitHub Actions workflow — see below

---

## 🤖 Automation — how daily refresh works

`.github/workflows/daily-pipeline.yml` runs the full pipeline on GitHub's infrastructure (not the hosting instance — a free web dyno doesn't have the RAM), Monday–Friday at 16:15 IST:

```
fetch new prices + macro  →  run the 10-stage pipeline  →  score matured
forecasts  →  refresh the backtest cache  →  ping the API to keep it warm
```

Requires three repo secrets (`Settings → Secrets and variables → Actions`): `DATABASE_URL`, `GROQ_API_KEY`, `GEMINI_API_KEY`. Can also be triggered manually from the Actions tab (`workflow_dispatch`).

---

## 🏗 Architecture

### Module Map

```
marketos/
│
├── main.py                  # Master orchestrator — 10-stage pipeline, CLI
├── database.py               # SQLAlchemy ORM — 12 tables, self-migrating on import
├── classification.py         # 7 sectors · 28 subsectors · 127 unique tickers
├── pipeline_utils.py         # ★ Single source of truth — pipeline date, NIFTY return
│
├── data_loader.py            # yfinance fetcher — 10yr history, dedupe-safe re-runs
├── market_calendar.py        # NSE holiday calendar, per-engine trading-day gates
│
├── macro_engine.py           # 6-signal regime classifier, macro moderation
├── sentiment_engine.py       # Google News RSS + Groq sentiment, non-blocking cache
│
├── alpha_engine.py            # 5-signal composite alpha scorer
├── ml_forecast_engine.py      # RF/Ridge/XGBoost/LightGBM tournament, 1M/3M/6M/12M
├── model_trainer.py           # Legacy per-sector trainer (superseded, kept for reference)
│
├── portfolio_engine.py        # Markowitz MVO portfolio construction
├── risk_engine.py             # 11 monotonically exposure-reducing risk rules
├── backtest_engine.py         # Walk-forward backtest, full Indian cost stack
├── populate_backtest_cache.py # Pre-computes backtests out-of-band (see above)
│
├── performance_engine.py      # MAE, RMSE, directional accuracy, Sharpe
├── feedback_evaluator.py      # Scores matured forecasts against realised outcomes
├── marketos_api.py            # Flask REST API — ~28 endpoints, JWT auth, rate limits
└── marketos_dashboard.html    # Dashboard — served by marketos_api.py, no build step

.github/workflows/
└── daily-pipeline.yml         # Scheduled automation (see above)
```

---

## ⚡ Quick Start

### Prerequisites
- Python 3.10+
- ~2 GB disk space (10-year historical data)
- Free API key from [Groq](https://console.groq.com)

### Installation

```bash
git clone https://github.com/Shreyaskale7/MarketOS.git
cd MarketOS
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configure

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here   # optional, narrative fallback
# GROQ_MODEL=openai/gpt-oss-20b       # optional override — Groq rotates
                                       # its model catalogue; if sentiment
                                       # starts failing, check available
                                       # models before assuming a code bug:
                                       #   curl -H "Authorization: Bearer
                                       #   $GROQ_API_KEY" https://api.groq
                                       #   .com/openai/v1/models
```

### First-Time Setup

```bash
python main.py --setup      # 30–90 min: 10yr of data, then trains ~500 model fits
python main.py --train-ml   # (re)train the horizon models explicitly
python main.py --daily      # one full pipeline run
```

### Run the Dashboard

```bash
python marketos_api.py
# http://localhost:5001/dashboard
```

---

## 🔧 CLI Reference

```bash
python main.py --setup              # First-time setup: downloads data, trains models
python main.py --daily              # Run full 10-stage daily pipeline
python main.py --train-ml [years]   # Train ML horizon models (default: 10 years)
python main.py --backtest [years]   # Walk-forward backtest (default: 3 years)
python main.py --portfolio          # Build today's Markowitz MVO allocation
python populate_backtest_cache.py   # Pre-compute 5yr/10yr backtests for the dashboard
```

---

## 🚀 Deploying your own copy

Free-tier deployment (Render web service + Postgres, GitHub Actions for scheduling) is documented step by step in the [build bible](MARKETOS_BUILD_BIBLE.pdf), Part 7. Short version: `render.yaml` is already in the repo — connect it as a Blueprint on Render, seed the database once from a machine with real RAM (`python main.py --setup` pointed at the production `DATABASE_URL`), then add the three secrets above to GitHub Actions.

---

## ⚠️ Known Limitations

Stated plainly rather than discovered the hard way:

- **The backtest tests the portfolio-construction heuristic, not the ML forecast engine** — those have never been run together. The single highest-value thing to build next.
- **Paper Trading Ledger doesn't persist in the deployed environment** — writes local files, not the database.
- **Forecast accuracy** only populates once forecasts mature (~30+ days after generation) — empty on a fresh deployment is expected, not broken.
- **Free-tier database has an expiry date** — check it periodically if self-hosting on Render's free Postgres.
- **No automated test suite** — most defects found during development were silent (wrong units, a dead ticker, a stray `return`) rather than crashes. Documented in full in the build bible.

---

## ⚠️ Disclaimer

MarketOS is an educational and research tool. It is **not** a licensed trading system and does **not** provide financial advice. Forward return projections and optimised weights are model outputs based on historical patterns and LLM inference, with measured accuracy documented above — not guarantees. Do not make investment decisions based solely on this system's output.

---

<div align="center">

Built by **Shreyas Kale** · RVCE Bengaluru · B.E. Computer Science (Data Science)

*If this project helped you or you found it interesting, please ⭐ the repo.*

</div>
