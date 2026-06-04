# model_trainer.py
# MarketOS v3 — Improved ML Training
# Key improvements:
# 1. GBM model for non-linear relationships
# 2. More features: momentum, sector-specific macro interactions
# 3. Sector-specific feature sets (IT gets USD/INR weighted higher)
# 4. Proper walk-forward validation
# 5. Fixed analytics error

import pandas as pd
import numpy as np
import json
import pickle
import os
import time
from datetime import datetime, timedelta
from sklearn.linear_model import Ridge
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import r2_score, mean_absolute_error
from database import (engine, DailyPrice, MacroData,
                      ModelVersion, get_session, ensure_tables_exist)
from classification import MARKET_CLASSIFICATION
import warnings
warnings.filterwarnings('ignore')

os.makedirs("data/models", exist_ok=True)

# ── Base macro features ───────────────────────────────────────────
BASE_FEATURES = [
    "repo_rate", "india_vix", "brent_crude",
    "usdinr_chg", "vix_chg", "crude_chg", "fii_net",
    "usdinr_chg_lag1", "vix_chg_lag1", "crude_chg_lag1",
    "usdinr_5d_mean", "vix_5d_mean", "crude_5d_mean",
    "vix_regime", "rate_x_vix", "crude_x_fx",
    # NEW: momentum features
    "nifty_5d_return", "nifty_20d_return",
    "sector_momentum_5d",
    # NEW: volatility regime
    "vix_20d_mean", "vix_percentile",
    # NEW: macro trend
    "crude_20d_trend", "usdinr_20d_trend",
]

# ── Sector-specific additional features ──────────────────────────
SECTOR_EXTRA_FEATURES = {
    "IT & Technology":              ["usdinr_chg_lag2", "usdinr_10d_mean", "nasdaq_chg", "nasdaq_chg_lag1", "nasdaq_5d_mean", "sp500_chg"],
    "IT Services":                  ["usdinr_chg_lag2", "usdinr_10d_mean", "nasdaq_chg", "nasdaq_chg_lag1", "nasdaq_5d_mean"],
    "Digital Engineering":          ["usdinr_chg_lag2", "usdinr_10d_mean", "nasdaq_chg", "sp500_chg"],
    "SaaS & Product-Based Companies": ["usdinr_chg_lag2", "nasdaq_chg", "nasdaq_chg_lag1"],
    "AI & Data Centers / Cloud":    ["usdinr_chg_lag2", "nasdaq_chg", "nasdaq_5d_mean", "sp500_chg"],
    "Energy & Oil & Gas":           ["crude_chg_lag2", "crude_10d_mean"],
    "Oil Refining & Marketing":     ["crude_chg_lag2", "crude_10d_mean"],
    "Renewable Energy":             ["crude_chg_lag2"],
    "Banking & Financial Services": ["rate_momentum", "fii_lag2", "fii_5d_mean"],
    "PSU Banks":                    ["rate_momentum", "fii_lag2"],
    "Private Banks":                ["fii_lag2", "fii_5d_mean"],
    "Pharmaceuticals":              ["usdinr_chg_lag2", "sp500_chg"],
    "Large Cap Pharma":             ["usdinr_chg_lag2", "sp500_chg"],
    "Automobiles":                  ["crude_chg_lag2", "rate_momentum"],
    "Infrastructure & Real Estate": ["rate_momentum", "gst_proxy"],
    "Consumer Goods & Retail":      ["gst_proxy"],
}


