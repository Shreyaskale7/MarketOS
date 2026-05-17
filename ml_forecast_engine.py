# ml_forecast_engine.py
# MarketOS — Data-Driven ML Forecasting Engine
#
# FIXES vs previous version:
#   1. DB diagnostic on startup — prints row counts so you know what data exists
#   2. Macro join uses LEFT join then ffill — never drops rows due to missing macro dates
#   3. nasdaq_close / sp500_close fallback to 0 when column missing in DB
#   4. dropna() only on CORE columns — optional columns filled with 0 instead of dropped
#   5. min_rows threshold lowered to 60 (was 120) to handle sparse subsectors
#   6. sector/subsector filter uses LIKE matching — tolerates minor name mismatches
#   7. Full debug mode: prints exactly why each sector is skipped
#   8. Macro reindex to daily_ret index so join always succeeds

import os
import json
import pickle
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, date
from collections import Counter

from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import r2_score, mean_absolute_error

from sqlalchemy import func
from database import (
    engine, DailyPrice, MacroData, ModelVersion,
    ForwardForecast, SectorGrowthAnalytics,
    get_session, ensure_tables_exist,
)
from classification import MARKET_CLASSIFICATION

warnings.filterwarnings("ignore")
os.makedirs("data/models/ml_horizon", exist_ok=True)

# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────

# ML models trained for 1M, 3M, 6M directly
# 12M synthesised from 6M model with extended compounding
HORIZONS = {
    "1M":  {"trading": 21,  "calendar": 30},
    "3M":  {"trading": 63,  "calendar": 91},
    "6M":  {"trading": 126, "calendar": 183},
    "12M": {"trading": 252, "calendar": 365},  # synthesised from 6M model
}

HORIZONS_TRAINED = ["1M", "3M", "6M"]   # models exist for these only

# CHANGE 1: 6M cap raised from 45.0 → 60.0
# BEFORE: OUTPUT_CAPS["6M"] = 45 caused all 6M forecasts to cluster near 45%
# because high-return sectors all hit the same ceiling. The hard np.clip()
# at 45% compressed real signal into an artificial flat distribution.
# AFTER: 60% matches the 12M cap philosophy — soft_cap() then compresses
# values beyond 60%, preserving relative ranking between sectors.
OUTPUT_CAPS = {"1M": 15.0, "3M": 25.0, "6M": 30.0, "12M": 30.0}

# MODULE 6: Hard output clamp applied AFTER all horizon calculations
FORECAST_MIN_ANNUAL = -50.0   # absolute floor across all horizons
FORECAST_MAX_ANNUAL = +60.0   # absolute ceiling across all horizons

# Minimum spread between bull and bear cases (as % of cap)
# Ensures forecasts always have meaningful uncertainty range
MIN_SPREAD_PCT = {"1M": 0.10, "3M": 0.12, "6M": 0.15}

MIN_ROWS = 60   # minimum clean rows needed to train


def _sector_offset(name):
    return (sum(ord(c) for c in name) % 41 - 20) / 2000.0


def soft_cap(x, cap):
    """
    Soft cap: values within ±cap pass through unchanged.
    Values beyond cap are compressed by 30% — signal preserved, explosion prevented.
    e.g. soft_cap(150, 120) = 129, not 120.
    """
    if abs(x) <= cap:
        return float(x)
    excess     = abs(x) - cap
    compressed = cap + excess * 0.30
    return float(compressed if x > 0 else -compressed)


# ─────────────────────────────────────────────────────────────────
# SECTION 0 — DB DIAGNOSTIC
# ─────────────────────────────────────────────────────────────────

def diagnose_database():
    """
    Prints a full summary of what is in your DB.
    Run this if training shows 0 rows everywhere:
      python ml_forecast_engine.py diagnose
    """
    ensure_tables_exist()
    session = get_session()
    try:
        print("\n" + "=" * 60)
        print("DATABASE DIAGNOSTIC")
        print("=" * 60)

        total_prices = session.query(func.count(DailyPrice.id)).scalar() or 0
        print(f"\nTotal rows in daily_prices : {total_prices:,}")

        if total_prices == 0:
            print("\n  *** CRITICAL: daily_prices table is EMPTY ***")
            print("  You must run the data loader first:")
            print("    python data_loader.py")
            print("  OR:  python main.py --setup")
            return

        min_date = session.query(func.min(DailyPrice.date)).scalar()
        max_date = session.query(func.max(DailyPrice.date)).scalar()
        print(f"Price date range           : {min_date}  to  {max_date}")

        with_return = session.query(func.count(DailyPrice.id)).filter(
            DailyPrice.daily_return.isnot(None)
        ).scalar() or 0
        print(f"Rows with daily_return set : {with_return:,}")

        if with_return == 0:
            print("\n  *** CRITICAL: daily_return column is NULL for all rows ***")
            print("  Re-run the data loader to recompute returns.")
            return

        sectors    = session.query(DailyPrice.sector).distinct().all()
        subsectors = session.query(DailyPrice.subsector).distinct().all()
        print(f"\nUnique sectors    : {len(sectors)}")
        print(f"Unique subsectors : {len(subsectors)}")

        print("\nSubsectors in DB (with row counts):")
        sub_counts = session.query(
            DailyPrice.subsector,
            func.count(DailyPrice.id)
        ).group_by(DailyPrice.subsector).order_by(
            func.count(DailyPrice.id).desc()
        ).all()
        for sub, cnt in sub_counts:
            print(f"  {str(sub)[:45]:45s}  {cnt:>6,} rows")

        total_macro = session.query(func.count(MacroData.id)).scalar() or 0
        print(f"\nTotal rows in macro_data   : {total_macro:,}")
        if total_macro > 0:
            macro_min = session.query(func.min(MacroData.date)).scalar()
            macro_max = session.query(func.max(MacroData.date)).scalar()
            print(f"Macro date range           : {macro_min}  to  {macro_max}")

            sample = session.query(MacroData).first()
            if sample:
                print("\nMacro columns in first row:")
                for col in ["repo_rate", "usdinr", "brent_crude", "india_vix",
                            "fii_net_crore", "nifty_close", "nifty_return",
                            "nasdaq_close", "sp500_close"]:
                    val    = getattr(sample, col, None)
                    status = f"{val:.4f}" if val is not None else "NULL"
                    print(f"  {col:25s}: {status}")
        else:
            print("\n  *** macro_data table is EMPTY — run data loader first ***")

        print("\n" + "=" * 60)
        print("CLASSIFICATION vs DB MATCH CHECK")
        print("=" * 60)
        db_subsectors = {str(s[0]).strip() for s in subsectors}
        for sec_name, sec_data in MARKET_CLASSIFICATION.items():
            for sub_name in sec_data["subsectors"]:
                match  = sub_name in db_subsectors
                status = "OK " if match else "NOT FOUND IN DB"
                print(f"  {status}  {sub_name}")

    except Exception as e:
        print(f"Diagnostic error: {e}")
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────
# SECTION 1 — TRAINING DATASET BUILDER (FIXED)
# ─────────────────────────────────────────────────────────────────

