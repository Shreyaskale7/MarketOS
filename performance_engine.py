# performance_engine.py
# MarketOS — Performance Analytics Engine
#
# Tracks:
#   1. Prediction accuracy (% correct direction) from PredictionAccuracy table
#   2. Forecast error (MAE, RMSE) per sector and horizon
#   3. Alpha vs NIFTY benchmark
#   4. Information ratio
#   5. Hit ratio per sector
#
# Reads from DB — no external dependencies beyond existing schema.
#
# Usage:
#   from performance_engine import compute_performance_summary
#   perf = compute_performance_summary()

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from database import get_session, PredictionAccuracy, MacroData, DailyPrice
import warnings
warnings.filterwarnings("ignore")

RISK_FREE_ANNUAL = 0.065   # 6.5% annualised


# ─────────────────────────────────────────────────────────────────
# SECTION 1 — PREDICTION ACCURACY FROM DB
# ─────────────────────────────────────────────────────────────────

def _load_prediction_records() -> pd.DataFrame:
    """Loads all PredictionAccuracy records from DB."""
    session = get_session()
    try:
        rows = session.query(PredictionAccuracy).all()
    except Exception:
        rows = []
    finally:
        session.close()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame([{
        "sector":            r.sector,
        "horizon":           r.horizon,
        "predicted_return":  float(r.predicted_return or 0.0),
        "actual_return":     float(r.actual_return or 0.0),
        "direction_correct": bool(r.direction_correct),
        "error_pct":         float(r.error_pct or 0.0),
        "evaluated_date":    r.evaluated_date,
    } for r in rows])


# ─────────────────────────────────────────────────────────────────
# SECTION 2 — NIFTY BENCHMARK RETURNS
# ─────────────────────────────────────────────────────────────────

def _load_nifty_returns(lookback_days: int = 365) -> pd.Series:
    """Loads NIFTY daily returns from MacroData table."""
    since   = datetime.today().date() - timedelta(days=lookback_days)
    session = get_session()
    try:
        rows = session.query(MacroData).filter(
            MacroData.date >= since
        ).order_by(MacroData.date).all()
    except Exception:
        rows = []
    finally:
        session.close()

    if not rows:
        return pd.Series(dtype=float)

    df = pd.DataFrame([{
        "date":         pd.Timestamp(r.date),
        # FIX 4: Use NaN for missing nifty_return instead of 0.0.
        # Storing 0.0 for non-trading days (weekends/holidays) artificially
        # drags the benchmark return toward zero and distorts Sharpe / IR.
        # NaN entries are forward-filled below so the series stays continuous.
        "nifty_return": float(r.nifty_return) if r.nifty_return is not None else np.nan,
    } for r in rows]).set_index("date").sort_index()

    # FIX 4: Forward-fill NaN gaps (weekends/holidays) with last known return,
    # then back-fill any leading NaNs at the start of the series.
    df["nifty_return"] = df["nifty_return"].ffill().bfill()

    return df["nifty_return"]


# ─────────────────────────────────────────────────────────────────
# SECTION 3 — CORE METRICS
# ─────────────────────────────────────────────────────────────────

def _compute_mae_rmse(df: pd.DataFrame) -> dict:
    """MAE and RMSE of predicted vs actual return."""
    errors   = df["predicted_return"] - df["actual_return"]
    mae      = float(errors.abs().mean())
    rmse     = float(np.sqrt((errors ** 2).mean()))
    bias     = float(errors.mean())   # positive = systematically over-predicting
    return {"mae": round(mae, 3), "rmse": round(rmse, 3), "bias": round(bias, 3)}


def _compute_information_ratio(alpha_series: pd.Series, nifty_series: pd.Series) -> float:
    """
    Information ratio = mean(active_return) / std(active_return)
    Active return = portfolio_return - benchmark_return.
    Uses daily returns aligned by date.
    """
    common = alpha_series.index.intersection(nifty_series.index)
    if len(common) < 5:
        return float("nan")
    active = alpha_series.loc[common] - nifty_series.loc[common]
    if active.std() < 1e-8:
        return float("nan")
    return float((active.mean() / active.std()) * np.sqrt(252))