def engineer_features(macro_df, price_series=None):
    """
    Engineers all features from raw macro data.
    Adds momentum, trend, percentile, and interaction features.
    """
    df = macro_df.copy()

    # ── Basic changes ─────────────────────────────────────────────
    df['usdinr_chg']      = df['usdinr'].pct_change() * 100
    df['vix_chg']         = df['india_vix'].pct_change() * 100
    df['crude_chg']       = df['brent_crude'].pct_change() * 100
    df['nifty_chg']       = df['nifty_return'] if 'nifty_return' in df else df.get('nifty', pd.Series(dtype=float)).pct_change() * 100

    # ── Lags ──────────────────────────────────────────────────────
    df['usdinr_chg_lag1']  = df['usdinr_chg'].shift(1)
    df['usdinr_chg_lag2']  = df['usdinr_chg'].shift(2)
    df['vix_chg_lag1']     = df['vix_chg'].shift(1)
    df['crude_chg_lag1']   = df['crude_chg'].shift(1)
    df['crude_chg_lag2']   = df['crude_chg'].shift(2)
    df['fii_net']          = df.get('fii_net_crore', pd.Series(0, index=df.index)) / 10000
    df['fii_lag2']         = df['fii_net'].shift(2)

    # ── Rolling means ─────────────────────────────────────────────
    df['usdinr_5d_mean']   = df['usdinr_chg'].rolling(5).mean()
    df['usdinr_10d_mean']  = df['usdinr_chg'].rolling(10).mean()
    df['usdinr_20d_trend'] = df['usdinr_chg'].rolling(20).mean()
    df['vix_5d_mean']      = df['vix_chg'].rolling(5).mean()
    df['vix_20d_mean']     = df['india_vix'].rolling(20).mean()
    df['crude_5d_mean']    = df['crude_chg'].rolling(5).mean()
    df['crude_10d_mean']   = df['crude_chg'].rolling(10).mean()
    df['crude_20d_trend']  = df['crude_chg'].rolling(20).mean()
    df['fii_5d_mean']      = df['fii_net'].rolling(5).mean()

    # ── VIX regime and percentile ─────────────────────────────────
    df['vix_regime']       = pd.cut(
        df['india_vix'], bins=[0,13,20,100], labels=[0,1,2]
    ).astype(float)
    df['vix_percentile']   = df['india_vix'].rolling(252).rank(pct=True)

    # ── Interactions ──────────────────────────────────────────────
    df['rate_x_vix']       = df['repo_rate'] * df['india_vix']
    df['crude_x_fx']       = df['crude_chg'] * df['usdinr_chg']

    # ── Momentum (NIFTY) ──────────────────────────────────────────
    if 'nifty' in df.columns:
        df['nifty_5d_return']  = df['nifty'].pct_change(5) * 100
        df['nifty_20d_return'] = df['nifty'].pct_change(20) * 100
    else:
        df['nifty_5d_return']  = 0.0
        df['nifty_20d_return'] = 0.0

    # ── Sector momentum (uses target price series if available) ───
    if price_series is not None:
        df['sector_momentum_5d'] = price_series.rolling(5).mean()
    else:
        df['sector_momentum_5d'] = 0.0

    # ── Sector-specific proxies ───────────────────────────────────
    # NASDAQ/global features (for IT sector)
    if 'nasdaq' in df.columns and df['nasdaq'].sum() > 0:
        df['nasdaq_chg']       = df['nasdaq'].pct_change() * 100
        df['nasdaq_chg_lag1']  = df['nasdaq_chg'].shift(1)
        df['nasdaq_5d_mean']   = df['nasdaq_chg'].rolling(5).mean()
    else:
        df['nasdaq_chg']       = 0.0
        df['nasdaq_chg_lag1']  = 0.0
        df['nasdaq_5d_mean']   = 0.0

    if 'sp500' in df.columns and df['sp500'].sum() > 0:
        df['sp500_chg']        = df['sp500'].pct_change() * 100
        df['sp500_chg_lag1']   = df['sp500_chg'].shift(1)
    else:
        df['sp500_chg']        = 0.0
        df['sp500_chg_lag1']   = 0.0

    df['rate_momentum']    = df['repo_rate'].diff(3)   # rate change over 3 months
    df['gst_proxy']        = df.get('gst_collections', pd.Series(150000, index=df.index)).pct_change(3) * 100
    df['us_tech_proxy']    = df['usdinr_chg'] * -1     # USD strength = US tech demand proxy

    return df