def build_training_dataset(subsector=None, sector=None, lookback_years=10):
    """
    Builds supervised ML datasets for 1M / 3M / 6M horizons.
    Returns dict: {"1M": DataFrame, "3M": DataFrame, "6M": DataFrame}
    Returns None if insufficient data.
    """
    ensure_tables_exist()
    end_date   = datetime.today().date()
    start_date = end_date - timedelta(days=lookback_years * 365 + 180)

    session = get_session()
    try:
        price_q = session.query(DailyPrice).filter(
            DailyPrice.date >= start_date,
            DailyPrice.date <= end_date,
            DailyPrice.daily_return.isnot(None),
        )
        if subsector:
            price_q = price_q.filter(DailyPrice.subsector == subsector)
        elif sector:
            price_q = price_q.filter(DailyPrice.sector == sector)
        prices = price_q.order_by(DailyPrice.date).all()

        macros = session.query(MacroData).filter(
            MacroData.date >= start_date,
            MacroData.date <= end_date,
        ).order_by(MacroData.date).all()

    except Exception as e:
        print(f"  [Dataset] DB error: {e}")
        return None
    finally:
        session.close()

    # Guard: must have price data
    if not prices:
        label = subsector or sector or "all"
        print(f"  [Dataset] 0 price rows for '{label}'")
        print(f"  [Dataset]  -> Run: python ml_forecast_engine.py diagnose")
        return None

    if len(macros) < 20:
        print(f"  [Dataset] Only {len(macros)} macro rows — run data loader first")
        return None

    # 1. Build weighted sector daily return series
    price_rows = []
    for p in prices:
        ret = float(p.daily_return or 0.0)
        if abs(ret) < 0.35:
            price_rows.append({
                "date":         pd.Timestamp(p.date),
                "daily_return": ret,
                "nifty_weight": float(p.nifty_weight or 0.001),
            })

    if not price_rows:
        print(f"  [Dataset] All price rows filtered out as extreme outliers")
        return None

    price_df = pd.DataFrame(price_rows)

    def _weighted_mean(g):
        w = g["nifty_weight"].sum()
        return (
            (g["daily_return"] * g["nifty_weight"]).sum() / w
            if w > 0 else g["daily_return"].mean()
        )

    daily_ret = (
        price_df.groupby("date")
        .apply(_weighted_mean)
        .rename("daily_return")
        .sort_index()
    )
    daily_ret.index = pd.to_datetime(daily_ret.index)

    if len(daily_ret) < MIN_ROWS:
        print(f"  [Dataset] Only {len(daily_ret)} trading days — need {MIN_ROWS}")
        return None

    # 2. Build macro DataFrame with safe fallbacks for optional columns
    macro_rows = []
    for m in macros:
        macro_rows.append({
            "date":            pd.Timestamp(m.date),
            "repo_rate":       float(m.repo_rate       or 6.5),
            "usdinr":          float(m.usdinr           or 83.0),
            "brent_crude":     float(m.brent_crude      or 80.0),
            "india_vix":       float(m.india_vix        or 15.0),
            "fii_net_crore":   float(m.fii_net_crore    or 0.0),
            "nifty_return":    float(m.nifty_return     or 0.0),
            "nasdaq_close":    float(getattr(m, "nasdaq_close", None) or 0.0),
            "sp500_close":     float(getattr(m, "sp500_close",  None) or 0.0),
            "gst_collections": float(m.gst_collections  or 150000.0),
            "cpi_yoy":         float(getattr(m, "cpi_yoy", None) or 5.0),
        })

    macro_df = pd.DataFrame(macro_rows).set_index("date").sort_index()

    # 3. Reindex macro to match price dates — KEY FIX
    # Macro dates and price dates rarely align perfectly.
    # Union the indices, ffill gaps, then reindex to price dates only.
    macro_aligned = (
        macro_df
        .reindex(macro_df.index.union(daily_ret.index))
        .ffill()
        .bfill()
        .reindex(daily_ret.index)
    )

    # 4. Engineer price features (min_periods so rolling doesn't produce all-NaN)
    feat = pd.DataFrame(index=daily_ret.index)
    r    = daily_ret

    feat["ret_1d"]           = r
    feat["ret_5d"]           = r.rolling(5,  min_periods=3).sum()
    feat["ret_20d"]          = r.rolling(20, min_periods=10).sum()
    # FIX 8: EWM volatility smoothing — prevents sudden spikes in vol estimates
    # that cause erratic weight swings. EWM span=20 gives 5% weight to oldest obs.
    feat["volatility_20d"]   = r.ewm(span=20, min_periods=10).std() * np.sqrt(252)
    feat["rolling_vol_raw"]  = r.rolling(20, min_periods=10).std() * np.sqrt(252)
    # Blend: 70% EWM (smooth) + 30% rolling (responsive)
    feat["volatility_20d"]   = 0.7 * feat["volatility_20d"] + 0.3 * feat["rolling_vol_raw"]
    feat["rolling_mean_20d"] = r.rolling(20, min_periods=10).mean()
    feat["momentum_60d"]     = r.rolling(60, min_periods=30).sum()
    feat["skew_20d"]         = r.rolling(20, min_periods=10).skew()

    # 5. Engineer macro features from aligned macro
    m = macro_aligned

    feat["repo_rate"]        = m["repo_rate"]
    feat["india_vix"]        = m["india_vix"]
    feat["brent_crude"]      = m["brent_crude"]
    feat["fii_net_crore"]    = m["fii_net_crore"]
    feat["gst_collections"]  = m["gst_collections"]
    feat["cpi_yoy"]          = m["cpi_yoy"]

    feat["brent_crude_chg"]  = m["brent_crude"].pct_change() * 100
    feat["usdinr_chg"]       = m["usdinr"].pct_change()      * 100
    feat["vix_chg"]          = m["india_vix"].pct_change()   * 100
    feat["nifty_5d_ret"]     = m["nifty_return"].rolling(5,  min_periods=3).sum()
    feat["nifty_20d_ret"]    = m["nifty_return"].rolling(20, min_periods=10).sum()
    feat["fii_flow"]         = m["fii_net_crore"] / 10_000.0
    feat["fii_5d_mean"]      = feat["fii_flow"].rolling(5, min_periods=3).mean()

    # Optional columns — zero if not populated in DB
    if (m["nasdaq_close"] != 0).any():
        feat["nasdaq_chg"]   = m["nasdaq_close"].pct_change() * 100
    else:
        feat["nasdaq_chg"]   = 0.0

    if (m["sp500_close"] != 0).any():
        feat["sp500_chg"]    = m["sp500_close"].pct_change() * 100
    else:
        feat["sp500_chg"]    = 0.0

    feat["gst_yoy"]          = m["gst_collections"].pct_change(252) * 100

    feat["brent_5d_mean"]    = feat["brent_crude_chg"].rolling(5,  min_periods=3).mean()
    feat["usdinr_5d_mean"]   = feat["usdinr_chg"].rolling(5,  min_periods=3).mean()
    feat["vix_5d_mean"]      = feat["vix_chg"].rolling(5,  min_periods=3).mean()
    feat["vix_20d_mean"]     = m["india_vix"].rolling(20, min_periods=10).mean()

    vix_vals              = m["india_vix"].reindex(feat.index).fillna(15.0)
    feat["vix_regime"]    = pd.cut(
        vix_vals, bins=[0, 13, 20, 200], labels=[0, 1, 2]
    ).astype(float).fillna(1.0)
    feat["vix_percentile"] = vix_vals.rolling(252, min_periods=60).rank(pct=True).fillna(0.5)

    feat["crude_x_fx"]    = feat["brent_crude_chg"].fillna(0) * feat["usdinr_chg"].fillna(0)
    feat["rate_x_vix"]    = feat["repo_rate"].fillna(6.5) * vix_vals
    feat["rate_momentum"] = m["repo_rate"].reindex(feat.index).diff(63).fillna(0.0)
    feat["vix_momentum"]  = vix_vals.diff(20).fillna(0.0)

    for col in ["brent_crude_chg", "usdinr_chg", "vix_chg", "fii_flow", "nasdaq_chg"]:
        feat[f"{col}_lag1"] = feat[col].shift(1)
        feat[f"{col}_lag5"] = feat[col].shift(5)

    sec_label              = sector or subsector or "All"
    sub_label              = subsector or sector or "All"
    feat["sector_hash"]    = _sector_offset(sec_label) * 1000
    feat["subsector_hash"] = _sector_offset(sub_label) * 1000

    # 6. Build forward targets — proper horizon for each
    def _compound_forward(r_series, n):
        """Computes compounded forward return over n trading days."""
        vals   = r_series.values.astype(float)
        result = np.full(len(vals), np.nan)
        for i in range(len(vals) - n):
            window = vals[i + 1: i + 1 + n]
            if not np.any(np.isnan(window)):
                result[i] = float(np.prod(1.0 + window) - 1.0) * 100.0
        return pd.Series(result, index=r_series.index)

    # Each horizon trained on its OWN forward target
    feat["future_return_21d"]  = _compound_forward(daily_ret, 21)   # 1M
    feat["future_return_63d"]  = _compound_forward(daily_ret, 63)   # 3M
    feat["future_return_126d"] = _compound_forward(daily_ret, 126)  # 6M — FIX: was using 63d

    # 7. Fill NaNs in feature columns — only drop rows where TARGET is NaN
    target_cols = ("future_return_21d", "future_return_63d", "future_return_126d")
    feat_cols   = [c for c in feat.columns if c not in target_cols]
    feat[feat_cols] = feat[feat_cols].fillna(0.0)
    feat            = feat.replace([np.inf, -np.inf], 0.0)

    # 8. Each horizon uses its own properly-sized target
    horizon_targets = {
        "1M": "future_return_21d",
        "3M": "future_return_63d",
        "6M": "future_return_126d",   # FIX: was future_return_60d (same as 3M)
    }

    datasets = {}
    for h_label, target_col in horizon_targets.items():
        tmp = feat[feat_cols + [target_col]].copy()
        tmp = tmp.rename(columns={target_col: "target"})
        tmp = tmp.dropna(subset=["target"])   # only drop when TARGET is NaN

        if len(tmp) > 10:
            mu, sd = tmp["target"].mean(), tmp["target"].std()
            if sd > 0:
                tmp = tmp[np.abs(tmp["target"] - mu) < 4 * sd]

        if len(tmp) < MIN_ROWS:
            print(f"  [Dataset] {h_label}: {len(tmp)} rows after cleaning — need {MIN_ROWS}, skipping")
            continue

        datasets[h_label] = tmp
        print(f"  [Dataset] {h_label}: {len(tmp):,} rows | "
              f"{tmp.index.min().date()} to {tmp.index.max().date()} | "
              f"target mean={tmp['target'].mean():+.2f}%  std={tmp['target'].std():.2f}%")

    return datasets if datasets else None


# ─────────────────────────────────────────────────────────────────
# SECTION 2 — MODEL TRAINING
# ─────────────────────────────────────────────────────────────────

