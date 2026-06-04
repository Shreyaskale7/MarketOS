<div align="center">

# 📊 MarketOS
### Institutional-Grade Market Intelligence System for Indian Equities

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-D71F00?style=flat)](https://www.sqlalchemy.org/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-ML-F7931E?style=flat&logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
[![Flask](https://img.shields.io/badge/Flask-REST%20API-000000?style=flat&logo=flask)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

*A production-grade, zero-cost financial intelligence pipeline — from raw market data to Markowitz MVO portfolio allocation, LLM sentiment analysis, and ML-driven forecasting — built entirely in Python.*

[Features](#-features) · [Architecture](#-architecture) · [Setup](#-quick-start) · [CLI Commands](#-cli-reference) · [API](#-rest-api) · [Dashboard](#-dashboard)

</div>

---

## What Is This?

MarketOS is a self-contained market intelligence engine that runs every trading day. It automatically pulls live data for **130 NSE-listed companies** across **7 sectors and 28 subsectors**, computes macro regime classification, generates ML-driven forward return forecasts, constructs a risk-adjusted Markowitz portfolio, and runs live AI sentiment analysis using Groq's LLaMA-3.3-70B.

Best of all: it achieves all of this **without any paid subscriptions**. It leverages free APIs, RSS feeds, Yahoo Finance, and local SQLite databases to provide a $100k+ institutional-level quantitative infrastructure at zero cost.

```
Raw Market Data (yfinance + Google News RSS)
        │
        ▼
  10-Stage Daily Pipeline
        │
        ├─► Macro Regime Classification  (5-factor weighted scorer)
        ├─► LLM Sentiment Engine         (Groq LLaMA-3.3 + RSS parsing)
        ├─► Sector Attribution Engine    (normalized to NIFTY return)
        ├─► Alpha Signal Engine v4       (5-factor: Mom, MRev, Vol, Mac, Sent)
        ├─► ML Forecast Engine           (RF + Ridge, 3 trained horizons)
        ├─► Markowitz MVO Portfolio      (Mean-Variance Optimization + EF)
        ├─► Risk Management              (VIX / drawdown / regime rules)
        ├─► Walk-Forward Backtest        (In-sample train / OOS validation)
        ├─► Performance Analytics        (MAE, directional accuracy, IR)
        └─► AI Insight Generation        (LLM + anti-hallucination prefix)
                │
                ▼
     REST API  +  Interactive Dashboard
```

---

## ✨ Core Features

### 1. Alpha Signal Engine v4
A robust composite scorer evaluating 28 subsectors across 5 factors:
- **Momentum (30%)**: 1M & 3M trailing velocity.
- **Mean Reversion (20%)**: Statistical oscillator distances.
- **Sentiment (20%)**: Live NLP analysis of recent headlines.
- **Volatility Breakout (15%)**: ATR and volume expansion.
- **Macro Alignment (15%)**: Regime-based structural tailwinds.
- Includes a dynamic threshold (0.40) that automatically adjusts based on Bearish/Bullish market regimes.

### 2. Live LLM Sentiment Pipeline
- **Google News RSS**: Real-time fetching of top 5 headlines per sector.
- **Groq LLaMA-3.3-70B**: Lightning-fast NLP inference calculates a sentiment score from -1.0 (Extreme Bearish) to +1.0 (Extreme Bullish).
- **Fully Integrated**: Sentiment directly influences the mathematical Alpha rank and final portfolio allocation.

### 3. Markowitz Mean-Variance Optimization (MVO)
- **Efficient Frontier Generation**: Scipy's `minimize` optimizer finds the optimal portfolio weights by maximizing the Sharpe Ratio.
- **Risk Limits**: Hard caps sector concentration to 25%, enforces a min/max allocation bounds per subsector, and targets an annualized volatility threshold.
- **Dynamic Expected Returns**: Integrates the Alpha scores into the return vectors.

### 4. Walk-Forward Cross Validation
- **Institutional Backtesting**: Avoids look-ahead bias by training the model on historical In-Sample (IS) windows and stepping forward to validate on Out-Of-Sample (OOS) data.
- **Turnover Limits**: Restricts weight changes to ±10% per month to minimize simulated transaction costs.
- **Metrics**: Calculates Information Ratio, Win Rate, Max Drawdown, and NIFTY Outperformance.

### 5. ML Forecast Engine
- **Random Forest + Ridge ensemble** trained separately for 1M, 3M, and 6M horizons.
- **Sector-specific feature sets** — IT models use NASDAQ lag + USD/INR features; Energy uses crude lag; Banks use rate momentum.
- **Scenario Outputs**: Bull / Base / Bear scenario outputs per subsector with confidence scores and opportunity scoring.

### 6. Zero-Cost Infrastructure
- **Historical Data**: 10 years of OHLCV pulled natively from `yfinance`.
- **Database**: Local SQLite via SQLAlchemy (9 tables).
- **Backend API**: Python Flask REST API.
- **Frontend**: A stunning, self-contained HTML/CSS/JS dashboard featuring glassmorphism, micro-animations, and live data polling.

---

## 🏗 Architecture

### Module Map

```
marketos/
│
├── main.py                  # Master orchestrator — 10-stage pipeline, CLI
├── database.py              # SQLAlchemy ORM — 9 tables, auto-creates on import
├── classification.py        # 7 sectors · 28 subsectors · 130 companies
├── pipeline_utils.py        # ★ Single source of truth — date, NIFTY
│
├── data_loader.py           # yfinance fetcher — 10yr history
├── market_calendar.py       # NSE holiday calendar — trading session detection
│
├── macro_engine.py          # Macro data loader, 5-factor regime classifier
├── sentiment_engine.py      # Google News RSS fetcher + Groq NLP scorer
│
├── alpha_engine.py          # 5-signal alpha scorer (Mom, MRev, Vol, Mac, Sent)
├── ml_forecast_engine.py    # RF + Ridge ML models
├── model_trainer.py         # Sector-specific feature engineering trainer
│
├── portfolio_engine.py      # Markowitz MVO Portfolio Construction
├── risk_engine.py           # VIX / drawdown / regime risk rules
├── backtest_engine.py       # Walk-forward cross validation engine
│
├── performance_engine.py    # MAE, RMSE, direction accuracy analytics
├── marketos_api.py          # Flask REST API — 14 endpoints
└── marketos_dashboard.html  # Dark terminal dashboard — Chart.js, live polling
```

---

## ⚡ Quick Start

### Prerequisites
- Python 3.10+
- ~2 GB disk space (for 10-year historical data)
- Free API key from [Groq](https://console.groq.com) (Mandatory for Sentiment Engine)

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
pip install flask flask-cors feedparser requests
```

### Configure API Keys

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_key_here
```

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
# Run the full 10-stage daily pipeline
python main.py --daily
```

---

## 🖥 Dashboard UI

The system includes a state-of-the-art interactive web dashboard (`marketos_dashboard.html`). 

### Start the API server
```bash
python marketos_api.py
# API available at http://localhost:5001
```

**Key Dashboard Panels:**
1. **Live NIFTY Ticker & Macro KPIs**
2. **LLM Sentiment Intelligence**: Displays live, visually-scored sentiment bars for each sector parsed directly from Groq.
3. **Alpha Signal Engine v4 Table**: Sorts and ranks all 28 subsectors based on the 5-factor composite score.
4. **Markowitz MVO Portfolio**: Visualized with a custom-colored Donut Chart and expected return metrics.
5. **Walk-Forward Validation**: Plots the simulated equity curve of the portfolio vs NIFTY over the last 3 years.

---

## 🔧 CLI Reference

```bash
python main.py --setup              # First-time setup: downloads data, trains models
python main.py --daily              # Run full 10-stage daily pipeline
python main.py --train-ml [years]   # Train ML horizon models (default: 10 years)
python main.py --backtest [years]   # Walk-forward backtest (default: 3 years)
python main.py --portfolio          # Build today's Markowitz MVO allocation
python main.py --schedule           # Start automated daily scheduler (APScheduler)
```

---

## ⚠️ Disclaimer

MarketOS is an educational, research, and personal analytical tool. It is **not** a licensed trading system and does **not** provide financial advice. All forward return projections and optimized weights are mathematical model outputs based on historical patterns and LLM inferences. Do not make investment decisions based solely on this system's output. 

---

<div align="center">

Built by **Shreyas Kale** · RVCE Bengaluru · B.E. Computer Science (Data Science)

*If this project helped you or you found it interesting, please ⭐ the repo.*

</div>