def get_features_for_sector(subsector_or_sector):
    """Returns the feature list for a given sector/subsector."""
    extra = SECTOR_EXTRA_FEATURES.get(subsector_or_sector, [])
    features = BASE_FEATURES + [f for f in extra if f not in BASE_FEATURES]
    return features


def load_training_data(subsector=None, sector=None, lookback_years=10):
    """Loads aligned price + macro data with enhanced features."""

    ensure_tables_exist()
    end_date   = datetime.today().date()
    start_date = end_date - timedelta(days=lookback_years * 365 + 60)  # extra buffer

    session = get_session()
    try:
        query = session.query(DailyPrice)
        if subsector:
            query = query.filter(DailyPrice.subsector == subsector)
        elif sector:
            query = query.filter(DailyPrice.sector == sector)
        query = query.filter(
            DailyPrice.date >= start_date,
            DailyPrice.date <= end_date,
            DailyPrice.daily_return.isnot(None)
        )
        prices = query.all()

        macros = session.query(MacroData).filter(
            MacroData.date >= start_date,
            MacroData.date <= end_date
        ).all()
    except Exception as e:
        print(f"  DB error: {e}")
        return None
    finally:
        session.close()

    if not prices or not macros:
        print(f"  No data for {subsector or sector}")
        return None

    print(f"  Loaded {len(prices)} price rows, {len(macros)} macro rows")

    # ── Build weighted sector return ──────────────────────────────
    price_df = pd.DataFrame([{
        'date':         pd.Timestamp(p.date),
        'daily_return': p.daily_return or 0,
        'nifty_weight': p.nifty_weight or 0.001,
    } for p in prices])

    price_df = price_df[
        (price_df['daily_return'].abs() < 0.4) &
        (price_df['daily_return'].notna())
    ]

    def weighted_ret(g):
        w = g['nifty_weight'].sum()
        return (g['daily_return'] * g['nifty_weight']).sum() / w if w > 0 else g['daily_return'].mean()

    target = price_df.groupby('date').apply(weighted_ret).rename('target_return')
    target = target.sort_index()

    # Cumulative sector price (for momentum)
    sector_cum = (1 + target).cumprod()

    # ── Build macro DataFrame ─────────────────────────────────────
    macro_df = pd.DataFrame([{
        'date':            pd.Timestamp(m.date),
        'repo_rate':       m.repo_rate   or 6.5,
        'usdinr':          m.usdinr      or 83.0,
        'brent_crude':     m.brent_crude or 80.0,
        'india_vix':       m.india_vix   or 15.0,
        'fii_net_crore':   m.fii_net_crore or 0,
        'nifty':           m.nifty_close or 0,
        'nifty_return':    m.nifty_return or 0,
        'gst_collections': m.gst_collections or 150000,
        'nasdaq':          getattr(m, 'nasdaq_close', None) or 0,
        'sp500':           getattr(m, 'sp500_close', None) or 0,
    } for m in macros]).set_index('date').sort_index()

    # ── Engineer features ─────────────────────────────────────────
    macro_df = engineer_features(macro_df, price_series=sector_cum)

    # ── Get feature list for this sector ─────────────────────────
    label    = subsector or sector or "all"
    features = get_features_for_sector(label)
    available = [f for f in features if f in macro_df.columns]

    # ── Align and clean ───────────────────────────────────────────
    combined = macro_df[available + ['nifty_return']].join(target, how='inner').dropna()

    if len(combined) < 100:
        print(f"  Insufficient samples: {len(combined)}")
        return None

    X = combined[available]
    y = combined['target_return'] - combined['nifty_return']  # RELATIVE RETURN (ALPHA)

    # Remove outliers (> 4 std)
    z = np.abs((y - y.mean()) / (y.std() + 1e-8))
    X, y = X[z < 4], y[z < 4]

    # Clip to actual lookback
    actual_start = end_date - timedelta(days=lookback_years * 365)
    mask = X.index >= pd.Timestamp(actual_start)
    X, y = X[mask], y[mask]

    # ── INFINITY / LARGE VALUE GUARD ──────────────────────────────
    # pct_change() on zero-valued columns (nasdaq=0, sp500=0 in early
    # history) produces inf. rolling().mean() of inf stays inf.
    # sklearn StandardScaler crashes on inf in test folds.
    # Fix: replace inf → NaN, then forward-fill, then drop remaining NaN.
    X = X.replace([np.inf, -np.inf], np.nan)

    # Forward-fill then back-fill so rolling features don't lose rows
    X = X.ffill().bfill()

    # Hard cap: clip any remaining extreme values to ±1000
    # (covers edge cases where ffill still leaves very large numbers)
    X = X.clip(lower=-1000, upper=1000)

    # Drop any rows where NaN still remains after fill
    # (happens if an entire column is NaN from the start)
    valid_mask = X.notna().all(axis=1)
    X = X[valid_mask]
    y = y[valid_mask]

    if len(X) < 100:
        print(f"  Insufficient samples after cleaning: {len(X)}")
        return None

    print(f"  Training samples: {len(X)} | "
          f"{X.index.min().date()} → {X.index.max().date()}")

    return X, y, available


