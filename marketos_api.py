# marketos_api.py
# MarketOS — Flask REST API Gateway
# 
# Place this file in the SAME directory as your backend files (main.py, etc.)
# Run: python marketos_api.py
# API available at: http://localhost:5001
#
# Endpoints:
#   GET  /api/status          — Pipeline status + NIFTY live data
#   GET  /api/macro           — Macro variables + regime classification
#   GET  /api/alpha           — Alpha signal scores per subsector
#   GET  /api/portfolio       — Current portfolio allocation
#   GET  /api/forecasts       — Forward forecasts (1M, 3M, 6M)
#   GET  /api/performance     — Forecast accuracy & analytics
#   GET  /api/backtest        — Walk-forward backtest results
#   GET  /api/insights        — Latest AI-generated daily insight
#   GET  /api/sectors         — All sector/subsector structure
#   POST /api/run/fetch        — Trigger data fetch (non-blocking)
#   POST /api/run/daily        — Trigger daily pipeline (non-blocking)
#   GET  /api/healthcheck     — Server health

import os
import sys
import json
import threading
from datetime import datetime, date, timedelta
from functools import wraps
import warnings
warnings.filterwarnings("ignore")

# ── Add project root to path so backend modules resolve ───────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from flask import Flask, jsonify, request, Response
    from flask_cors import CORS
except ImportError:
    print("ERROR: Flask / flask-cors not installed.")
    print("Run: pip install flask flask-cors")
    sys.exit(1)

app = Flask(__name__)
CORS(app)

# ── Global pipeline job tracker ──────────────────────────────────
_job_status = {"running": False, "job": None, "started_at": None, "result": None}

# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def success(data: dict, **kwargs) -> Response:
    payload = {"status": "ok", "timestamp": datetime.utcnow().isoformat(), **kwargs}
    payload.update(data)
    return jsonify(payload)


def error(message: str, code: int = 500) -> Response:
    return jsonify({"status": "error", "message": message,
                    "timestamp": datetime.utcnow().isoformat()}), code