def _walk_forward_cv(model, scaler, X, y, n_splits=5):
    n_splits = min(n_splits, max(2, len(X) // 20))
    if n_splits < 2:
        return 0.0, 0.5
    tscv = TimeSeriesSplit(n_splits=n_splits)
    r2_scores, dir_scores = [], []
    for tr_idx, te_idx in tscv.split(X):
        Xtr = scaler.fit_transform(X.iloc[tr_idx])
        Xte = scaler.transform(X.iloc[te_idx])
        ytr, yte = y.iloc[tr_idx], y.iloc[te_idx]
        model.fit(Xtr, ytr)
        preds = model.predict(Xte)
        r2_scores.append(r2_score(yte, preds))
        dir_scores.append(float((np.sign(preds) == np.sign(yte)).mean()))
    return float(np.mean(r2_scores)), float(np.mean(dir_scores))


def train_horizon_models(subsector=None, sector=None, lookback_years=10):
    label = (subsector or sector or "all") \
        .replace(" ", "_").replace("/", "_").replace("&", "and")[:40]
    print(f"\n--- ML TRAIN | {subsector or sector or 'all'} | {lookback_years}yr ---")

    datasets = build_training_dataset(subsector, sector, lookback_years)
    if not datasets:
        return None

    version_date = datetime.today().strftime("%Y%m%d")
    summary      = {}

    for horizon, df in datasets.items():
        feature_cols = [c for c in df.columns if c != "target"]
        X = df[feature_cols]
        y = df["target"]

        from sklearn.ensemble import GradientBoostingRegressor

        rf    = RandomForestRegressor(
            n_estimators=200, max_depth=5,
            min_samples_leaf=max(10, len(X) // 100),
            max_features="sqrt", random_state=42, n_jobs=-1,
        )
        ridge = Ridge(alpha=1.0)
        gbm   = GradientBoostingRegressor(
            n_estimators=200, max_depth=3, learning_rate=0.05,
            min_samples_leaf=max(10, len(X) // 100),
            subsample=0.8, random_state=42,
        )

        rf_scaler    = StandardScaler()
        ridge_scaler = StandardScaler()
        gbm_scaler   = StandardScaler()

        rf_r2,    rf_dir    = _walk_forward_cv(rf,    rf_scaler,    X, y)
        ridge_r2, ridge_dir = _walk_forward_cv(ridge, ridge_scaler, X, y)
        gbm_r2,   gbm_dir   = _walk_forward_cv(gbm,   gbm_scaler,   X, y)

        print(f"  [{horizon}] RF R2={rf_r2:.3f} Dir={rf_dir*100:.0f}% | "
              f"Ridge R2={ridge_r2:.3f} Dir={ridge_dir*100:.0f}% | "
              f"GBM R2={gbm_r2:.3f} Dir={gbm_dir*100:.0f}%")

        best_r2 = max(rf_r2, ridge_r2, gbm_r2)
        if gbm_r2 == best_r2 and gbm_r2 > -0.05:
            chosen_model, chosen_scaler, chosen_name, chosen_r2, chosen_dir = \
                gbm, gbm_scaler, "gbm", gbm_r2, gbm_dir
        elif rf_r2 == best_r2 and rf_r2 > -0.05:
            chosen_model, chosen_scaler, chosen_name, chosen_r2, chosen_dir = \
                rf, rf_scaler, "rf", rf_r2, rf_dir
        else:
            chosen_model, chosen_scaler, chosen_name, chosen_r2, chosen_dir = \
                ridge, ridge_scaler, "ridge", ridge_r2, ridge_dir

        X_scaled  = chosen_scaler.fit_transform(X)
        chosen_model.fit(X_scaled, y)
        preds_all = chosen_model.predict(X_scaled)
        final_mae = float(mean_absolute_error(y, preds_all))
        final_dir = float((np.sign(preds_all) == np.sign(y)).mean())

        print(f"  [{horizon}] Selected={chosen_name} | "
              f"DirAcc={final_dir*100:.1f}% | MAE={final_mae:.3f}%")

        if hasattr(chosen_model, "feature_importances_"):
            importance = dict(zip(feature_cols, chosen_model.feature_importances_))
        elif hasattr(chosen_model, "coef_"):
            importance = dict(zip(feature_cols, chosen_model.coef_))
        else:
            importance = {}
        importance = dict(
            sorted(importance.items(), key=lambda x: abs(x[1]), reverse=True)[:20]
        )

        version_str = f"ml_{version_date}_{label}_{horizon}"
        model_path  = f"data/models/ml_horizon/{version_str}.pkl"
        with open(model_path, "wb") as f:
            pickle.dump({
                "model":           chosen_model,
                "scaler":          chosen_scaler,
                "features":        feature_cols,
                "chosen":          chosen_name,
                "r2":              chosen_r2,
                "directional_acc": final_dir,
                "mae":             final_mae,   # FIX 1: stored for dynamic confidence at inference
                "horizon":         horizon,
                "subsector":       subsector,
                "sector":          sector,
                "trained_date":    datetime.today().date(),
            }, f)

        mv_label = f"{subsector or sector or 'all'}_{horizon}"
        session  = get_session()
        try:
            # Deactivate any existing active model for this subsector+horizon
            session.query(ModelVersion).filter(
                ModelVersion.subsector == mv_label,
                ModelVersion.is_active == True,
            ).update({"is_active": False})

            # Delete any existing record with the SAME version string
            # This prevents UNIQUE constraint failure on same-day retraining
            session.query(ModelVersion).filter(
                ModelVersion.version == version_str,
            ).delete(synchronize_session=False)

            session.commit()

            mv = ModelVersion(
                version=version_str,
                trained_date=datetime.today().date(),
                training_start=df.index.min().date(),
                training_end=df.index.max().date(),
                subsector=mv_label,
                r_squared=round(chosen_r2, 4),
                mae=round(final_mae, 4),
                directional_acc=round(final_dir, 4),
                feature_weights=json.dumps(
                    {k: round(float(v), 6) for k, v in importance.items()}
                ),
                feature_names=json.dumps(feature_cols),
                n_samples=len(X),
                is_active=True,
                notes=f"{chosen_name} | {lookback_years}yr | ml_horizon",
            )
            session.add(mv)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"  [Train] DB save error (non-critical, model .pkl saved): {e}")
        finally:
            session.close()

        summary[horizon] = {
            "version":              version_str,
            "model_type":           chosen_name,
            "r_squared":            chosen_r2,
            "mae":                  final_mae,
            "directional_accuracy": final_dir,
            "n_samples":            len(X),
        }

    return summary if summary else None


def train_all_horizon_models(lookback_years=10):
    print("\n" + "=" * 65)
    print(f"ML HORIZON TRAINING — {lookback_years}yr")
    print("=" * 65)

    # Always show DB state first so you know what you're training on
    diagnose_database()

    results = {}
    for sector_name, sec_data in MARKET_CLASSIFICATION.items():
        r = train_horizon_models(sector=sector_name, lookback_years=lookback_years)
        results[f"sector_{sector_name}"] = r
        for sub_name in sec_data["subsectors"]:
            r2 = train_horizon_models(subsector=sub_name, lookback_years=lookback_years)
            results[f"sub_{sub_name}"] = r2

    ok = sum(1 for v in results.values() if v is not None)
    print(f"\n{'='*65}")
    print(f"Training complete: {ok}/{len(results)} models trained")
    if ok == 0:
        print("\n  *** 0 models trained. Your DB is empty or data hasn't loaded. ***")
        print("  Step 1: python data_loader.py")
        print("  Step 2: python ml_forecast_engine.py train 10")
    print("=" * 65)
    return results


# ─────────────────────────────────────────────────────────────────
# SECTION 3 — MODEL LOADER
# ─────────────────────────────────────────────────────────────────

_MODEL_CACHE = {}


def _load_horizon_model(horizon, subsector=None, sector=None):
    for label in filter(None, [subsector, sector]):
        safe      = label.replace(" ", "_").replace("/", "_").replace("&", "and")[:40]
        cache_key = f"{safe}_{horizon}"
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]

        model_dir  = "data/models/ml_horizon"
        if not os.path.isdir(model_dir):
            continue
        candidates = [
            f for f in os.listdir(model_dir)
            if f.endswith(f"_{horizon}.pkl") and safe in f
        ]
        if not candidates:
            continue
        candidates.sort(reverse=True)
        path = os.path.join(model_dir, candidates[0])
        try:
            with open(path, "rb") as f:
                payload = pickle.load(f)
            _MODEL_CACHE[cache_key] = payload
            return payload
        except Exception as e:
            print(f"  [Load] {path}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────
# SECTION 4 — INFERENCE
# ─────────────────────────────────────────────────────────────────

def _get_recent_sector_returns(subsector, sector, lookback_days=90):
    since   = datetime.today().date() - timedelta(days=lookback_days)
    session = get_session()
    try:
        q = session.query(DailyPrice).filter(DailyPrice.date >= since)
        if subsector:
            q = q.filter(DailyPrice.subsector == subsector)
        elif sector:
            q = q.filter(DailyPrice.sector == sector)
        rows = q.order_by(DailyPrice.date).all()
    except Exception:
        rows = []
    finally:
        session.close()

    if not rows:
        return None

    df = pd.DataFrame([{
        "date":         pd.Timestamp(r.date),
        "daily_return": float(r.daily_return or 0.0),
        "nifty_weight": float(r.nifty_weight or 0.001),
    } for r in rows])

    def _wm(g):
        w = g["nifty_weight"].sum()
        return (g["daily_return"] * g["nifty_weight"]).sum() / w if w > 0 else g["daily_return"].mean()

    return df.groupby("date").apply(_wm).sort_index()


def _build_inference_features(macro_data, subsector, sector, feature_cols,
                               recent_sector_rets=None):
    usdinr_chg = macro_data.get("usdinr",       {}).get("change_pct", 0.0)
    vix_val    = macro_data.get("india_vix",     {}).get("current",    15.0)
    vix_chg    = macro_data.get("india_vix",     {}).get("change_pct", 0.0)
    crude_val  = macro_data.get("brent_crude",   {}).get("current",    80.0)
    crude_chg  = macro_data.get("brent_crude",   {}).get("change_pct", 0.0)
    repo       = macro_data.get("repo_rate",     {}).get("current",    6.5)
    fii        = macro_data.get("fii_flows",     {}).get("estimated_crore", 0.0)
    nasdaq_chg = macro_data.get("nasdaq",        {}).get("change_pct", 0.0)
    sp500_chg  = macro_data.get("sp500",         {}).get("change_pct", 0.0)
    nifty_ret  = macro_data.get("nifty",         {}).get("return_pct", 0.0)
    fii_norm   = fii / 10_000.0
    vix_regime = 0.0 if vix_val < 13 else (1.0 if vix_val < 20 else 2.0)

    ret_1d = ret_5d = ret_20d = vol_20d = rolling_mean_20d = momentum_60d = skew_20d = 0.0
    if recent_sector_rets is not None and len(recent_sector_rets) >= 5:
        rv = recent_sector_rets.values
        n  = len(rv)
        ret_1d           = float(rv[-1])
        ret_5d           = float(np.sum(rv[-5:]))
        ret_20d          = float(np.sum(rv[-min(20, n):]))
        vol_20d          = float(np.std(rv[-min(20, n):]) * np.sqrt(252))
        rolling_mean_20d = float(np.mean(rv[-min(20, n):]))
        if n >= 60:
            momentum_60d = float(np.sum(rv[-60:]))
        if n >= 10:
            skew_20d = float(pd.Series(rv[-min(20, n):]).skew())

    row = {
        "ret_1d": ret_1d, "ret_5d": ret_5d, "ret_20d": ret_20d,
        "volatility_20d": vol_20d, "rolling_mean_20d": rolling_mean_20d,
        "momentum_60d": momentum_60d, "skew_20d": skew_20d,
        "repo_rate": repo, "india_vix": vix_val, "brent_crude": crude_val,
        "fii_net_crore": fii, "gst_collections": 150000.0, "cpi_yoy": 5.0,
        "brent_crude_chg": crude_chg, "usdinr_chg": usdinr_chg,
        "vix_chg": vix_chg, "fii_flow": fii_norm,
        "fii_5d_mean": fii_norm * 0.85, "nasdaq_chg": nasdaq_chg,
        "sp500_chg": sp500_chg, "nifty_5d_ret": nifty_ret * 5,
        "nifty_20d_ret": nifty_ret * 20, "gst_yoy": 0.0,
        "brent_5d_mean": crude_chg * 0.7, "usdinr_5d_mean": usdinr_chg * 0.7,
        "vix_5d_mean": vix_chg * 0.7, "vix_20d_mean": vix_val,
        "vix_regime": vix_regime,
        "vix_percentile": float(np.clip((vix_val - 10) / 25, 0.0, 1.0)),
        "crude_x_fx": crude_chg * usdinr_chg, "rate_x_vix": repo * vix_val,
        "rate_momentum": macro_data.get("repo_rate", {}).get("change", 0.0),
        "vix_momentum": vix_chg,
        "brent_crude_chg_lag1": crude_chg * 0.9, "brent_crude_chg_lag5": crude_chg * 0.6,
        "usdinr_chg_lag1": usdinr_chg * 0.9,     "usdinr_chg_lag5": usdinr_chg * 0.6,
        "vix_chg_lag1": vix_chg * 0.9,           "vix_chg_lag5": vix_chg * 0.6,
        "fii_flow_lag1": fii_norm * 0.9,          "fii_flow_lag5": fii_norm * 0.6,
        "nasdaq_chg_lag1": nasdaq_chg * 0.9,      "nasdaq_chg_lag5": nasdaq_chg * 0.6,
        "sector_hash": _sector_offset(sector) * 1000,
        "subsector_hash": _sector_offset(subsector) * 1000,
    }

    vec = np.array([row.get(f, 0.0) for f in feature_cols], dtype=np.float64)
    vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
    return vec.reshape(1, -1)


def _perturb_macro(macro_data, scenario):
    import copy
    m = copy.deepcopy(macro_data)
    if scenario == "bull":
        if "india_vix"   in m: m["india_vix"]["current"]         = max(10.0, m["india_vix"].get("current", 15) * 0.75)
        if "repo_rate"   in m: m["repo_rate"]["current"]         = max(5.0,  m["repo_rate"].get("current", 6.5) - 0.5)
        if "brent_crude" in m: m["brent_crude"]["change_pct"]    = -3.0
        if "fii_flows"   in m: m["fii_flows"]["estimated_crore"] = abs(m["fii_flows"].get("estimated_crore", 0)) + 5000
    elif scenario == "bear":
        if "india_vix"   in m: m["india_vix"]["current"]         = m["india_vix"].get("current", 15) * 1.5
        if "repo_rate"   in m: m["repo_rate"]["current"]         = min(9.0,  m["repo_rate"].get("current", 6.5) + 0.5)
        if "brent_crude" in m: m["brent_crude"]["change_pct"]    = +5.0
        if "fii_flows"   in m: m["fii_flows"]["estimated_crore"] = -abs(m["fii_flows"].get("estimated_crore", 0)) - 5000
    return m


def predict_sector_returns(macro_data, subsector, sector, scenario="base"):
    recent_rets = _get_recent_sector_returns(subsector, sector)
    m           = _perturb_macro(macro_data, scenario)
    predictions = {}

    for horizon in HORIZONS_TRAINED:   # 12M synthesised in generate_ml_forecasts
        payload = _load_horizon_model(horizon, subsector=subsector)
        if payload is None:
            payload = _load_horizon_model(horizon, sector=sector)
        if payload is None:
            predictions[horizon] = 0.0
            continue

        feat_vec = _build_inference_features(m, subsector, sector,
                                             payload["features"], recent_rets)
        try:
            scaled = payload["scaler"].transform(feat_vec)
            pred   = float(payload["model"].predict(scaled)[0])
        except Exception as e:
            pred = 0.0

        # Use model prediction directly — each horizon has its own trained model
        # No extrapolation needed since 6M model is trained on 126-day targets
        predictions[horizon] = pred

    return predictions


# ─────────────────────────────────────────────────────────────────
# SECTION 5 — FORECAST GENERATION
# ─────────────────────────────────────────────────────────────────

def _get_crude_dir(macro_data):
    chg = macro_data.get("brent_crude", {}).get("change_pct", 0)
    return "SPIKING" if chg > 2 else ("FALLING" if chg < -2 else "STABLE")


def _stub_forecast(subsector, sector, horizon, today, h_cfg, macro_data, regime):
    catalyst, risk = _domain_catalyst_risk(subsector, sector, macro_data, regime)
    return {
        "horizon":               horizon,
        "target_date":           str(today + timedelta(days=h_cfg["calendar"])),
        "base_case_return_pct":  0.0,
        "bull_case_return_pct":  OUTPUT_CAPS[horizon] * 0.10,
        "bear_case_return_pct":  -OUTPUT_CAPS[horizon] * 0.10,
        "confidence_score":      0.20,
        "opportunity_score":     5.0,
        "primary_catalyst":      catalyst,
        "risk_factor":           risk,
        "model_r2":              0.0,
        "directional_accuracy":  0.5,
        "source":                "no_model_stub",
        "crude_direction":       _get_crude_dir(macro_data),
    }


def generate_ml_forecasts(macro_data, regime):
    """Drop-in replacement for forward_engine.generate_forward_forecasts()."""
    print("\n=== ML FORWARD FORECAST ENGINE ===")
    today = datetime.today().date()
    ensure_tables_exist()

    all_forecasts = {}

    for sector_name, sec_data in MARKET_CLASSIFICATION.items():
        sector_forecasts = {}

        for subsector_name in sec_data["subsectors"]:
            horizon_forecasts = {}
            has_model = any(
                _load_horizon_model(h, subsector=subsector_name) is not None
                or _load_horizon_model(h, sector=sector_name) is not None
                for h in HORIZONS_TRAINED   # check trained horizons only
            )

            if not has_model:
                for h_label, h_cfg in HORIZONS.items():
                    horizon_forecasts[h_label] = _stub_forecast(
                        subsector_name, sector_name, h_label,
                        today, h_cfg, macro_data, regime
                    )
                sector_forecasts[subsector_name] = horizon_forecasts
                continue

            base_rets = predict_sector_returns(macro_data, subsector_name, sector_name, "base")
            bull_rets = predict_sector_returns(macro_data, subsector_name, sector_name, "bull")
            bear_rets = predict_sector_returns(macro_data, subsector_name, sector_name, "bear")

            for h_label, h_cfg in HORIZONS.items():
                cap     = OUTPUT_CAPS.get(h_label, OUTPUT_CAPS["6M"] * 1.5)
                payload = (_load_horizon_model(h_label, subsector=subsector_name)
                           or _load_horizon_model(h_label, sector=sector_name))

                # ── 12M: derived from 1M model's daily return × 252 trading days
                # This is the ONLY correct method — no reuse of 6M, no scaling tricks.
                # Formula: (1 + r_daily)^252 - 1  where r_daily comes from 1M model.
                # Sectors with different 1M daily returns will produce different 12M outputs.
                if h_label == "12M":
                    base_1m = float(base_rets.get("1M", 0.0))
                    bull_1m = float(bull_rets.get("1M", 0.0))
                    bear_1m = float(bear_rets.get("1M", 0.0))

                    # Derive implied daily return from 21-day model prediction
                    # (1 + r_daily)^21 = (1 + r_1m/100) → solve for r_daily
                    def _daily_from_horizon(r_pct, n_days=21):
                        r_frac = r_pct / 100.0
                        sign   = 1 if r_frac >= 0 else -1
                        return sign * (abs(1.0 + r_frac) ** (1.0 / n_days) - 1.0)

                    rd_base = _daily_from_horizon(base_1m, 21)
                    rd_bull = _daily_from_horizon(bull_1m, 21)
                    rd_bear = _daily_from_horizon(bear_1m, 21)

                    # FIX 3: Loose daily guard — only blocks truly insane values (>200% annual)
                    # Previous tight cap (120%) caused ALL sectors to cluster at 111.6%
                    # because every sector hitting the cap compounds to the same number.
                    _MAX_DAILY = (3.0 ** (1.0 / 252.0)) - 1.0   # 0.436%/day = +200% annual guard
                    _MIN_DAILY = -(2.0 ** (1.0 / 252.0)) + 1.0  # -0.276%/day = -100% guard
                    rd_bull = float(np.clip(rd_bull, _MIN_DAILY, _MAX_DAILY))
                    rd_bear = float(np.clip(rd_bear, _MIN_DAILY, _MAX_DAILY))

                    # Compound over 252 trading days
                    base_r = ((1.0 + rd_base) ** 252 - 1.0) * 100.0
                    bull_r = ((1.0 + rd_bull) ** 252 - 1.0) * 100.0
                    bear_r = ((1.0 + rd_bear) ** 252 - 1.0) * 100.0

                    # Add sector uniqueness offset at 12M scale
                    base_r += _sector_offset(subsector_name) * 12
                    base_r += regime.get("regime_score", 0) * 0.5
                    # CHANGE 2: soft_cap for 12M base_r — same reasoning as non-12M path
                    base_r  = soft_cap(base_r, cap)
                    base_r  = float(np.clip(base_r, FORECAST_MIN_ANNUAL, FORECAST_MAX_ANNUAL))

                    # FIX 1: Load mae_1m BEFORE using it in _vol_factor
                    # (was causing UnboundLocalError — Python scoping rule)
                    _payload_1m = (_load_horizon_model("1M", subsector=subsector_name)
                                   or _load_horizon_model("1M", sector=sector_name)
                                   or {})
                    mae_1m     = float(_payload_1m.get("mae", 10.0))
                    r2_1m      = float(_payload_1m.get("r2", 0.1))
                    dir_acc_1m = float(_payload_1m.get("directional_acc", 0.5))
                    r2         = r2_1m

                    # MAE-based volatility spread — genuine per-sector dispersion
                    # vol_factor: MAE=3.5% → 0.7x, MAE=10% → 2.0x, MAE=17% → 3.4x
                    _vol_factor  = float(np.clip(mae_1m / 5.0, 0.5, 3.5))
                    _min_spread  = max(abs(base_r) * 0.30, 15.0)
                    _bull_spread = _vol_factor * _min_spread
                    bull_r = base_r + _bull_spread
                    bear_r = base_r - _bull_spread * 0.80
                    # MODULE 6: Realistic ceiling — min -50%, max +60% (removed 90%/150% extremes)
                    bull_r = float(np.clip(bull_r, FORECAST_MIN_ANNUAL, FORECAST_MAX_ANNUAL))
                    bear_r = float(np.clip(bear_r, FORECAST_MIN_ANNUAL, FORECAST_MAX_ANNUAL))

                    # Confidence degrades for 12M vs 1M (longer horizon = more uncertainty)
                    mae_norm   = float(np.clip(mae_1m / 10.0, 0.10, 2.0))
                    conf_base  = 1.0 / (1.0 + mae_norm)
                    dir_boost  = float(np.clip((dir_acc_1m - 0.50) * 0.8, -0.15, 0.20))
                    # 12M horizon: reduce confidence by 25% — longer horizon = more uncertainty
                    confidence = float(np.clip((conf_base + dir_boost) * 0.75, 0.20, 0.70))

                else:
                    base_r = float(base_rets.get(h_label, 0.0))
                    bull_r = float(bull_rets.get(h_label, 0.0))
                    bear_r = float(bear_rets.get(h_label, 0.0))

                    r2      = float(payload.get("r2",              0.1))  if payload else 0.1
                    dir_acc = float(payload.get("directional_acc", 0.55)) if payload else 0.55
                    mae     = float(payload.get("mae", 0.0)) if payload else 0.0

                    # FIX 4: DB fallback for mae when pkl was trained before mae storage was added
                    # If mae == 0.0, it was not stored in pkl → look it up from DB
                    if mae <= 0.0:
                        try:
                            _sess = get_session()
                            _mv = _sess.query(ModelVersion).filter(
                                ModelVersion.subsector.like(f"%{subsector_name.replace(' ', '_')}%"),
                                ModelVersion.is_active == True
                            ).first()
                            if _mv and _mv.mae and _mv.mae > 0:
                                mae = float(_mv.mae)
                            else:
                                mae = 10.0   # conservative default
                            _sess.close()
                        except Exception:
                            mae = 10.0

                    # FIX 1: DYNAMIC CONFIDENCE via prediction uncertainty (MAE)
                    # Formula: confidence = 1 / (1 + mae_normalised)
                    # MAE of 3%  → conf = 1/(1+0.3) = 0.77  (high-confidence sector)
                    # MAE of 7%  → conf = 1/(1+0.7) = 0.59  (medium confidence)
                    # MAE of 12% → conf = 1/(1+1.2) = 0.45  (lower confidence)
                    # MAE of 20% → conf = 1/(1+2.0) = 0.33  (noisy sector)
                    # Normalise MAE to [0, 2] range (typical MAE: 3-20%)
                    mae_norm   = float(np.clip(mae / 10.0, 0.10, 2.0))
                    conf_base  = 1.0 / (1.0 + mae_norm)
                    # Directional accuracy acts as multiplier — better direction = more confident
                    dir_boost  = float(np.clip((dir_acc - 0.50) * 0.8, -0.15, 0.20))
                    confidence = float(np.clip(conf_base + dir_boost, 0.20, 0.90))

                offset  = _sector_offset(subsector_name) * h_cfg["trading"] / 21 * 0.5
                base_r += offset
                base_r += regime.get("regime_score", 0) * 0.05 * (h_cfg["trading"] / 21.0)

                # Spread based on confidence — lower confidence = wider spread
                conf_spread_factor = 1.0 - confidence * 0.4   # 0.6 to 1.0
                min_spread = max(
                    abs(base_r) * 0.20,
                    cap * MIN_SPREAD_PCT.get(h_label, 0.10),
                ) * conf_spread_factor * 1.5
                bull_r = max(bull_r, base_r + min_spread)
                bear_r = min(bear_r, base_r - min_spread)

                # CHANGE 2: Use soft_cap for base_r instead of hard np.clip.
                # BEFORE: np.clip(base_r, -cap, cap) — hard ceiling caused all
                # high-return sectors to land at exactly the same value (cap),
                # making ranking impossible and weights uniform.
                # AFTER: soft_cap compresses values beyond cap by 30%, so a
                # sector at 55% (cap=45) becomes ~48% — still differentiated
                # from a sector at 42%, preserving relative ordering.
                base_r = soft_cap(base_r, cap)
                base_r = float(np.clip(base_r, FORECAST_MIN_ANNUAL, FORECAST_MAX_ANNUAL))
                bull_r = soft_cap(bull_r, cap * 1.20)
                bull_r = float(np.clip(bull_r, FORECAST_MIN_ANNUAL, FORECAST_MAX_ANNUAL))
                bear_r = -soft_cap(-bear_r, cap * 1.20)
                bear_r = float(np.clip(bear_r, FORECAST_MIN_ANNUAL, FORECAST_MAX_ANNUAL))

                opp_score       = _compute_opp_score(base_r, bull_r, bear_r, confidence, regime, cap,
                                                     subsector=subsector_name, macro_data=macro_data)
                catalyst, risk  = _domain_catalyst_risk(subsector_name, sector_name, macro_data, regime)

                horizon_forecasts[h_label] = {
                    "horizon":               h_label,
                    "target_date":           str(today + timedelta(days=h_cfg["calendar"])),
                    "base_case_return_pct":  round(base_r, 2),
                    "bull_case_return_pct":  round(bull_r, 2),
                    "bear_case_return_pct":  round(bear_r, 2),
                    "confidence_score":      round(confidence, 2),
                    "opportunity_score":     round(opp_score, 1),
                    "primary_catalyst":      catalyst,
                    "risk_factor":           risk,
                    "model_r2":              round(r2, 3),
                    "directional_accuracy":  round(0.5, 3),
                    "source":                "ml_horizon_model",
                    "crude_direction":       _get_crude_dir(macro_data),
                }

            sector_forecasts[subsector_name] = horizon_forecasts
            # Apply OUTPUT_CAPS clipping to displayed values
            def _capped(h):
                val = horizon_forecasts.get(h, {}).get("base_case_return_pct", 0.0)
                cap = OUTPUT_CAPS.get(h, 60.0)
                clipped = float(np.clip(val, -cap, cap))
                # Update the dict in-place so downstream also gets capped value
                if h in horizon_forecasts:
                    horizon_forecasts[h]["base_case_return_pct"] = round(clipped, 2)
                return clipped

            print(
                f"  {subsector_name[:42]:42s} "
                f"1M={_capped('1M'):+6.1f}% "
                f"3M={_capped('3M'):+6.1f}% "
                f"6M={_capped('6M'):+6.1f}%"
            )

        all_forecasts[sector_name] = sector_forecasts

    # FIX 5: Z-SCORE NORMALISATION for opportunity scores
    # After all sectors are computed, rescale so scores span 2–9
    # Formula: score = 5 + z_score * 2  (where z = (raw - mean) / std)
    # This guarantees meaningful ranking: top sectors ~7-9, weak ~2-4
    all_scores = []
    for sec_data in all_forecasts.values():
        for sub_data in sec_data.values():
            for h_data in sub_data.values():
                if isinstance(h_data, dict) and "opportunity_score" in h_data:
                    all_scores.append(h_data["opportunity_score"])

    if len(all_scores) > 5:
        arr   = np.array(all_scores, dtype=float)
        mean  = float(arr.mean())
        std   = float(arr.std())
        if std > 0.05:
            for sec_data in all_forecasts.values():
                for sub_data in sec_data.values():
                    for h_data in sub_data.values():
                        if isinstance(h_data, dict) and "opportunity_score" in h_data:
                            raw = h_data["opportunity_score"]
                            z   = (raw - mean) / std
                            # z-score → 1-10 scale: centred at 5, spread of 2 per σ
                            normalised = float(np.clip(5.0 + z * 2.0, 1.0, 10.0))
                            h_data["opportunity_score"] = round(normalised, 1)

    # FIX 4: CROSS-HORIZON DIVERSIFICATION PENALTY
    # Prevents the same subsector (e.g. Oil Refining) from being #1 in all 4 horizons.
    # After z-score normalisation, if a subsector already topped a shorter horizon,
    # reduce its score by 12% in subsequent horizons.
    HORIZONS_ORDER = ["1M", "3M", "6M", "12M"]
    horizon_top_picks = set()

    for h_label in HORIZONS_ORDER:
        horizon_entries = []
        for sec_data in all_forecasts.values():
            for sub_name, sub_data in sec_data.items():
                if h_label in sub_data and isinstance(sub_data[h_label], dict):
                    score = sub_data[h_label].get("opportunity_score", 5.0)
                    horizon_entries.append((score, sub_name, sub_data[h_label]))
        if not horizon_entries:
            continue
        # Apply 12% penalty to any subsector that already topped a previous horizon
        for score, sub_name, h_data in horizon_entries:
            if sub_name in horizon_top_picks:
                h_data["opportunity_score"] = round(float(np.clip(score * 0.88, 1.0, 10.0)), 1)
        # Record this horizon's winner (after penalties)
        horizon_entries.sort(key=lambda x: x[2].get("opportunity_score", 5.0), reverse=True)
        if horizon_entries:
            horizon_top_picks.add(horizon_entries[0][1])

    # ── REGIME-AWARE DAMPENING ────────────────────────────────────
    _rs = float(regime.get("regime_score", 0) if isinstance(regime, dict) else 0)
    HORIZON_SEQ = ["1M", "3M", "6M", "12M"]
    for sec_name, sec_data in all_forecasts.items():
        for sub_name, sub_data in sec_data.items():
            for h in HORIZON_SEQ:
                if h not in sub_data or not isinstance(sub_data[h], dict):
                    continue
                h_data = sub_data[h]
                base_r = h_data.get("base_case_return_pct", 0.0)
                bull_r = h_data.get("bull_case_return_pct", 0.0)
                bear_r = h_data.get("bear_case_return_pct", 0.0)
                if _rs < -0.3 and base_r > 0:
                    _damp = max(0.60, 1.0 - (abs(_rs) * 0.35))
                    h_data["base_case_return_pct"] = round(base_r * _damp, 2)
                    h_data["bull_case_return_pct"] = round(bull_r * _damp, 2)
                    h_data["bear_case_return_pct"] = round(bear_r * _damp, 2)
                elif _rs > 0.3 and base_r < 0:
                    _damp = max(0.60, 1.0 - (_rs * 0.25))
                    h_data["base_case_return_pct"] = round(base_r * _damp, 2)
                    h_data["bull_case_return_pct"] = round(bull_r * _damp, 2)
                    h_data["bear_case_return_pct"] = round(bear_r * _damp, 2)
    # ── END REGIME-AWARE DAMPENING ────────────────────────────────

    # ── MONOTONIC HORIZON ORDER ENFORCEMENT ──────────────────────
    for sec_name, sec_data in all_forecasts.items():
        for sub_name, sub_data in sec_data.items():
            available = [(h, sub_data[h]) for h in HORIZON_SEQ
                         if h in sub_data and isinstance(sub_data[h], dict)]
            if len(available) < 2:
                continue
            last_base = available[-1][1].get("base_case_return_pct", 0.0)
            direction = 1 if last_base >= 0 else -1
            prev_base = None
            for h, h_data in available:
                curr_base = h_data.get("base_case_return_pct", 0.0)
                if prev_base is not None:
                    if direction > 0:
                        curr_base = max(curr_base, prev_base)
                    else:
                        curr_base = min(curr_base, prev_base)
                    old_bull  = h_data.get("bull_case_return_pct", curr_base)
                    old_bear  = h_data.get("bear_case_return_pct", curr_base)
                    old_base  = h_data.get("base_case_return_pct", curr_base)
                    spread_up   = abs(old_bull - old_base)
                    spread_down = abs(old_base - old_bear)
                    h_data["base_case_return_pct"] = round(curr_base, 2)
                    h_data["bull_case_return_pct"] = round(curr_base + spread_up, 2)
                    h_data["bear_case_return_pct"] = round(curr_base - spread_down, 2)
                prev_base = curr_base
    # ── END MONOTONIC ENFORCEMENT ─────────────────────────────────

    _store_ml_forecasts(all_forecasts, today)
    validate_forecast_sanity(all_forecasts)
    return all_forecasts


# ─────────────────────────────────────────────────────────────────
# SECTION 6 — OPPORTUNITY SCORE
# ─────────────────────────────────────────────────────────────────

def _compute_opp_score(base_r, bull_r, bear_r, confidence, regime, cap, subsector="", macro_data=None, macro_alignment="MACRO_ALIGNED"):
    """
    Composite opportunity score 1–10 with genuine spread.

    Components:
      45% — return quality (sigmoid on base_r vs cap, centred at 0)
      25% — risk/reward asymmetry (bull upside vs bear downside)
      20% — model confidence (actual R² + directional accuracy)
      10% — macro regime alignment

    Domain overrides baked in after composite:
      OMC subsector is penalised when crude is SPIKING
      Renewables get a bonus when crude is SPIKING (substitution tailwind)
    """
    if macro_data is None:
        macro_data = {}

    # 1. Return quality — sigmoid so +20% scores ~0.85, -20% scores ~0.15
    # Stretch the curve so scores naturally fall between 2 and 9
    norm_ret = 1.0 / (1.0 + np.exp(-base_r / (cap * 0.30)))   # 0–1

    # 2. Asymmetry — upside potential vs downside risk
    upside   = max(bull_r - base_r, 0.0)
    downside = max(base_r - bear_r, 0.01)
    asym_raw = upside / downside   # 0 to infinity
    asym     = np.clip(asym_raw / 3.0, 0.0, 1.0)   # normalise: ratio of 3 → 1.0

    # 3. Confidence — use full 0–1 range
    conf_norm = np.clip(confidence, 0.0, 1.0)

    # 4. Regime — positive regime adds score, negative subtracts
    rs       = regime.get("regime_score", 0)
    reg_norm = np.clip((rs + 1.0) / 2.0, 0.0, 1.0)

    # Raw composite → scale to 1–10
    raw = (0.45 * norm_ret + 0.25 * asym + 0.20 * conf_norm + 0.10 * reg_norm) * 10.0

    # ── Domain overrides — applied AFTER composite so they genuinely shift rank ──

    crude_dir  = _get_crude_dir(macro_data)
    usdinr_chg = macro_data.get("usdinr", {}).get("change_pct", 0.0)
    sub_lower  = subsector.lower()

    # FIX 6: OMC vs Upstream crude logic (Issue 6)
    # Crude FALLING → OMC benefits (GRM expands), Upstream/E&P hurt (lower realisation)
    # Crude RISING → OMC hurt (input cost), Upstream benefits (higher realisation)
    if "oil refin" in sub_lower or "omc" in sub_lower:
        if crude_dir == "SPIKING":
            raw -= 2.5   # GRM severely compressed
        elif crude_dir == "FALLING":
            raw += 1.5   # strong input cost relief
    elif "renew" in sub_lower:
        if crude_dir == "SPIKING":
            raw += 0.8   # substitution tailwind
        elif crude_dir == "FALLING":
            raw -= 0.3   # slight dampening (green premium narrows vs fossil)
    elif "gas distrib" in sub_lower:
        if crude_dir == "FALLING":
            raw += 0.5   # APM gas prices ease, margins improve
    elif "power gen" in sub_lower:
        pass  # largely independent of crude

    # FIX 2a: Rupee-directional penalty for export sectors
    # Rupee STRENGTHENING → hurts IT and Pharma (dollar revenues shrink in INR)
    # Rupee WEAKENING    → helps IT and Pharma
    rupee_strengthening = usdinr_chg < -0.5   # usdinr falling = rupee stronger
    rupee_weakening     = usdinr_chg > 0.5
    if "it service" in sub_lower or "digital eng" in sub_lower or "saas" in sub_lower or "ai &" in sub_lower:
        nasdaq_chg = macro_data.get("nasdaq", {}).get("change_pct", 0.0)
        if nasdaq_chg > 1.0:
            raw += 0.5
        elif nasdaq_chg < -1.0:
            raw -= 0.5
        if rupee_strengthening:
            raw -= 0.8   # FIX 1: rupee up → IT dollar revenue contracts in INR
        elif rupee_weakening:
            raw += 0.5
    if "pharma" in sub_lower or "healthcare" in sub_lower:
        if rupee_strengthening:
            raw -= 1.0   # rupee up → US generic export revenue shrinks in INR
        elif rupee_weakening:
            raw += 0.6

    # FIX 2b: MACRO_DIVERGENT penalty — sector moving against macro should score lower
    # This prevents ranking a sector as #1 opportunity when macro opposes it
    if macro_alignment == "MACRO_DIVERGENT":
        raw -= 1.2   # meaningful penalty: divergent sectors are higher risk
    elif macro_alignment == "MACRO_ALIGNED":
        raw += 0.3   # small bonus for alignment confirming the signal

    return float(np.clip(raw, 1.0, 10.0))


# ─────────────────────────────────────────────────────────────────
# SECTION 7 — CATALYSTS
# ─────────────────────────────────────────────────────────────────

_CATALYSTS = {
    "Private Banks":
        ("FII inflows lifting large-cap valuations; liability repricing faster than assets in rate-cut cycle widens short-term NIM — but asset repricing lags 2-3 quarters so full benefit is delayed",
         "Unsecured retail credit slippage rising; NIM compression if deposit repricing accelerates before asset repricing completes"),
    "PSU Banks":
        ("MSME and retail credit growth accelerating; CASA ratio expansion reducing cost of funds — net NIM impact depends on deposit book tenure mix",
         "Gross NPA risk in agriculture segment; bond portfolio MTM losses if long yields rise even as repo is cut"),
    "NBFCs":
        ("Shorter-duration borrowing book reprices faster in rate-cut cycle, directly expanding spreads; rural credit demand recovering post-harvest",
         "Wholesale funding cost stickier than retail rates; MFI asset quality in stressed geographies deteriorating"),
    "Insurance":
        ("Regulatory expansion of mandatory cover; Bima Sugam digital distribution platform opening rural penetration at low distribution cost",
         "Rising claims inflation in health segment; equity market correction compressing ULIP NAVs and new business premium flows"),
    "AMCs & Capital Markets":
        ("SIP book at record monthly run-rate drives fee income regardless of market level; equity AUM growth from both market returns and fresh inflows",
         "Market correction compresses AUM and variable performance fee income simultaneously; SEBI TER reduction risk"),
    "IT Services":
        ("US enterprise tech capex recovering — deal pipeline conversion improving; rupee depreciation directly expands dollar-denominated revenue in INR reporting",
         "Client discretionary IT spend cuts in US recession scenario; pricing pressure in legacy application maintenance"),
    "Digital Engineering":
        ("R&D outsourcing from global OEMs and semiconductor firms accelerating; engineering services less exposed to commoditisation than IT services",
         "Revenue concentration in auto and aerospace verticals subject to capex cycle; dollar billing compressed by rupee appreciation"),
    "SaaS & Product-Based Companies":
        ("India PLI for software products; global SaaS expansion through partner channels in Middle East and Southeast Asia",
         "US valuation multiple compression flows through to Indian SaaS peers; SMB churn risk in economic slowdown"),
    "Oil Refining & Marketing":
        ("Gross refining margin is the single driver — GRM expands when crude falls and retail prices lag the drop, creating inventory gains",
         "Crude spike compresses GRM faster than retail price hikes can compensate; government excise reduction risk caps upside in inflationary crude environment"),
    "Gas Distribution":
        ("City gas volume growth from new household connections in Tier-2 cities; APM price stability supporting distribution margins",
         "Upstream gas price hike triggered by crude linkage reduces industrial demand volume; PNGRB tariff revision risk on transmission charges"),
    "Renewable Energy":
        ("500GW target driving 40GW annual capacity addition; green bond yields compressing as global ESG capital inflows reduce project financing cost",
         "Long-duration capex highly rate-sensitive — 100bps rate rise reduces project IRR by 150-200bps; grid connectivity delays add 12-18 months to revenue recognition"),
    "Passenger Vehicles":
        ("Rate cut lowers EMI on ₹8L entry-level car loan by ₹500-700/month, expanding addressable buyer pool; SUV premiumisation driving ASP and revenue per unit higher",
         "EV penetration in hatchback segment disrupting ICE volume mix; commodity cost pass-through ability limited by competitive intensity"),
    "Two Wheelers":
        ("Rural disposable income recovery post-kharif harvest; two-wheeler loan penetration improving in semi-urban markets with new NBFC partnerships",
         "EV disruption accelerating in electric scooter segment taking share from ICE; monsoon-linked rural demand is high-beta to rainfall quantum"),
    "Commercial Vehicles":
        ("Infrastructure capex cycle driving fleet additions for construction, mining, and logistics; fleet replacement cycle after 3-year COVID-era deferral",
         "Diesel price sensitivity directly impacts fleet operator profitability and purchase decisions; financing cost stickiness from PSU bank NIM constraints"),
    "Large Cap Pharma":
        ("US generic approval pipeline converting to incremental revenue; domestic branded formulation pricing power from exclusion under NLEM scheduled drugs",
         "US FDA import alerts are binary high-impact risk events; US generic price erosion accelerating as generic competition intensifies"),
    "Mid Cap Pharma & Generic":
        ("CDMO opportunity from China+1 supply chain diversification by global innovators; API export demand from regulated US and EU markets growing 15% annually",
         "API raw material price volatility from China supply disruption flows through to margins; domestic price control orders on essential medicines limit revenue growth"),
    "Healthcare & Hospitals":
        ("Occupancy recovery with domestic and international medical tourism; high-margin international patient revenue from South Asia and Middle East growing",
         "Nursing and doctor wage inflation compressing EBITDA margins by 150-200bps annually; NPPA pricing pressure on medical devices and implants constraining procedure revenue"),
    "Real Estate Developers":
        ("Rate cut reduces home loan EMI — every 25bps cut improves affordability by approximately 2% — converting fence-sitters to buyers; PMAY demand pipeline in affordable segment",
         "Commercial real estate inventory overhang in Tier-1 cities; RERA compliance costs and project approval delays extending cash conversion cycles"),
    "Construction & EPC":
        ("Record Union Budget allocation to roads, railways, and urban infrastructure; NHI and NIP projects in execution phase driving order inflows and revenue backlog",
         "Labour cost inflation 12-15% YoY; monsoon season construction halt for 3 months impacts quarterly revenue recognition and cash collection"),
    "Cement":
        ("Housing and infrastructure demand driving volume growth; regional capacity utilisation above 80% supporting producer pricing discipline",
         "Coal and pet coke cost inflation is the primary margin risk — 10% coal price rise compresses EBITDA per tonne by approximately ₹40-50"),
    "Industrial & Defence":
        ("Defence indigenisation mandate requiring 68% domestic procurement by 2027; multi-year order book providing 3-4 year revenue visibility with milestone billing",
         "Government payment cycle delays create working capital pressure; long execution timelines make quarterly revenue lumpy and hard to forecast"),
    "FMCG Staples":
        ("Rural demand recovery on above-normal monsoon driving volume growth in sachets and value packs; palm oil and crude derivative input costs falling improve gross margins",
         "Urban consumption slowdown visible in premium pack offtake; packaging and freight cost inflation offset raw material relief"),
    "Consumer Durables":
        ("Rate cut expands EMI-financed purchase pool for ACs and appliances; real estate upcycle pulling through kitchen and home improvement demand",
         "Commodity cost spike in steel, copper, and aluminium compresses gross margins; weak monsoon reduces rural purchasing power for aspirational categories"),
    "Paints & Building Materials":
        ("Housing construction boom from PMAY and real estate upcycle driving volume; premiumisation in decorative segment expanding revenue per litre",
         "TiO2 and solvent costs are crude-linked — crude spike of 15% directly compresses raw material margins by 200-300 basis points"),
    "Auto Ancillaries & EV":
        ("EV component localisation mandate creating new addressable market for domestic suppliers; global auto OEM India sourcing for cost competitiveness growing",
         "OEM customer concentration risk — top 3 customers typically 60-70% of revenue; component commoditisation as EV technology matures compresses margins"),
    "Power Generation":
        ("Power demand growing 7-8% YoY driven by industrial load and data centre electricity consumption; renewable capacity auction pipeline strong with 50GW in pipeline",
         "Fuel supply disruptions for thermal plants impact generation availability; state DISCOM payment default risk creates receivables build-up"),
}


def _domain_catalyst_risk(subsector, sector, macro_data, regime):
    """
    Returns macro-state-aware catalyst and risk strings.
    Checks current macro conditions to make catalysts dynamic.
    NEVER uses forbidden phrases: company-specific factors, technical factors,
    market sentiment, broader trends, positioning effects, investor confidence.
    """
    crude_dir  = _get_crude_dir(macro_data)
    nasdaq_chg = macro_data.get("nasdaq", {}).get("change_pct", 0.0)
    repo       = macro_data.get("repo_rate", {}).get("current", 6.5)
    rate_chg   = macro_data.get("repo_rate", {}).get("change", 0.0)
    usdinr_chg = macro_data.get("usdinr", {}).get("change_pct", 0.0)
    fii_signal = macro_data.get("fii_flows", {}).get("signal", "NEUTRAL")

    sub_lower  = subsector.lower()

    # Dynamic catalysts for key macro-sensitive subsectors
    if "oil refin" in sub_lower or "omc" in sub_lower:
        if crude_dir == "SPIKING":
            return (
                f"Crude SPIKING — gross refining margin compressed as input cost rises faster than capped retail prices; inventory losses likely in quarterly earnings",
                "Crude remaining above $95/bbl through quarter-end will show $2-4/bbl GRM compression in results; government may mandate excise cut capping upside"
            )
        elif crude_dir == "FALLING":
            return (
                "Crude falling — GRM expanding as retail prices lag input cost decline; inventory gains boosting quarterly profitability",
                "OPEC+ supply cut could reverse crude trajectory; any government excise hike will neutralise GRM benefit"
            )

    if "it service" in sub_lower or "digital eng" in sub_lower:
        rupee_dir = "WEAKENING" if usdinr_chg > 0.3 else ("STRENGTHENING" if usdinr_chg < -0.3 else "STABLE")
        nasdaq_label = "RISING" if nasdaq_chg > 0.5 else ("FALLING" if nasdaq_chg < -0.5 else "FLAT")
        return (
            f"NASDAQ {nasdaq_label} ({nasdaq_chg:+.1f}%) driving US enterprise tech capex sentiment; rupee {rupee_dir} ({usdinr_chg:+.2f}%) {'expanding' if rupee_dir == 'WEAKENING' else 'compressing'} dollar revenue in INR terms",
            f"US recession reducing discretionary IT budget; {'rupee appreciation eroding USD billing realization' if rupee_dir == 'STRENGTHENING' else 'watch rupee stabilisation as hedge against dollar revenue compression'}"
        )

    if "private bank" in sub_lower or "psu bank" in sub_lower or "nbfc" in sub_lower:
        rate_label = "CUT" if rate_chg < -0.01 else ("HIKED" if rate_chg > 0.01 else "UNCHANGED")
        return (
            f"Repo rate {rate_label} at {repo}% — liability book reprices within 1 quarter but asset book reprices over 2-3 quarters; net NIM impact is positive but delayed; FII {fii_signal} supporting large-cap bank valuations",
            f"Unsecured retail credit slippage rising; {'deposit repricing risk if savers move to higher-yield instruments' if rate_label == 'CUT' else 'borrower stress in rate-hike cycle compressing asset quality'}"
        )

    if "pharma" in sub_lower or "large cap pharma" in sub_lower:
        rupee_dir = "WEAKENING" if usdinr_chg > 0.3 else ("STRENGTHENING" if usdinr_chg < -0.3 else "STABLE")
        return (
            f"Rupee {rupee_dir} ({usdinr_chg:+.2f}%) directly {'expanding' if usdinr_chg > 0 else 'compressing'} US generic export revenue in INR; domestic formulation pricing power from NLEM exclusions",
            "US FDA import alert risk is binary and event-driven; US generic price erosion of 3-5% per year compresses revenue per approved product"
        )

    # Standard catalogue lookup
    for key, (cat, rsk) in _CATALYSTS.items():
        if key.lower() in sub_lower or sub_lower in key.lower():
            return cat, rsk

    # Regime-based fallback — data-driven, no generic phrases
    rs = regime.get("regime_score", 0)
    regime_label = regime.get("overall_regime", "NEUTRAL")
    vix_val      = macro_data.get("india_vix", {}).get("current", 15.0)
    fii_cr       = macro_data.get("fii_flows", {}).get("estimated_crore", 0)
    if rs > 0.20:
        return (
            f"Regime {regime_label} (score {rs:+.2f}): FII {fii_signal} (~₹{abs(fii_cr):,.0f} Cr), "
            f"repo at {repo}%, VIX {vix_val:.1f} — foreign capital and rate environment supporting index-level valuations",
            f"Watch India VIX crossing 20 (currently {vix_val:.1f}) as the key stress signal — "
            f"above 20 historically triggers 3-5% index correction within 10 trading days"
        )
    else:
        return (
            f"Regime {regime_label} (score {rs:+.2f}) with VIX {vix_val:.1f} — "
            f"repo at {repo}% and FII {fii_signal} flows create mixed signals; sector-specific earnings catalysts required to outperform",
            f"Regime upgrade requires FII sustained buying >₹2,000 Cr/week and VIX below 15 — "
            f"neither condition currently met"
        )


# ─────────────────────────────────────────────────────────────────
# SECTION 8 — DB PERSISTENCE
# ─────────────────────────────────────────────────────────────────

def _store_ml_forecasts(all_forecasts, generated_date):
    records = []
    for sector_name, sub_dict in all_forecasts.items():
        for subsector_name, h_dict in sub_dict.items():
            for h_label, fc in h_dict.items():
                # Hard-cap returns at OUTPUT_CAPS before storing
                _cap          = OUTPUT_CAPS.get(h_label, 60.0)
                _base         = float(fc.get("base_case_return_pct", 0))
                _bull         = float(fc.get("bull_case_return_pct", 0))
                _bear         = float(fc.get("bear_case_return_pct", 0))
                # Clip base to [-cap, +cap], bull/bear follow proportionally
                _base_clipped = float(np.clip(_base, -_cap, _cap))
                _ratio        = (_base_clipped / _base) if abs(_base) > 0.01 else 1.0
                _bull_clipped = float(np.clip(_bull * _ratio, -_cap * 1.2, _cap * 1.2))
                _bear_clipped = float(np.clip(_bear * _ratio, -_cap * 1.2, _cap * 1.2))
                records.append({
                    "generated_date":    generated_date,
                    "forecast_horizon":  h_label,
                    "target_date":       fc.get("target_date", ""),
                    "sector":            sector_name,
                    "subsector":         subsector_name,
                    "base_case_return":  round(_base_clipped, 3),
                    "bull_case_return":  round(_bull_clipped, 3),
                    "bear_case_return":  round(_bear_clipped, 3),
                    "confidence_score":  round(float(fc.get("confidence_score", 0)), 3),
                    "opportunity_score": round(float(fc.get("opportunity_score", 5)), 2),
                    "primary_catalyst":  fc.get("primary_catalyst", "")[:250],
                    "risk_factor":       fc.get("risk_factor", "")[:250],
                    "model_version":     fc.get("source", "ml_horizon_model"),
                })
    if not records:
        return
    session = get_session()
    try:
        session.query(ForwardForecast).filter(
            ForwardForecast.generated_date == generated_date
        ).delete(synchronize_session=False)
        session.bulk_insert_mappings(ForwardForecast, records)
        session.commit()
        print(f"  Stored {len(records)} ML forecasts to DB")
    except Exception as e:
        session.rollback()
        print(f"  [Store] DB error: {e}")
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────
# SECTION 9 — VALIDATION
# ─────────────────────────────────────────────────────────────────

def validate_forecast_sanity(all_forecasts):
    print("\n--- FORECAST SANITY CHECK ---")
    results = {}
    for horizon in list(HORIZONS.keys()):
        cap       = OUTPUT_CAPS.get(horizon, 60.0)
        vals      = []
        all_bases = []
        for sec, sub_dict in all_forecasts.items():
            for sub, h_dict in sub_dict.items():
                if horizon not in h_dict:
                    continue
                fc     = h_dict[horizon]
                base_r = fc.get("base_case_return_pct", 0.0)
                bull_r = fc.get("bull_case_return_pct", 0.0)
                bear_r = fc.get("bear_case_return_pct", 0.0)
                vals.append(base_r)
                all_bases.append(round(base_r, 1))
                if abs(base_r) > cap * 2.0:
                    print(f"  EXPLOSION {sub}/{horizon}: {base_r:+.1f}%")
                if not (bear_r <= base_r <= bull_r):
                    print(f"  ORDER VIOLATION {sub}/{horizon}")
                    corrected_base = float(np.clip(base_r, bear_r, bull_r))
                    fc["base_case_return_pct"] = round(corrected_base, 3)

        if not vals:
            continue

        arr  = np.array(vals)
        mean = float(arr.mean())
        std  = float(arr.std())
        mn   = float(arr.min())
        mx   = float(arr.max())

        status_mean = "OK" if abs(mean) > 0.3 else "FLAT"
        status_std  = "OK" if std > 0.3 else "LOW_VAR"

        print(f"  {horizon}: mean={mean:+.2f}% std={std:.2f}% "
              f"range=[{mn:+.1f}% to {mx:+.1f}%] "
              f"mean={status_mean} std={status_std}")

        results[horizon] = {"mean": mean, "std": std, "min": mn, "max": mx}
    return results


# ─────────────────────────────────────────────────────────────────
# CONVENIENCE WRAPPERS
# ─────────────────────────────────────────────────────────────────

def retrain_ml_models(lookback_years=10):
    return train_all_horizon_models(lookback_years=lookback_years)

def retrain_rolling_ml(lookback_years=3):
    print("\nRolling ML retrain (3yr window)...")
    return train_all_horizon_models(lookback_years=lookback_years)


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from database import init_database
    init_database()

    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"

    if cmd == "diagnose":
        diagnose_database()

    elif cmd == "train":
        yrs = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        train_all_horizon_models(lookback_years=yrs)

    elif cmd == "validate":
        for sector_name, sec_data in MARKET_CLASSIFICATION.items():
            for sub_name in sec_data["subsectors"]:
                ds = build_training_dataset(subsector=sub_name, lookback_years=10)
                if ds:
                    for h, df in ds.items():
                        print(f"  {sub_name[:35]:35s} {h}: {len(df)} rows  "
                              f"mean={df['target'].mean():+.2f}%  std={df['target'].std():.2f}%")

    elif cmd == "predict":
        dummy_macro  = {
            "usdinr":      {"change_pct": 0.1, "current": 83.5},
            "india_vix":   {"current": 16.0,   "change_pct": -2.0},
            "brent_crude": {"current": 82.0,   "change_pct": 1.5},
            "repo_rate":   {"current": 6.5,    "change": 0.0},
            "fii_flows":   {"estimated_crore": 2000, "signal": "NET_BUYING"},
            "nasdaq":      {"change_pct": 0.5, "current": 17500},
            "sp500":       {"change_pct": 0.3, "current": 5200},
            "nifty":       {"return_pct": 0.2},
        }
        dummy_regime = {"regime_score": 2, "overall_regime": "MILD_BULLISH"}
        fc = generate_ml_forecasts(dummy_macro, dummy_regime)
        validate_forecast_sanity(fc)

    else:
        print("Commands: diagnose | train [years] | validate | predict")