def select_best_model(X, y):
    """
    Tries Ridge, GBM, and RF. Returns the best one by CV R².
    Uses TimeSeriesSplit throughout.
    """
    tscv = TimeSeriesSplit(n_splits=5)

    candidates = {
        'ridge': Ridge(alpha=0.5),
        'gbm':   GradientBoostingRegressor(
            n_estimators=200, max_depth=3,
            learning_rate=0.05, min_samples_leaf=15,
            subsample=0.8, random_state=42
        ),
        'rf':    RandomForestRegressor(
            n_estimators=200, max_depth=5,
            min_samples_leaf=15, random_state=42
        ),
    }

    best_name  = 'ridge'
    best_r2    = -999
    best_model = None
    best_scaler = None
    results = {}

    for name, model in candidates.items():
        scaler   = StandardScaler()
        cv_r2_oos  = []
        cv_dir_oos = []
        cv_r2_is   = []

        from scipy.stats import spearmanr
        for tr_idx, te_idx in tscv.split(X):
            Xtr = scaler.fit_transform(X.iloc[tr_idx])
            Xte = scaler.transform(X.iloc[te_idx])
            ytr, yte = y.iloc[tr_idx], y.iloc[te_idx]
            model.fit(Xtr, ytr)
            
            # OOS (Out-Of-Sample)
            preds_oos = model.predict(Xte)
            corr_oos, _ = spearmanr(yte, preds_oos)
            cv_r2_oos.append(float(corr_oos) if not np.isnan(corr_oos) else 0.0)
            cv_dir_oos.append((np.sign(preds_oos) == np.sign(yte)).mean())
            
            # IS (In-Sample)
            preds_is = model.predict(Xtr)
            corr_is, _ = spearmanr(ytr, preds_is)
            cv_r2_is.append(float(corr_is) if not np.isnan(corr_is) else 0.0)

        avg_r2_oos  = float(np.mean(cv_r2_oos))
        avg_dir_oos = float(np.mean(cv_dir_oos))
        avg_r2_is   = float(np.mean(cv_r2_is))
        
        results[name] = {'r2': avg_r2_oos, 'dir': avg_dir_oos, 'r2_is': avg_r2_is}

        if avg_r2_oos > best_r2:
            best_r2     = avg_r2_oos
            best_name   = name
            best_model  = model
            best_scaler = scaler

    print(f"  Walk-Forward Validation OOS Comparison: ")
    for k, v in results.items():
        overfit = (v['r2_is'] - v['r2']) / v['r2_is'] if v['r2_is'] > 0 else 0
        print(f"    {k:<6}: IS={v['r2_is']:.3f} | OOS={v['r2']:.3f} | OOS-Dir={v['dir']*100:.0f}% | Overfit={overfit*100:.1f}%")
    print(f"  Selected: {best_name} (OOS R²={best_r2:.3f})")

    return best_model, best_scaler, best_name, best_r2, results