def safe_import(module_name: str):
    """Safely imports a backend module, returns None on failure."""
    try:
        import importlib
        return importlib.import_module(module_name)
    except Exception as exc:
        print(f"  [API] Warning: could not import {module_name}: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────
# ROUTE 1 — HEALTHCHECK
# ─────────────────────────────────────────────────────────────────

@app.route("/api/healthcheck")
def healthcheck():
    return success({"message": "MarketOS API is running", "version": "2.0"})


# ─────────────────────────────────────────────────────────────────
# ROUTE 2 — PIPELINE STATUS
# ─────────────────────────────────────────────────────────────────

@app.route("/api/status")
def pipeline_status():
    try:
        from database import ensure_tables_exist
        ensure_tables_exist()

        from pipeline_utils import get_pipeline_date, get_nifty_return_from_db
        pipeline_date = get_pipeline_date()
        nifty_ret, is_valid, nifty_level, nifty_pts = get_nifty_return_from_db(pipeline_date)

        from market_calendar import get_market_status
        mkt = get_market_status()

        from database import get_session, DailyInsight
        session = get_session()
        try:
            latest_insight = session.query(DailyInsight).order_by(
                DailyInsight.date.desc()).first()
            last_run = str(latest_insight.date) if latest_insight else None
            regime_label = latest_insight.regime_label if latest_insight else "UNKNOWN"
            regime_score = latest_insight.regime_score if latest_insight else 0
        finally:
            session.close()

        return success({
            "pipeline_date":    str(pipeline_date),
            "is_trading_day":   mkt.get("is_trading_day", False),
            "engine_mode":      mkt.get("engine_mode", "UNKNOWN"),
            "nifty": {
                "level":        nifty_level,
                "return_pct":   nifty_ret,
                "points":       nifty_pts,
                "is_valid":     is_valid,
            },
            "last_run_date":    last_run,
            "regime_label":     regime_label,
            "regime_score":     regime_score,
            "job_running":      _job_status["running"],
        })
    except Exception as exc:
        # Return safe defaults if backend not fully set up
        return success({
            "pipeline_date":    str(date.today() - timedelta(days=1)),
            "is_trading_day":   False,
            "engine_mode":      "OFFLINE",
            "nifty": {"level": 0, "return_pct": None, "points": 0, "is_valid": False},
            "last_run_date":    None,
            "regime_label":     "UNKNOWN",
            "regime_score":     0,
            "job_running":      _job_status["running"],
            "warning":          f"Backend partially unavailable: {str(exc)[:80]}",
        })


# ─────────────────────────────────────────────────────────────────
# ROUTE 3 — MACRO DATA
# ─────────────────────────────────────────────────────────────────

@app.route("/api/macro")
def macro_data():
    try:
        from macro_engine import fetch_live_macro_data, classify_macro_regime
        macro = fetch_live_macro_data()
        regime = classify_macro_regime(macro)

        # Flatten regime for JSON serialisation
        regime_out = {
            "overall_regime":   regime.get("overall_regime", "UNKNOWN"),
            "regime_score":     float(regime.get("regime_score", 0)),
            "legacy_score":     int(regime.get("legacy_score", 0)),
            "bull_bear_label":  regime.get("bull_bear_label", "NEUTRAL"),
            "volatility_regime": regime.get("volatility_regime", "NORMAL"),
            "rate_regime":      regime.get("rate_regime", "STABLE"),
            "global_regime":    regime.get("global_regime", "NEUTRAL"),
        }

        return success({"macro": macro, "regime": regime_out})
    except Exception as exc:
        return error(f"Macro engine error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 4 — ALPHA SIGNALS
# ─────────────────────────────────────────────────────────────────

@app.route("/api/alpha")
def alpha_signals():
    try:
        from macro_engine import fetch_live_macro_data, classify_macro_regime, moderate_sector_scores
        from alpha_engine import compute_alpha_scores

        macro  = fetch_live_macro_data()
        regime = classify_macro_regime(macro)

        # Build a minimal moderated_output for alpha engine
        from database import get_session, SectorPerformance
        from pipeline_utils import get_pipeline_date
        pd_date = get_pipeline_date()
        session = get_session()
        try:
            rows = session.query(SectorPerformance).filter(
                SectorPerformance.date >= pd_date - timedelta(days=3)
            ).all()
        finally:
            session.close()

        moderated_output = {
            "macro_data": macro,
            "macro_regime": regime,
            "moderated_sectors": {},
        }

        alpha = compute_alpha_scores(moderated_output, macro, regime)

        # Sort by alpha score descending
        sorted_alpha = dict(sorted(
            alpha.items(),
            key=lambda x: x[1].get("alpha_score", 0),
            reverse=True
        ))

        return success({"alpha": sorted_alpha, "total_sectors": len(alpha)})
    except Exception as exc:
        return error(f"Alpha engine error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 5 — PORTFOLIO ALLOCATION
# ─────────────────────────────────────────────────────────────────

@app.route("/api/portfolio")
def portfolio():
    try:
        horizon = request.args.get("horizon", "3M")
        from macro_engine import fetch_live_macro_data, classify_macro_regime
        from ml_forecast_engine import generate_ml_forecasts
        from portfolio_engine import build_portfolio
        from risk_engine import apply_risk_rules

        macro   = fetch_live_macro_data()
        regime  = classify_macro_regime(macro)
        fc      = generate_ml_forecasts(macro, regime)
        port    = build_portfolio(fc, macro, regime, horizon=horizon)
        risk_p  = apply_risk_rules(port, macro, regime)

        return success({"portfolio": risk_p, "horizon": horizon})
    except Exception as exc:
        return error(f"Portfolio engine error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 6 — FORWARD FORECASTS
# ─────────────────────────────────────────────────────────────────

@app.route("/api/forecasts")
def forecasts():
    try:
        from database import get_session, ForwardForecast
        from pipeline_utils import get_pipeline_date
        pd_date = get_pipeline_date()

        # Load most recent forecasts from DB (last 7 days)
        session = get_session()
        try:
            since = pd_date - timedelta(days=7)
            rows = session.query(ForwardForecast).filter(
                ForwardForecast.generated_date >= since
            ).order_by(ForwardForecast.generated_date.desc()).all()
        finally:
            session.close()

        if not rows:
            # Fall back to generating live forecasts
            from macro_engine import fetch_live_macro_data, classify_macro_regime
            from ml_forecast_engine import generate_ml_forecasts
            macro  = fetch_live_macro_data()
            regime = classify_macro_regime(macro)
            fc     = generate_ml_forecasts(macro, regime)

            out = []
            for sector, horizons in fc.items():
                for horizon, data in horizons.items():
                    if isinstance(data, dict):
                        out.append({
                            "sector":           sector,
                            "horizon":          horizon,
                            "base_case_return": data.get("base_case_return", 0),
                            "bull_case_return": data.get("bull_case_return", 0),
                            "bear_case_return": data.get("bear_case_return", 0),
                            "confidence_score": data.get("confidence_score", 0),
                            "opportunity_score": data.get("opportunity_score", 5),
                            "primary_catalyst": data.get("primary_catalyst", ""),
                            "risk_factor":      data.get("risk_factor", ""),
                            "generated_date":   str(pd_date),
                        })
            return success({"forecasts": out, "source": "live", "count": len(out)})

        out = [{
            "id":               r.id,
            "sector":           r.sector,
            "subsector":        r.subsector,
            "horizon":          r.forecast_horizon,
            "base_case_return": r.base_case_return,
            "bull_case_return": r.bull_case_return,
            "bear_case_return": r.bear_case_return,
            "confidence_score": r.confidence_score,
            "opportunity_score": r.opportunity_score,
            "primary_catalyst": r.primary_catalyst,
            "risk_factor":      r.risk_factor,
            "generated_date":   str(r.generated_date),
        } for r in rows]

        return success({"forecasts": out, "source": "database", "count": len(out)})
    except Exception as exc:
        return error(f"Forecasts error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 7 — PERFORMANCE ANALYTICS
# ─────────────────────────────────────────────────────────────────

@app.route("/api/performance")
def performance():
    try:
        from performance_engine import compute_performance_summary
        lookback = int(request.args.get("lookback_days", 365))
        result = compute_performance_summary(lookback_days=lookback)

        # Make serialisable (numpy types → python)
        def _clean(obj):
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [_clean(i) for i in obj]
            elif hasattr(obj, "item"):  # numpy scalar
                return obj.item()
            return obj

        return success({"performance": _clean(result)})
    except Exception as exc:
        return error(f"Performance engine error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 8 — BACKTEST
# ─────────────────────────────────────────────────────────────────

@app.route("/api/backtest")
def backtest():
    try:
        years = int(request.args.get("years", 3))
        force = request.args.get("force", "false").lower() == "true"

        from backtest_engine import run_backtest
        results = run_backtest(lookback_years=years, force_recompute=force)

        def _clean(obj):
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [_clean(i) for i in obj]
            elif hasattr(obj, "item"):
                return obj.item()
            elif hasattr(obj, "isoformat"):
                return obj.isoformat()
            return obj

        return success({"backtest": _clean(results), "years": years})
    except Exception as exc:
        return error(f"Backtest engine error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 9 — AI INSIGHTS
# ─────────────────────────────────────────────────────────────────

@app.route("/api/insights")
def insights():
    try:
        from database import get_session, DailyInsight
        limit = int(request.args.get("limit", 5))
        session = get_session()
        try:
            rows = session.query(DailyInsight).order_by(
                DailyInsight.date.desc()).limit(limit).all()
        finally:
            session.close()

        out = [{
            "date":           str(r.date),
            "what_text":      r.what_text,
            "why_text":       r.why_text,
            "implication":    r.implication,
            "regime_context": r.regime_context,
            "full_insight":   r.full_insight,
            "regime_label":   r.regime_label,
            "regime_score":   r.regime_score,
            "nifty_return":   r.nifty_return,
            "top_sector":     r.top_sector,
        } for r in rows]

        return success({"insights": out, "count": len(out)})
    except Exception as exc:
        return error(f"Insights error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 10 — SECTOR STRUCTURE
# ─────────────────────────────────────────────────────────────────

@app.route("/api/sectors")
def sectors():
    try:
        from classification import MARKET_CLASSIFICATION
        out = {}
        for sector, data in MARKET_CLASSIFICATION.items():
            out[sector] = {
                "nifty_weight": data.get("sector_nifty_weight", 0),
                "macro_drivers": data.get("macro_drivers", []),
                "subsectors": list(data.get("subsectors", {}).keys()),
            }
        return success({"sectors": out})
    except Exception as exc:
        return error(f"Sectors error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 11 — SECTOR PERFORMANCE HISTORY
# ─────────────────────────────────────────────────────────────────

@app.route("/api/sector-performance")
def sector_performance():
    try:
        from database import get_session, SectorPerformance
        from pipeline_utils import get_pipeline_date
        days = int(request.args.get("days", 30))
        pd_date = get_pipeline_date()
        since = pd_date - timedelta(days=days)

        session = get_session()
        try:
            rows = session.query(SectorPerformance).filter(
                SectorPerformance.date >= since
            ).order_by(SectorPerformance.date.desc()).all()
        finally:
            session.close()

        out = [{
            "date":            str(r.date),
            "sector":          r.sector,
            "subsector":       r.subsector,
            "sector_return":   r.sector_return_pct,
            "subsector_return": r.subsector_return_pct,
            "macro_alignment": r.macro_alignment,
            "regime_label":    r.regime_label,
            "top_company":     r.top_company,
        } for r in rows]

        return success({"sector_performance": out, "count": len(out)})
    except Exception as exc:
        return error(f"Sector performance error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 12 — TRIGGER PIPELINE JOBS (async)
# ─────────────────────────────────────────────────────────────────

def _run_job(job_fn):
    """Runs a job in a background thread."""
    global _job_status
    _job_status["running"] = True
    _job_status["started_at"] = datetime.utcnow().isoformat()
    try:
        result = job_fn()
        _job_status["result"] = "success"
    except Exception as exc:
        _job_status["result"] = f"error: {str(exc)}"
    finally:
        _job_status["running"] = False


# ─────────────────────────────────────────────────────────────────
# ROUTE 12b — MACRO HISTORY (for dashboard charts)
# ─────────────────────────────────────────────────────────────────

@app.route("/api/macro-history")
def macro_history():
    try:
        from database import get_session, MacroData
        from pipeline_utils import get_pipeline_date
        days = int(request.args.get("days", 30))
        pd_date = get_pipeline_date()
        since = pd_date - timedelta(days=days)

        session = get_session()
        try:
            rows = session.query(MacroData).filter(
                MacroData.date >= since
            ).order_by(MacroData.date.asc()).all()
        finally:
            session.close()

        out = [{
            "date":         str(r.date),
            "nifty_close":  r.nifty_close,
            "nifty_return": r.nifty_return,
            "india_vix":    r.india_vix,
            "brent_crude":  r.brent_crude,
            "usdinr":       r.usdinr,
            "fii_net_crore": r.fii_net_crore,
            "gold_close":   r.gold_close,
        } for r in rows if r.nifty_close and r.nifty_close > 0]

        return success({"macro_history": out, "days": days, "count": len(out)})
    except Exception as exc:
        return error(f"Macro history error: {str(exc)}")


@app.route("/api/run/fetch", methods=["POST"])
def run_fetch():
    if _job_status["running"]:
        return error("A job is already running. Please wait.", 409)
    try:
        from data_loader import run_data_loader
        t = threading.Thread(target=_run_job, args=(run_data_loader,), daemon=True)
        t.start()
        return success({"message": "Data fetch started in background"})
    except Exception as exc:
        return error(f"Could not start fetch job: {str(exc)}")


@app.route("/api/run/daily", methods=["POST"])
def run_daily():
    if _job_status["running"]:
        return error("A job is already running. Please wait.", 409)
    try:
        import main as m
        t = threading.Thread(target=_run_job, args=(m.run_daily_pipeline,), daemon=True)
        t.start()
        return success({"message": "Daily pipeline started in background"})
    except Exception as exc:
        return error(f"Could not start daily pipeline: {str(exc)}")


@app.route("/api/run/status")
def run_status():
    return success({"job": _job_status})


# ─────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═"*60)
    print("  MarketOS API Gateway v2.0")
    print("  http://localhost:5001")
    print("  Press Ctrl+C to stop")
    print("═"*60 + "\n")

    # Ensure DB is ready before accepting requests
    try:
        from database import ensure_tables_exist
        ensure_tables_exist()
        print("  ✓ Database ready")
    except Exception as e:
        print(f"  ⚠ Database warning: {e}")

    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