def _compute_sharpe(returns: pd.Series, freq: str = "daily") -> float:
    """Annualised Sharpe ratio from a return series."""
    if len(returns) < 5 or returns.std() < 1e-8:
        return float("nan")
    rf_daily = RISK_FREE_ANNUAL / 252
    excess   = returns - rf_daily
    return float(excess.mean() / excess.std() * np.sqrt(252))


def _compute_max_drawdown(cum_returns: pd.Series) -> float:
    """Maximum drawdown from a cumulative return series."""
    rolling_max = cum_returns.cummax()
    drawdown    = (cum_returns - rolling_max) / rolling_max * 100
    return float(drawdown.min())


# ─────────────────────────────────────────────────────────────────
# SECTION 4 — PERFORMANCE SUMMARY
# ─────────────────────────────────────────────────────────────────

def compute_performance_summary(lookback_days: int = 365) -> dict:
    """
    Computes the full performance analytics summary.

    Returns:
    {
      "overall": {...},
      "by_horizon": {"1M": {...}, "3M": {...}, ...},
      "by_sector": {"Banking & Financial Services": {...}, ...},
      "nifty_benchmark": {...},
    }
    """
    print("\n=== PERFORMANCE ANALYTICS ENGINE ===")

    pred_df    = _load_prediction_records()
    nifty_rets = _load_nifty_returns(lookback_days)

    if pred_df.empty:
        print("  No evaluated forecasts yet — performance analytics unavailable.")
        print("  Forecasts need time to mature (1M = 30 days, 3M = 90 days).")
        return {
            "status":       "no_data",
            "message":      "No matured forecasts yet. Check back after 30+ days.",
            "overall":      {},
            "by_horizon":   {},
            "by_sector":    {},
        }

    print(f"  Loaded {len(pred_df)} evaluated forecast records")

    # ── Overall metrics ───────────────────────────────────────────
    overall_dir_acc = float(pred_df["direction_correct"].mean())
    overall_mae_rmse = _compute_mae_rmse(pred_df)
    win_rate         = float((pred_df["actual_return"] > 0).mean())

    overall = {
        "n_forecasts":         len(pred_df),
        "direction_accuracy":  round(overall_dir_acc, 4),
        "direction_accuracy_pct": round(overall_dir_acc * 100, 1),
        "mae_pct":             overall_mae_rmse["mae"],
        "rmse_pct":            overall_mae_rmse["rmse"],
        "bias_pct":            overall_mae_rmse["bias"],
        "win_rate_pct":        round(win_rate * 100, 1),
    }

    # OPTIONAL IMPROVEMENT: Model degradation early warning
    # Below 55% directional accuracy, the model is barely beating a coin flip.
    # Institutional systems typically retrain when accuracy degrades for 2+ weeks.
    if overall_dir_acc < 0.55:
        print(f"\n  ⚠ WARNING: Model performance degrading — "
              f"directional accuracy={overall_dir_acc*100:.1f}% (threshold: 55%)")
        print(f"  ⚠ Retraining recommended: run main.py --retrain")
    elif overall_dir_acc < 0.60:
        print(f"\n  ℹ NOTICE: Directional accuracy={overall_dir_acc*100:.1f}% — "
              f"monitoring recommended (threshold: 60%)")

    # ── By horizon ────────────────────────────────────────────────
    by_horizon = {}
    for horizon in pred_df["horizon"].unique():
        h_df = pred_df[pred_df["horizon"] == horizon]
        metrics = _compute_mae_rmse(h_df)
        by_horizon[horizon] = {
            "n_forecasts":          len(h_df),
            "direction_accuracy":   round(float(h_df["direction_correct"].mean()), 4),
            "direction_accuracy_pct": round(float(h_df["direction_correct"].mean()) * 100, 1),
            "mae_pct":              metrics["mae"],
            "rmse_pct":             metrics["rmse"],
            "bias_pct":             metrics["bias"],
        }

    # ── By sector ─────────────────────────────────────────────────
    by_sector = {}
    for sector in pred_df["sector"].unique():
        s_df = pred_df[pred_df["sector"] == sector]
        metrics = _compute_mae_rmse(s_df)
        dir_acc = float(s_df["direction_correct"].mean())
        by_sector[sector] = {
            "n_forecasts":          len(s_df),
            "direction_accuracy":   round(dir_acc, 4),
            "hit_ratio_pct":        round(dir_acc * 100, 1),
            "mae_pct":              metrics["mae"],
            "bias_pct":             metrics["bias"],
            "grade": ("A" if dir_acc >= 0.65 else
                      "B" if dir_acc >= 0.55 else
                      "C" if dir_acc >= 0.50 else "D"),
        }

    # ── Benchmark: NIFTY metrics ──────────────────────────────────
    nifty_benchmark = {}
    if not nifty_rets.empty:
        nifty_rets_frac = nifty_rets / 100.0
        cum_nifty       = (1 + nifty_rets_frac).cumprod()
        nifty_ann_ret   = float((cum_nifty.iloc[-1]) ** (252 / len(nifty_rets)) - 1) * 100
        nifty_sharpe    = _compute_sharpe(nifty_rets_frac)
        nifty_drawdown  = _compute_max_drawdown(cum_nifty)

        nifty_benchmark = {
            "period_days":           len(nifty_rets),
            "annualised_return_pct": round(nifty_ann_ret, 2),
            "sharpe_ratio":          round(nifty_sharpe, 3) if not np.isnan(nifty_sharpe) else None,
            "max_drawdown_pct":      round(nifty_drawdown, 2),
        }

    # ── Print summary ─────────────────────────────────────────────
    print(f"\n  OVERALL PERFORMANCE")
    print(f"  Forecasts evaluated    : {overall['n_forecasts']}")
    print(f"  Direction accuracy     : {overall['direction_accuracy_pct']}%")
    print(f"  MAE                    : {overall['mae_pct']}%")
    print(f"  RMSE                   : {overall['rmse_pct']}%")
    print(f"  Bias                   : {overall['bias_pct']:+.3f}% "
          f"({'over-predicting' if overall['bias_pct'] > 0 else 'under-predicting'})")

    if by_horizon:
        print(f"\n  BY HORIZON:")
        print(f"  {'Horizon':<8} {'N':>5} {'DirAcc':>8} {'MAE':>7} {'Bias':>8}")
        print(f"  {'-'*45}")
        for h in sorted(by_horizon.keys()):
            m = by_horizon[h]
            print(f"  {h:<8} {m['n_forecasts']:>5} {m['direction_accuracy_pct']:>7.1f}% "
                  f"{m['mae_pct']:>6.2f}% {m['bias_pct']:>+7.2f}%")

    if by_sector:
        print(f"\n  SECTOR HIT RATIOS (top 5):")
        top5 = sorted(by_sector.items(), key=lambda x: x[1]["hit_ratio_pct"], reverse=True)[:5]
        for sec, m in top5:
            print(f"  {sec[:35]:<35}  {m['hit_ratio_pct']:>5.1f}%  [{m['grade']}]  n={m['n_forecasts']}")

    if nifty_benchmark:
        print(f"\n  NIFTY BENCHMARK ({nifty_benchmark['period_days']} days):")
        print(f"  Annualised return : {nifty_benchmark['annualised_return_pct']:+.2f}%")
        if nifty_benchmark['sharpe_ratio'] is not None:
            print(f"  Sharpe ratio      : {nifty_benchmark['sharpe_ratio']:.3f}")
        print(f"  Max drawdown      : {nifty_benchmark['max_drawdown_pct']:.2f}%")

    return {
        "status":          "ok",
        "generated_at":    datetime.today().strftime("%Y-%m-%d %H:%M"),
        "overall":         overall,
        "by_horizon":      by_horizon,
        "by_sector":       by_sector,
        "nifty_benchmark": nifty_benchmark,
    }


# ─────────────────────────────────────────────────────────────────
# STANDALONE
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = compute_performance_summary()
    if result["status"] == "no_data":
        print(result["message"])