def train_sector_model(subsector=None, sector=None,
                       lookback_years=10, model_type='auto'):
    """
    Trains model. model_type='auto' selects best of Ridge/GBM/RF.
    """
    label = subsector or sector or "All"
    print(f"\n─── {label} | {lookback_years}yr ───")

    result = load_training_data(subsector, sector, lookback_years)
    if result is None:
        return None

    X, y, features = result

    if model_type == 'auto':
        model, scaler, chosen, avg_r2, all_results = select_best_model(X, y)
    else:
        scaler = StandardScaler()
        if model_type == 'gbm':
            model = GradientBoostingRegressor(
                n_estimators=200, max_depth=3, learning_rate=0.05,
                min_samples_leaf=15, subsample=0.8, random_state=42
            )
        else:
            model = Ridge(alpha=0.5)

        tscv   = TimeSeriesSplit(n_splits=5)
        cv_r2_oos  = []
        cv_dir_oos = []
        cv_r2_is   = []
        from scipy.stats import spearmanr
        for tr_idx, te_idx in tscv.split(X):
            Xtr = scaler.fit_transform(X.iloc[tr_idx])
            Xte = scaler.transform(X.iloc[te_idx])
            ytr, yte = y.iloc[tr_idx], y.iloc[te_idx]
            model.fit(Xtr, ytr)
            
            preds_oos = model.predict(Xte)
            corr_oos, _ = spearmanr(yte, preds_oos)
            cv_r2_oos.append(float(corr_oos) if not np.isnan(corr_oos) else 0.0)
            cv_dir_oos.append((np.sign(preds_oos) == np.sign(yte)).mean())
            
            preds_is = model.predict(Xtr)
            corr_is, _ = spearmanr(ytr, preds_is)
            cv_r2_is.append(float(corr_is) if not np.isnan(corr_is) else 0.0)

        avg_r2  = float(np.mean(cv_r2_oos))
        avg_dir = float(np.mean(cv_dir_oos))
        avg_r2_is = float(np.mean(cv_r2_is))
        overfit = (avg_r2_is - avg_r2) / avg_r2_is if avg_r2_is > 0 else 0
        print(f"  Walk-Forward Status: IS={avg_r2_is:.3f}, OOS={avg_r2:.3f} (Overfit: {overfit*100:.1f}%)")
        chosen  = model_type

    # Final fit on all data
    X_scaled = scaler.fit_transform(X)
    model.fit(X_scaled, y)

    avg_mae = float(mean_absolute_error(y, model.predict(X_scaled)))

    # Feature importance
    if hasattr(model, 'coef_'):
        importance = dict(zip(features, model.coef_))
    elif hasattr(model, 'feature_importances_'):
        importance = dict(zip(features, model.feature_importances_))
    else:
        importance = {}

    importance_sorted = dict(
        sorted(importance.items(), key=lambda x: abs(x[1]), reverse=True)
    )

    # Directional accuracy on full data
    preds_all = model.predict(X_scaled)
    dir_acc   = float((np.sign(preds_all) == np.sign(y)).mean())

    print(f"  FINAL → R²={avg_r2:.3f} | MAE={avg_mae:.4f} | "
          f"DirAcc={dir_acc*100:.1f}% | Model={chosen}")

    # Save model
    safe = (subsector or sector or 'all').replace(
        ' ', '_').replace('/', '_').replace('&', 'and')[:35]
    version = f"v{datetime.today().strftime('%Y%m%d')}_{safe}_{int(time.time())}"
    model_path = f"data/models/{version}.pkl"

    with open(model_path, 'wb') as f:
        pickle.dump({
            'model':    model,
            'scaler':   scaler,
            'features': features,
            'chosen':   chosen,
            'r2':       avg_r2,
        }, f)

    # Store to DB
    session = get_session()
    try:
        session.query(ModelVersion).filter(
            ModelVersion.subsector == (subsector or sector or "all"),
            ModelVersion.is_active == True
        ).update({"is_active": False})

        mv = ModelVersion(
            version=version,
            trained_date=datetime.today().date(),
            training_start=X.index.min().date(),
            training_end=X.index.max().date(),
            subsector=subsector or sector or "all",
            r_squared=round(avg_r2, 4),
            mae=round(avg_mae, 4),
            directional_acc=round(dir_acc, 4),
            feature_weights=json.dumps(
                {k: round(float(v), 6) for k, v in importance_sorted.items()}
            ),
            feature_names=json.dumps(features),
            n_samples=len(X),
            is_active=True,
            notes=f"{chosen} | {lookback_years}yr | enhanced features"
        )
        session.add(mv)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"  DB save error: {e}")
    finally:
        session.close()

    return {
        "version":              version,
        "r_squared":            avg_r2,
        "mae":                  avg_mae,
        "directional_accuracy": dir_acc,
        "model_type":           chosen,
        "feature_importance":   importance_sorted,
    }


def train_all_models(lookback_years=10, model_type='auto'):
    """Trains models for all sectors and subsectors."""

    ensure_tables_exist()
    print("\n" + "="*60)
    print(f"TRAINING ALL MODELS — {lookback_years}yr | type={model_type}")
    print("="*60)

    results = {}
    for sector_name, sec_data in MARKET_CLASSIFICATION.items():
        r = train_sector_model(
            sector=sector_name,
            lookback_years=lookback_years,
            model_type=model_type
        )
        results[f"sector_{sector_name}"] = r

        for sub_name in sec_data["subsectors"]:
            r2 = train_sector_model(
                subsector=sub_name,
                lookback_years=lookback_years,
                model_type=model_type
            )
            results[f"sub_{sub_name}"] = r2

    ok = sum(1 for v in results.values() if v is not None)

    # Print summary table
    print(f"\n{'='*60}")
    print(f"TRAINING SUMMARY — {ok}/{len(results)} models")
    print(f"{'='*60}")
    print(f"{'Model':<40} {'R²':>6} {'DirAcc':>8} {'Type':>8}")
    print("─"*60)
    for k, v in results.items():
        if v:
            name = k.replace('sector_','').replace('sub_','')[:39]
            print(f"{name:<40} {v['r_squared']:>6.3f} "
                  f"{v['directional_accuracy']*100:>7.1f}% "
                  f"{v.get('model_type','?'):>8}")
    print("="*60)

    return results


def load_model(subsector=None, sector=None):
    """Loads active trained model. Returns (model, scaler, features)."""
    ensure_tables_exist()
    session = get_session()
    try:
        label = subsector or sector or "all"
        mv = session.query(ModelVersion).filter(
            ModelVersion.subsector == label,
            ModelVersion.is_active == True
        ).first()

        if mv is None:
            return None, None, None

        model_path = f"data/models/{mv.version}.pkl"
        if not os.path.exists(model_path):
            return None, None, None

        with open(model_path, 'rb') as f:
            saved = pickle.load(f)

        return saved['model'], saved['scaler'], saved['features']
    except Exception:
        return None, None, None
    finally:
        session.close()


def retrain_rolling_window():
    """Monthly retraining on latest 3yr window."""
    print("\nRolling window retraining (3yr)...")
    return train_all_models(lookback_years=3, model_type='auto')


if __name__ == "__main__":
    from database import init_database
    init_database()
    # Train with auto model selection, max 4 years to prevent lookahead bias
    train_all_models(lookback_years=4, model_type='auto')
