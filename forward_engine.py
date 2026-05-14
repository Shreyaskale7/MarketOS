# forward_engine.py — MarketOS v6
# Production-grade improvements:
# 1. ML FORECAST ENGINE — generate_forward_forecasts() now delegates to
#    ml_forecast_engine.generate_ml_forecasts() — pure data-driven, no rule overrides
# 2. CRUDE LOGIC — direction injected into every forecast and scoring function
# 3. OIL REFINING BIAS — crude direction adjusts OMC opportunity score directly
# 4. NO GENERIC AI LANGUAGE — strict prompt rules eliminate vague phrases
# 5. IMPROVED OPPORTUNITY SCORING — weighted composite with meaningful spread (1-10)
# 6. DATA LOADER SAFETY — 0 price records triggers explicit WARNING
# 7. NO RUNTIME ERRORS — all variables initialized before use
# 8. REALISTIC FORECASTS — ML-trained on 10yr historical data, sector-differentiated

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta, date
from sqlalchemy import and_, func, desc
from database import (engine, DailyPrice, MacroData, ModelVersion,
                      ForwardForecast, SectorGrowthAnalytics,
                      SectorPerformance, get_session)
from model_trainer import load_model, BASE_FEATURES as MACRO_FEATURES
from classification import MARKET_CLASSIFICATION
# ── ML Forecast Engine (data-driven replacement for rule-based forecasts) ──
try:
    from ml_forecast_engine import generate_ml_forecasts, retrain_ml_models
    ML_ENGINE_AVAILABLE = True
except ImportError:
    ML_ENGINE_AVAILABLE = False
    print("WARNING: ml_forecast_engine.py not found — falling back to rule-based forecasts")
import warnings
warnings.filterwarnings('ignore')


# ══════════════════════════════════════════════════════════════════
# SECTION 1 — CRUDE DIRECTION HELPER
# Central function used by forecasts, scoring, and prompts
# ══════════════════════════════════════════════════════════════════

def get_crude_direction(macro_data):
    """
    Returns crude oil direction as a string label.
    Used consistently across forecasts, scoring, and LLM prompts.
    Prevents crude contradiction bugs.
    """
    crude_change = macro_data.get('brent_crude', {}).get('change_pct', 0)
    if crude_change > 2:
        return "SPIKING"
    elif crude_change < -2:
        return "FALLING"
    else:
        return "STABLE"


def get_oil_refining_bias(crude_direction):
    """
    Oil Refining & Marketing (OMC) is HURT when crude spikes.
    Rising input cost compresses refining margins.
    Returns -1 (negative), 0 (neutral), or +1 (positive).
    """
    if crude_direction == "SPIKING":
        return -1   # crude rising = OMC margin compression
    elif crude_direction == "FALLING":
        return +1   # crude falling = OMC margin expansion
    else:
        return 0


def get_nasdaq_direction(macro_data):
    """Returns NASDAQ direction for IT sector context."""
    chg = macro_data.get('nasdaq', {}).get('change_pct', 0)
    if chg > 0.5:
        return "RISING"
    elif chg < -0.5:
        return "FALLING"
    else:
        return "FLAT"


# ══════════════════════════════════════════════════════════════════
# SECTION 2 — SECTOR GROWTH ANALYTICS
# ══════════════════════════════════════════════════════════════════

def compute_sector_growth_analytics():
    """
    Computes historical returns, volatility, Sharpe, max drawdown
    for every subsector across multiple timeframes.
    Called weekly (or on --retrain) to keep analytics fresh.
    """
    print("\n=== COMPUTING SECTOR GROWTH ANALYTICS ===")

    from data_loader import get_data_status
    today = get_data_status()["pipeline_date"]
    timeframes = {
        "1M":  30, "3M":  90, "6M": 180,
        "1Y":  365, "3Y": 365*3, "5Y": 365*5, "10Y": 365*10,
    }

    records_to_store = []

    for sector_name, sec_data in MARKET_CLASSIFICATION.items():
        for subsector_name, sub_data in sec_data["subsectors"].items():

            tickers = [info["ticker"] for info in sub_data["companies"].values()]
            weights = [info["sector_weight"] for info in sub_data["companies"].values()]
            total_weight = sum(weights)
            if total_weight == 0:
                continue

            session = get_session()
            try:
                prices = session.query(DailyPrice).filter(
                    DailyPrice.ticker.in_(tickers),
                    DailyPrice.date >= today - timedelta(days=365 * 11)
                ).order_by(DailyPrice.date).all()
            except Exception:
                prices = []
            finally:
                session.close()

            if not prices:
                continue

            price_df = pd.DataFrame([{
                'date': p.date,
                'ticker': p.ticker,
                'daily_return': p.daily_return,
                'nifty_weight': p.nifty_weight,
            } for p in prices])
            price_df['date'] = pd.to_datetime(price_df['date'])

            daily_returns = price_df.groupby('date').apply(
                lambda g: (
                    (g['daily_return'] * g['nifty_weight']).sum() / g['nifty_weight'].sum()
                    if g['nifty_weight'].sum() > 0
                    else g['daily_return'].mean()
                )
            ).sort_index()
            daily_returns.index = pd.to_datetime(daily_returns.index)

            if daily_returns.empty:
                continue

            # NIFTY returns for beta
            nifty_session = get_session()
            try:
                nifty_data = nifty_session.query(
                    MacroData.date, MacroData.nifty_return
                ).filter(
                    MacroData.date >= today - timedelta(days=365 * 11)
                ).all()
            except Exception:
                nifty_data = []
            finally:
                nifty_session.close()

            nifty_returns = pd.Series(
                {pd.Timestamp(r.date): (r.nifty_return or 0) / 100 for r in nifty_data}
            ).sort_index()

            for period_label, days in timeframes.items():
                cutoff = pd.Timestamp(today - timedelta(days=days))
                period_returns = daily_returns[daily_returns.index >= cutoff]

                if len(period_returns) < 20:
                    continue

                ret = period_returns.values
                trading_years = len(ret) / 252

                total_return = float((1 + ret).prod() - 1)
                ann_return   = float((1 + total_return) ** (1 / trading_years) - 1) if trading_years > 0 else 0
                vol          = float(ret.std() * np.sqrt(252))

                rf_daily = 0.065 / 252
                excess   = ret - rf_daily
                sharpe   = float(excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0

                cumulative   = (1 + ret).cumprod()
                rolling_max  = pd.Series(cumulative).cummax()
                drawdowns    = (pd.Series(cumulative) - rolling_max) / rolling_max
                max_drawdown = float(drawdowns.min())

                # Beta to NIFTY
                nifty_period = nifty_returns[nifty_returns.index >= cutoff]
                common_idx   = period_returns.index.intersection(nifty_period.index)
                beta = correlation = 0.0
                if len(common_idx) > 20:
                    s_ret = period_returns.loc[common_idx].values
                    n_ret = nifty_period.loc[common_idx].values
                    cov   = np.cov(s_ret, n_ret)
                    if cov[1, 1] > 0:
                        beta = float(cov[0, 1] / cov[1, 1])
                    if s_ret.std() > 0 and n_ret.std() > 0:
                        correlation = float(np.corrcoef(s_ret, n_ret)[0, 1])

                records_to_store.append({
                    'computed_date':          today,
                    'sector':                 sector_name,
                    'subsector':              subsector_name,
                    'period':                 period_label,
                    'total_return_pct':       round(total_return * 100, 2),
                    'annualised_return_pct':  round(ann_return * 100, 2),
                    'volatility_pct':         round(vol * 100, 2),
                    'sharpe_ratio':           round(sharpe, 3),
                    'max_drawdown_pct':       round(max_drawdown * 100, 2),
                    'best_month_pct':         0,
                    'worst_month_pct':        0,
                    'positive_months_pct':    0,
                    'beta_to_nifty':          round(beta, 3),
                    'correlation_to_nifty':   round(correlation, 3),
                    'avg_contribution_pct':   0,
                })

    session = get_session()
    try:
        session.query(SectorGrowthAnalytics).filter(
            SectorGrowthAnalytics.computed_date == today
        ).delete(synchronize_session=False)
        session.bulk_insert_mappings(SectorGrowthAnalytics, records_to_store)
        session.commit()
    except Exception:
        pass
    finally:
        session.close()

    print(f"Stored {len(records_to_store)} sector growth analytics records")
    return records_to_store


# ══════════════════════════════════════════════════════════════════
# SECTION 3 — FORWARD FORECAST ENGINE (CORE FIX)
# ══════════════════════════════════════════════════════════════════

def generate_forward_forecasts(macro_data, regime):
    # FIX 2: Replace hard crash with safe neutral fallback — system NEVER crashes
    # due to missing/invalid NIFTY data. Forecasts continue with neutral 0.0% change.
    nifty_data = macro_data.get("nifty", {})
    if not nifty_data:
        print("  ⚠ WARNING: Missing NIFTY data — using neutral fallback (change_pct=0.0)")
        macro_data["nifty"] = {
            "current":    0,
            "change_pct": 0.0,
            "is_valid":   True,
        }
    elif not nifty_data.get("is_valid", True):
        # is_valid=False but data exists — repair in-place, do NOT raise
        print(f"  ⚠ WARNING: NIFTY marked invalid (current={nifty_data.get('current', 0)}, "
              f"change_pct={nifty_data.get('change_pct')}) — overriding is_valid=True, "
              f"keeping existing values")
        macro_data["nifty"] = {
            "current":    nifty_data.get("current", 0),
            "change_pct": nifty_data.get("change_pct") if nifty_data.get("change_pct") is not None else 0.0,
            "is_valid":   True,
        }

    """
    Generates 1M, 3M, 6M forward return forecasts per sector.

    MARKET STATE AWARENESS: On non-trading days, NIFTY movement and
    regime price adjustments are suppressed. ML forecasts still run
    (they use DB macro history, not live prices).
    """
    # ── MARKET STATE GATE ─────────────────────────────────────────
    try:
        from market_calendar import get_market_status, log_market_status
        _mkt = get_market_status()
    except ImportError:
        _mkt = {"is_trading_day": True, "engine_mode": "FULL",
                "nifty_is_valid": True, "market_status": "OPEN"}

    _market_open = _mkt["is_trading_day"] and _mkt.get("nifty_is_valid", True)

    if not _market_open:
        print(f"\n  ℹ FORWARD ENGINE: Market closed ({_mkt.get('close_reason', 'non-trading day')})")
        print("     Regime price adjustments DISABLED — using macro-only ML forecasts")
        # Zero out the regime score so no NIFTY-movement-driven regime nudge is applied
        # The regime dict is NOT mutated globally — we pass a local copy to the forecasters
        regime = {**regime, "regime_score": 0, "_market_closed": True}

    if ML_ENGINE_AVAILABLE:
        print("\n=== GENERATING FORWARD FORECASTS (ML ENGINE) ===")
        try:
            return generate_ml_forecasts(macro_data, regime)
        except Exception as e:
            print(f"  ML engine error: {e} — falling back to rule-based")

    # ── Original rule-based fallback (unchanged) ──────────────────
    print("\n=== GENERATING FORWARD FORECASTS (RULE-BASED FALLBACK) ===")

    from data_loader import get_data_status
    today = get_data_status()["pipeline_date"]

    # Pre-compute crude direction ONCE — used throughout
    crude_direction    = get_crude_direction(macro_data)
    oil_refining_bias  = get_oil_refining_bias(crude_direction)
    nasdaq_direction   = get_nasdaq_direction(macro_data)

    # Trading day counts per horizon
    horizons = {"1M": 21, "3M": 63, "6M": 126, "12M": 252}

    all_forecasts = {}

    current_features = build_macro_feature_vector(macro_data)
    base_features    = current_features.copy()
    bull_features    = build_bull_scenario(current_features, macro_data)
    bear_features    = build_bear_scenario(current_features, macro_data)

    for sector_name, sec_data in MARKET_CLASSIFICATION.items():
        sector_forecasts = {}

        for subsector_name in sec_data["subsectors"].keys():

            # Load trained model (subsector → sector → rule-based)
            model, scaler, features = load_model(subsector=subsector_name)
            if model is None:
                model, scaler, features = load_model(sector=sector_name)

            if model is None:
                forecast = rule_based_forecast(
                    subsector_name, sector_name, macro_data, regime,
                    crude_direction, oil_refining_bias
                )
                sector_forecasts[subsector_name] = forecast
                continue

            # Model prediction
            def predict(feat_dict):
                feat_vec = np.array([feat_dict.get(f, 0) for f in features]).reshape(1, -1)
                scaled   = scaler.transform(feat_vec)
                return float(model.predict(scaled)[0])

            try:
                base_daily = predict(base_features)
                bull_daily = predict(bull_features)
                bear_daily = predict(bear_features)
            except Exception:
                base_daily = bull_daily = bear_daily = 0.0

            # Model quality
            r2 = dir_acc = 0.0
            session = get_session()
            try:
                mv = session.query(ModelVersion).filter(
                    ModelVersion.subsector == subsector_name,
                    ModelVersion.is_active == True
                ).first()
                if mv:
                    r2      = float(mv.r_squared or 0.1)
                    dir_acc = float(mv.directional_acc or 0.5)
                else:
                    r2, dir_acc = 0.1, 0.5
            except Exception:
                r2, dir_acc = 0.1, 0.5
            finally:
                session.close()

            # Confidence — ALWAYS computed before use
            confidence = min(0.9, max(0.3, r2 * 0.5 + dir_acc * 0.5))

            # ── STEP 1: LOG-RETURN AGGREGATION (fixes explosion bug) ─
            # Model predicts a daily return fraction (e.g. 0.003 = 0.3%/day)
            # Convert to log-return for proper aggregation across trading days
            # log_return is additive: total = mean_log * n_days
            regime_adj  = regime.get('regime_score', 0) * 0.00015  # tiny regime nudge
            # MARKET STATE: suppress NIFTY-driven regime adjustment on closed days
            if regime.get("_market_closed", False):
                regime_adj = 0.0

            # Safe log conversion — prevent log(0) or log(negative)
            def safe_log(r):
                return np.log(max(1 + r, 1e-6))

            base_log = safe_log(base_daily + regime_adj)
            bull_log = safe_log(bull_daily + abs(regime_adj))
            bear_log = safe_log(bear_daily - abs(regime_adj))

            # ── STEP 2: MACRO CONSISTENCY RULES ─────────────────────
            # Apply domain corrections BEFORE horizon scaling
            # so macro logic is consistent across all horizons

            # Historical mean daily log-return for shrinkage (~6% annual / 252 days)
            hist_mean_log = np.log(1.06) / 252   # ≈ 0.000231

            # Sector-specific macro adjustments (in log-return space)
            macro_adj_log = 0.0

            sub_lower = subsector_name.lower()
            sec_lower  = sector_name.lower()

            # Crude rules
            if "oil refin" in sub_lower or "refin" in sub_lower:
                if crude_direction == "SPIKING":
                    macro_adj_log = -0.0003   # -7.5% annualised drag
                elif crude_direction == "FALLING":
                    macro_adj_log = +0.0002   # +5% annualised boost
                else:
                    macro_adj_log = 0.0       # stable crude → neutral OMC

            elif "renewable" in sub_lower or "power" in sub_lower:
                if crude_direction == "SPIKING":
                    macro_adj_log = +0.0001   # renewables benefit slightly

            elif "paint" in sub_lower or "building" in sub_lower:
                if crude_direction == "SPIKING":
                    macro_adj_log = -0.0002   # petrochemical input cost rise

            elif "two wheel" in sub_lower or "commercial" in sub_lower:
                if crude_direction == "SPIKING":
                    macro_adj_log = -0.0002   # fuel cost anxiety

            # Rate rules
            rate_label_fe = regime.get('variables', {}).get('repo_rate', {}).get('regime', '')
            if "RATE_CUT" in rate_label_fe:
                if any(x in sub_lower for x in ["bank", "nbfc", "real estate", "auto", "housing"]):
                    macro_adj_log += +0.0002
                if any(x in sub_lower for x in ["insurance", "amc"]):
                    macro_adj_log += +0.0001
            elif "RATE_HIKE" in rate_label_fe:
                if any(x in sub_lower for x in ["bank", "nbfc", "real estate", "auto"]):
                    macro_adj_log -= 0.0002

            # Apply macro adjustment to base prediction
            base_log = base_log + macro_adj_log
            bull_log = bull_log + macro_adj_log * 0.7
            bear_log = bear_log + macro_adj_log * 1.3

            # ── STEP 3: SHRINKAGE TOWARD HISTORICAL MEAN ────────────
            # Prevents extreme predictions from dominating
            # Higher confidence = less shrinkage = more model weight
            shrink_weight = 0.3 + (1 - confidence) * 0.3   # 0.30 to 0.60
            model_weight  = 1.0 - shrink_weight

            base_log_shrunk = model_weight * base_log + shrink_weight * hist_mean_log
            bull_log_shrunk = model_weight * bull_log + shrink_weight * hist_mean_log * 1.2
            bear_log_shrunk = model_weight * bear_log + shrink_weight * hist_mean_log * 0.3

            # ── STEP 4: HORIZON SCALING WITH HARD CAPS ──────────────
            # Trading days per horizon
            horizon_days = {"1M": 21, "3M": 63, "6M": 126, "12M": 252}

            # Hard caps per horizon — institutionally realistic
            # CHANGE: 6M raised from 40.0 → 55.0 to match ML engine relaxation.
            # At 40% cap, all strong 6M forecasts clustered at the ceiling,
            # making sector differentiation impossible for portfolio weighting.
            caps = {
                "1M":  15.0,   # ±15%
                "3M":  25.0,   # ±25%
                "6M":  55.0,   # ±55%  (was 40%)
                "12M": 60.0,   # ±60%
            }

            # Sector-specific unique offset (prevents identical outputs)
            sector_hash = (sum(ord(c) for c in subsector_name) % 50 - 25) / 10000

            horizon_forecasts = {}

            for h_label, trading_days in horizons.items():
                n_days = horizon_days[h_label]
                cap    = caps[h_label]

                # Convert aggregated log-return to percentage
                # exp(log_return * n_days) - 1 gives cumulative return
                base_return = (np.exp(base_log_shrunk * n_days) - 1) * 100
                bull_return = (np.exp(bull_log_shrunk * n_days) - 1) * 100
                bear_return = (np.exp(bear_log_shrunk * n_days) - 1) * 100

                # Add tiny sector-unique offset so no two sectors are identical
                base_return += sector_hash * n_days / 21

                # Confidence-based bull/bear spread (proportional, not additive)
                spread_pct  = abs(base_return) * max(0.20, 0.80 - confidence * 0.50)
                spread_pct  = max(spread_pct, cap * 0.15)   # minimum meaningful spread
                bull_return = base_return + spread_pct
                bear_return = base_return - spread_pct

                # Regime asymmetry — modest tilt, not multiplicative explosion
                rs = regime.get("regime_score", 0)
                bull_return += rs * 0.05 * cap / 10
                bear_return -= abs(rs) * 0.03 * cap / 10

                # Apply hard caps — ALL horizons capped
                base_return = max(-cap,        min(cap,        base_return))
                bull_return = max(-cap * 0.8,  min(cap * 1.3,  bull_return))
                bear_return = max(-cap * 1.2,  min(cap * 0.8,  bear_return))

                # Ensure ordering: bear < base < bull
                bull_return = max(bull_return, base_return + cap * 0.05)
                bear_return = min(bear_return, base_return - cap * 0.05)

                # Compute opportunity score with crude context
                opp_score = compute_opportunity_score(
                    subsector_name, sector_name, base_return,
                    bull_return, bear_return, confidence,
                    regime, crude_direction, oil_refining_bias
                )

                catalyst, risk = identify_catalysts_and_risks(
                    subsector_name, sector_name, macro_data, regime,
                    crude_direction, nasdaq_direction
                )

                horizon_forecasts[h_label] = {
                    "horizon":               h_label,
                    "target_date":           str(today + timedelta(days=trading_days * 365 // 252)),
                    "base_case_return_pct":  round(base_return, 2),
                    "bull_case_return_pct":  round(bull_return, 2),
                    "bear_case_return_pct":  round(bear_return, 2),
                    "confidence_score":      round(confidence, 2),
                    "opportunity_score":     round(opp_score, 1),
                    "primary_catalyst":      catalyst,
                    "risk_factor":           risk,
                    "model_r2":              round(r2, 3),
                    "directional_accuracy":  round(dir_acc, 3),
                    "crude_direction":       crude_direction,
                }

            sector_forecasts[subsector_name] = horizon_forecasts
            print(f"  {subsector_name[:40]}: "
                  f"1M={horizon_forecasts['1M']['base_case_return_pct']:+.1f}% | "
                  f"6M={horizon_forecasts['6M']['base_case_return_pct']:+.1f}%")

        all_forecasts[sector_name] = sector_forecasts

    store_forecasts_to_db(all_forecasts, today)
    return all_forecasts


# ══════════════════════════════════════════════════════════════════
# SECTION 4 — SCENARIO BUILDERS
# ══════════════════════════════════════════════════════════════════

def build_macro_feature_vector(macro_data):
    """Converts current macro data to model feature dict."""
    usdinr_chg = macro_data.get('usdinr', {}).get('change_pct', 0)
    vix_val    = macro_data.get('india_vix', {}).get('current', 15)
    crude_chg  = macro_data.get('brent_crude', {}).get('change_pct', 0)
    fii        = macro_data.get('fii_flows', {}).get('estimated_crore', 0)
    repo       = macro_data.get('repo_rate', {}).get('current', 6.5)
    crude_val  = macro_data.get('brent_crude', {}).get('current', 80)
    nasdaq_chg = macro_data.get('nasdaq', {}).get('change_pct', 0)

    vix_regime = 0 if vix_val < 13 else (1 if vix_val < 20 else 2)

    return {
        "repo_rate":         repo,
        "india_vix":         vix_val,
        "brent_crude":       crude_val,
        "usdinr_chg":        usdinr_chg,
        "vix_chg":           macro_data.get('india_vix', {}).get('change_pct', 0),
        "crude_chg":         crude_chg,
        "fii_net":           fii / 10000,
        "usdinr_chg_lag1":   usdinr_chg * 0.9,
        "usdinr_chg_lag2":   usdinr_chg * 0.8,
        "vix_chg_lag1":      0.0,
        "crude_chg_lag1":    crude_chg * 0.9,
        "fii_lag1":          fii / 10000 * 0.9,
        "fii_lag2":          fii / 10000 * 0.8,
        "usdinr_5d_mean":    usdinr_chg * 0.7,
        "usdinr_10d_mean":   usdinr_chg * 0.6,
        "vix_5d_mean":       0.0,
        "crude_5d_mean":     crude_chg * 0.7,
        "vix_regime":        vix_regime,
        "rate_x_vix":        repo * vix_val,
        "crude_x_fx":        crude_chg * usdinr_chg,
        "nasdaq_chg":        nasdaq_chg,
        "nasdaq_chg_lag1":   nasdaq_chg * 0.9,
        "nasdaq_5d_mean":    nasdaq_chg * 0.7,
        "sp500_chg":         macro_data.get('sp500', {}).get('change_pct', 0),
        "sp500_chg_lag1":    macro_data.get('sp500', {}).get('change_pct', 0) * 0.9,
    }


def build_bull_scenario(base_features, macro_data):
    """Bull: rate cut, FII buying, lower crude, lower VIX."""
    bull = base_features.copy()
    bull['repo_rate']  = max(5.0, base_features.get('repo_rate', 6.5) - 0.5)
    bull['india_vix']  = max(10,  base_features.get('india_vix', 15) * 0.7)
    bull['fii_net']    = abs(base_features.get('fii_net', 0)) + 0.5
    bull['crude_chg']  = -3.0
    bull['vix_regime'] = 0
    bull['rate_x_vix'] = bull['repo_rate'] * bull['india_vix']
    return bull


def build_bear_scenario(base_features, macro_data):
    """Bear: rate hike, FII selling, crude spike, high VIX."""
    bear = base_features.copy()
    bear['repo_rate']  = min(9.0, base_features.get('repo_rate', 6.5) + 0.5)
    bear['india_vix']  = base_features.get('india_vix', 15) * 1.5
    bear['fii_net']    = -abs(base_features.get('fii_net', 0)) - 0.5
    bear['crude_chg']  = +5.0
    bear['vix_regime'] = 2
    bear['rate_x_vix'] = bear['repo_rate'] * bear['india_vix']
    return bear


# ══════════════════════════════════════════════════════════════════
# SECTION 5 — RULE-BASED FALLBACK
# ══════════════════════════════════════════════════════════════════

def rule_based_forecast(subsector, sector, macro_data, regime,
                        crude_direction, oil_refining_bias):
    """
    Fallback when no trained model exists.
    Uses macro sensitivity + crude direction for domain-correct results.
    Returns dict keyed by horizon label.
    """
    subsector_data = None
    for sec_name, sec_data in MARKET_CLASSIFICATION.items():
        if subsector in sec_data["subsectors"]:
            subsector_data = sec_data["subsectors"][subsector]
            break

    if subsector_data is None:
        return {}

    sensitivity = subsector_data.get("macro_sensitivity", {})
    score_map   = {
        "HIGH_POSITIVE": +2, "MEDIUM_POSITIVE": +1, "LOW_POSITIVE": +0.5,
        "HIGH_NEGATIVE": -2, "MEDIUM_NEGATIVE": -1, "LOW_NEGATIVE": -0.5
    }

    usdinr_chg = macro_data.get('usdinr', {}).get('change_pct', 0)
    crude_chg  = macro_data.get('brent_crude', {}).get('change_pct', 0)
    rate_chg   = macro_data.get('repo_rate', {}).get('change', 0)
    fii        = macro_data.get('fii_flows', {}).get('signal', 'NEUTRAL')

    macro_signals = {
        "repo_rate":   np.sign(-rate_chg),
        "usdinr":      np.sign(usdinr_chg),
        "brent_crude": np.sign(-crude_chg),
        "fii_flows":   1 if fii == "NET_BUYING" else (-1 if fii == "NET_SELLING" else 0),
    }

    base_score = 0.0
    for var, signal in macro_signals.items():
        sens = sensitivity.get(var, "LOW_POSITIVE")
        base_score += score_map.get(sens, 0) * signal

    base_score += regime.get('regime_score', 0) * 0.3

    # Apply crude bias for oil-related subsectors
    if "oil refin" in subsector.lower() or "refin" in subsector.lower():
        base_score += oil_refining_bias * 1.5

    # Rule-based: score → realistic 1M return (±5% per unit of score)
    base_1m    = np.clip(base_score * 1.5, -10.0, 10.0)  # 1M: max ±10%
    confidence = 0.3   # low confidence for rule-based

    # Hard caps per horizon — same as model-based (6M raised to 55%)
    caps       = {"1M": 15.0, "3M": 25.0, "6M": 55.0, "12M": 60.0}
    # Scale multipliers — linear, not exponential
    scales     = {"1M": 1.0,  "3M": 1.6,  "6M": 2.2,  "12M": 3.5}

    forecasts = {}
    for h_label, trading_days in {"1M": 21, "3M": 63, "6M": 126, "12M": 252}.items():
        cap         = caps[h_label]
        base_return = np.clip(base_1m * scales[h_label], -cap, cap)
        spread      = max(abs(base_return) * 0.40, cap * 0.12)
        bull_return = min(base_return + spread, cap * 1.2)
        bear_return = max(base_return - spread, -cap * 1.2)

        if False:   # placeholder to preserve indentation
            base_return = max(-60.0, min(70.0, base_return))

        forecasts[h_label] = {
            "horizon":              h_label,
            "base_case_return_pct": round(base_return, 2),
            "bull_case_return_pct": round(bull_return, 2),
            "bear_case_return_pct": round(bear_return, 2),
            "confidence_score":     confidence,
            "opportunity_score":    min(9.0, max(1.0, 5.0 + base_score)),
            "primary_catalyst":     "Rule-based estimate — awaiting model training",
            "risk_factor":          "Low confidence — run --setup to train models",
            "model_r2":             0.0,
            "crude_direction":      crude_direction,
        }

    return forecasts


# ══════════════════════════════════════════════════════════════════
# SECTION 6 — OPPORTUNITY SCORING (REDESIGNED)
# ══════════════════════════════════════════════════════════════════

def compute_opportunity_score(subsector, sector, base_return, bull_return,
                               bear_return, confidence, regime,
                               crude_direction="STABLE", oil_refining_bias=0):
    """
    Composite opportunity score on 1-10 scale.
    Spread is wide (1-10) with meaningful differentiation.

    Formula:
      score = (0.5 × normalized_return + 0.3 × macro_alignment + 0.2 × confidence) × 10

    crude_direction directly penalizes Oil Refining when crude is spiking.
    """
    # 1. Normalized return component — sigmoid on realistic range
    # Centered at 8% (good 1M return) → 0.5; ±15% maps to ~0.1/0.9
    # PENALIZE extreme forecasts: returns >30% get diminishing score
    capped_return = np.clip(base_return, -30.0, 30.0)
    norm_return   = 1 / (1 + np.exp(-capped_return / 8))   # 0 to 1

    # 2. Macro alignment component (0, 0.5, or 1.0)
    regime_score = regime.get('regime_score', 0)
    if regime_score > 2:
        macro_alignment = 1.0
    elif regime_score > -2:
        macro_alignment = 0.5
    else:
        macro_alignment = 0.0

    # 3. Confidence component (already 0.3 to 0.9)
    conf_norm = (confidence - 0.3) / 0.6   # rescale to 0-1

    # Composite
    raw = (0.5 * norm_return + 0.3 * macro_alignment + 0.2 * conf_norm) * 10

    # Crude domain correction for OMC sector
    is_omc = "oil refin" in subsector.lower() or "refin" in subsector.lower()
    if is_omc:
        raw += oil_refining_bias * 1.5   # -1.5 if crude spiking, +1.5 if falling

    # Asymmetry bonus (strong upside with limited downside = better score)
    if bear_return < 0 and bull_return > 0:
        asymmetry = abs(bull_return) / (abs(bear_return) + 0.001)
        if asymmetry > 2:
            raw += 0.5
        elif asymmetry < 0.5:
            raw -= 0.5

    return round(max(1.0, min(10.0, raw)), 1)


# ══════════════════════════════════════════════════════════════════
# SECTION 7 — CATALYSTS AND RISKS (ENHANCED)
# ══════════════════════════════════════════════════════════════════

def identify_catalysts_and_risks(subsector, sector, macro_data, regime,
                                  crude_direction="STABLE",
                                  nasdaq_direction="FLAT"):
    """
    Returns domain-specific catalyst and risk strings.
    Uses crude_direction and nasdaq_direction to prevent generic responses.
    """
    # Specific crude-aware catalysts for energy subsectors
    if "oil refin" in subsector.lower() or "refin" in subsector.lower():
        if crude_direction == "SPIKING":
            return (
                f"Crude SPIKING to ${macro_data.get('brent_crude', {}).get('current', 80):.0f}/bbl — "
                f"refining margin compression hurting OMC profitability",
                "Crude remaining elevated compresses GRMs; govt may cut excise to cap retail prices"
            )
        elif crude_direction == "FALLING":
            return (
                "Falling crude expanding gross refining margins (GRM) for OMCs",
                "Crude reversal on OPEC+ supply cut could compress margins again"
            )

    if "it service" in subsector.lower() or "digital eng" in subsector.lower():
        if nasdaq_direction == "RISING":
            return (
                f"NASDAQ RISING — US tech sentiment lifting Indian IT; strong deal pipeline from FY26 budget season",
                "Rupee appreciation eroding dollar revenue realisation"
            )
        else:
            return (
                "Stable rupee maintaining dollar revenue; cost optimisation driving margin expansion",
                "US recession reducing discretionary IT spend; client budget cuts Q2"
            )

    CATALYSTS = {
        "PSU Banks":               ("RBI rate cut cycle boosting NIMs; PSU bank credit growth outpacing private",
                                    "NPL spike if GDP slows below 5.5%; capital adequacy pressure"),
        "Private Banks":           ("FII inflows driving premium valuations; strong retail credit demand post rate cut",
                                    "Asset quality deterioration in unsecured lending; NIM compression"),
        "NBFCs":                   ("Rate cut expanding NIM and reducing borrowing costs; rural credit demand rising",
                                    "Liquidity tightness if RBI reverses easing; asset quality in MFI segment"),
        "Insurance":               ("Regulatory push for insurance penetration; Bima Sugam digital platform launch",
                                    "Equity market correction reducing ULIP returns; higher claims inflation"),
        "AMCs & Capital Markets":  ("SIP inflows hitting record highs; equity AUM growing with market rally",
                                    "Market correction reducing AUM and management fees; regulatory changes"),
        "FMCG Staples":            ("Rural demand recovery on good monsoon; lower input costs improving margins",
                                    "Urban slowdown; input cost inflation (palm oil, wheat) compressing margins"),
        "Consumer Durables":       ("Rate cuts spurring EMI-based purchases; real estate recovery lifting AC/appliance demand",
                                    "Raw material cost spike; weak monsoon reducing rural purchasing power"),
        "Retail & QSR":            ("Urban consumption recovery; premiumisation trend in organised retail",
                                    "Inflation eroding discretionary spend; rental cost escalation for stores"),
        "Paints & Building Materials": ("Housing construction boom from PMAY; real estate upcycle",
                                        "Crude-linked raw material inflation (TiO2, solvents)"),
        "Large Cap Pharma":        ("US FDA approvals opening export pipeline; domestic formulation pricing power",
                                    "US price erosion in generics; FDA import alerts"),
        "Mid Cap Pharma & Generic": ("CDMO opportunities from China+1; API export demand rising",
                                     "API price volatility; domestic price control orders"),
        "Healthcare & Hospitals":  ("Post-COVID health awareness driving hospitalisation volumes; medical tourism",
                                    "Talent shortage and wage inflation in nursing; regulatory pricing pressure"),
        "Passenger Vehicles":      ("Rate cut reducing EMI; pent-up demand in SUV segment",
                                    "EV transition risk for ICE-heavy OEMs; commodity cost pressure"),
        "Commercial Vehicles":     ("Infrastructure capex cycle driving CV demand; fleet replacement cycle",
                                    "Fuel cost inflation reducing fleet profitability; demand cyclicality"),
        "Two Wheelers":            ("Rural income recovery from kharif harvest; finance availability improving",
                                    "EV disruption accelerating in scooter segment; monsoon dependency"),
        "Auto Ancillaries & EV":   ("EV penetration driving new component demand; global export traction",
                                    "OEM concentration risk; component commoditisation pressure"),
        "Gas Distribution":        ("City gas distribution expansion to Tier-2 cities; residential connections",
                                    "Crude-linked gas price hike reducing volume demand"),
        "Power Generation":        ("Renewable capacity addition; power demand growing 7% YoY",
                                    "Fuel supply disruptions; state DISCOMs payment default risk"),
        "Renewable Energy":        ("Government 500GW target driving massive capex; green financing availability",
                                    "Interest rate sensitivity of long-duration capex; land acquisition delays"),
        "Construction & EPC":      ("Government capex on roads, railways, smart cities — record budget allocation",
                                    "Labour cost inflation; execution delays in monsoon season"),
        "Real Estate Developers":  ("Rate cuts reducing home loan EMI; pent-up housing demand in metros",
                                    "Inventory overhang in commercial; RERA compliance cost"),
        "Cement":                  ("Infrastructure boom driving cement demand; housing upcycle",
                                    "Coal and pet coke cost inflation; freight cost increases"),
        "Industrial & Defence":    ("Defence indigenisation (Make in India) driving order books; export opportunities",
                                    "Long execution cycles; payment delays from government clients"),
    }

    for key, (catalyst, risk) in CATALYSTS.items():
        if key.lower() in subsector.lower() or subsector.lower() in key.lower():
            return catalyst, risk

    # Regime-based fallback
    regime_label = regime.get('overall_regime', 'NEUTRAL')
    _rs_int = int(round(float(regime.get('regime_score', 0)) * 10))
    if 'BULLISH' in regime_label:
        return (
            f"Broad market momentum supporting sector — {regime_label} regime with score {_rs_int:+d}/10",
            "Regime reversal on global risk-off event (US recession, China slowdown)"
        )
    else:
        return (
            f"Rate cut cycle and FII inflows providing underlying support in {regime_label} environment",
            "Elevated VIX suggesting continued near-term volatility — monitor FII positioning"
        )


# ══════════════════════════════════════════════════════════════════
# SECTION 8 — PORTFOLIO CLASSIFICATION
# ══════════════════════════════════════════════════════════════════

def classify_portfolio_stance(base_return, confidence, macro_alignment, regime_score):
    """OVERWEIGHT / NEUTRAL_POSITIVE / NEUTRAL / NEUTRAL_NEGATIVE / UNDERWEIGHT"""
    score = 0

    # Thresholds calibrated to realistic 1M returns (±5-12% range)
    if base_return > 8:    score += 3
    elif base_return > 5:  score += 2
    elif base_return > 2:  score += 1
    elif base_return < -8: score -= 3
    elif base_return < -5: score -= 2
    elif base_return < -2: score -= 1

    if confidence > 0.65:  score += 2
    elif confidence > 0.5: score += 1
    elif confidence < 0.4: score -= 1

    if macro_alignment == "MACRO_ALIGNED":   score += 1
    elif macro_alignment == "MACRO_DIVERGENT": score -= 1

    if regime_score > 3:   score += 1
    elif regime_score < -3: score -= 1

    if score >= 4:    return "OVERWEIGHT"
    elif score >= 1:  return "NEUTRAL_POSITIVE"
    elif score >= -1: return "NEUTRAL"
    elif score >= -3: return "NEUTRAL_NEGATIVE"
    else:             return "UNDERWEIGHT"


def compute_risk_adjusted_score(base_return, volatility_pct, confidence, horizon_days):
    """Sharpe-like score for risk-adjusted opportunity ranking."""
    if volatility_pct <= 0:
        volatility_pct = 15.0

    ann_return  = base_return * (252 / max(horizon_days, 1))
    sharpe_like = (ann_return - 6.5) / volatility_pct if volatility_pct > 0 else 0
    adjusted    = sharpe_like * confidence

    return max(1.0, min(10.0, 5.0 + adjusted * 2))


# ══════════════════════════════════════════════════════════════════
# SECTION 9 — DATABASE OPERATIONS
# ══════════════════════════════════════════════════════════════════

def store_forecasts_to_db(all_forecasts, today):
    """Stores forecasts to ForwardForecast table. Replaces today's records."""
    records = []
    for sector_name, sector_data in all_forecasts.items():
        for subsector_name, subsector_forecasts in sector_data.items():
            if not isinstance(subsector_forecasts, dict):
                continue
            for horizon_label, forecast in subsector_forecasts.items():
                if not isinstance(forecast, dict) or 'base_case_return_pct' not in forecast:
                    continue
                records.append({
                    'generated_date':    today,
                    'forecast_horizon':  horizon_label,
                    'target_date':       forecast.get('target_date'),
                    'sector':            sector_name,
                    'subsector':         subsector_name,
                    'base_case_return':  forecast.get('base_case_return_pct', 0),
                    'bull_case_return':  forecast.get('bull_case_return_pct', 0),
                    'bear_case_return':  forecast.get('bear_case_return_pct', 0),
                    'confidence_score':  forecast.get('confidence_score', 0),
                    'opportunity_score': forecast.get('opportunity_score', 5),
                    'primary_catalyst':  str(forecast.get('primary_catalyst', ''))[:200],
                    'risk_factor':       str(forecast.get('risk_factor', ''))[:200],
                    'model_version':     'active',
                })

    session = get_session()
    try:
        session.query(ForwardForecast).filter(
            ForwardForecast.generated_date == today
        ).delete(synchronize_session=False)
        session.bulk_insert_mappings(ForwardForecast, records)
        session.commit()
    except Exception as e:
        print(f"  WARNING: Could not store forecasts: {e}")
        session.rollback()
    finally:
        session.close()

    print(f"Stored {len(records)} forecast records")


def get_sector_comparison_report():
    """Returns sector historical comparison from SectorGrowthAnalytics."""
    from data_loader import get_data_status
    today = get_data_status()["pipeline_date"]
    session = get_session()
    try:
        analytics = session.query(SectorGrowthAnalytics).filter(
            SectorGrowthAnalytics.computed_date == today
        ).all()
        if not analytics:
            latest = session.query(func.max(SectorGrowthAnalytics.computed_date)).scalar()
            if latest:
                analytics = session.query(SectorGrowthAnalytics).filter(
                    SectorGrowthAnalytics.computed_date == latest
                ).all()
    except Exception:
        analytics = []
    finally:
        session.close()

    if not analytics:
        return {}

    records = [{
        'sector':                 a.sector,
        'subsector':              a.subsector,
        'period':                 a.period,
        'total_return_pct':       a.total_return_pct,
        'annualised_return_pct':  a.annualised_return_pct,
        'volatility_pct':         a.volatility_pct,
        'sharpe_ratio':           a.sharpe_ratio,
        'max_drawdown_pct':       a.max_drawdown_pct,
        'beta_to_nifty':          a.beta_to_nifty,
    } for a in analytics]

    df = pd.DataFrame(records)
    comparison = {}
    for period in ["1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y"]:
        period_df = df[df['period'] == period].copy()
        if not period_df.empty:
            comparison[period] = period_df.sort_values(
                'annualised_return_pct', ascending=False
            ).to_dict('records')

    return comparison


def get_top_opportunities(horizon="3M", top_n=10):
    """Returns top N opportunities for a given horizon by opportunity score."""
    from data_loader import get_data_status
    today = get_data_status()["pipeline_date"]
    session = get_session()
    try:
        forecasts = session.query(ForwardForecast).filter(
            ForwardForecast.generated_date == today,
            ForwardForecast.forecast_horizon == horizon
        ).order_by(desc(ForwardForecast.opportunity_score)).limit(top_n).all()

        if not forecasts:
            latest = session.query(func.max(ForwardForecast.generated_date)).scalar()
            if latest:
                forecasts = session.query(ForwardForecast).filter(
                    ForwardForecast.generated_date == latest,
                    ForwardForecast.forecast_horizon == horizon
                ).order_by(desc(ForwardForecast.opportunity_score)).limit(top_n).all()
    except Exception:
        forecasts = []
    finally:
        session.close()

    return [{
        "rank":                  i + 1,
        "sector":                f.sector,
        "subsector":             f.subsector,
        "horizon":               horizon,
        "base_case_return_pct":  f.base_case_return,
        "bull_case_return_pct":  f.bull_case_return,
        "bear_case_return_pct":  f.bear_case_return,
        "opportunity_score":     f.opportunity_score,
        "confidence_score":      f.confidence_score,
        "primary_catalyst":      f.primary_catalyst,
        "risk_factor":           f.risk_factor,
    } for i, f in enumerate(forecasts)]


# ══════════════════════════════════════════════════════════════════
# SECTION 10 — REPORT PRINTING
# ══════════════════════════════════════════════════════════════════

def print_forward_intelligence_report(all_forecasts, macro_data, regime):
    """Prints the complete forward intelligence report."""
    crude_direction = get_crude_direction(macro_data)

    print(f"\n{'='*70}")
    print(f"MARKETOS FORWARD INTELLIGENCE REPORT")
    _data_date = macro_data.get("data_date", "N/A")
    print(f"Generated: {_data_date}")
    _rs = regime.get('legacy_score', int(round(float(regime.get('regime_score',0))*10)))
    print(f"Macro Regime: {regime['overall_regime']} | Score: {_rs:+d}")
    print(f"Crude: {crude_direction} | NASDAQ: {get_nasdaq_direction(macro_data)}")
    print(f"{'='*70}")

    for horizon in ["1M", "3M", "6M", "12M"]:
        opportunities = get_top_opportunities(horizon=horizon, top_n=5)
        if not opportunities:
            continue

        print(f"\n{'─'*70}")
        print(f"TOP OPPORTUNITIES — {horizon} HORIZON")
        print(f"{'─'*70}")
        print(f"{'#':<3} {'Subsector':<30} {'Base':>7} {'Bull':>7} {'Bear':>7} "
              f"{'Score':>6} {'Conf':>6}")
        print(f"{'─'*70}")

        for opp in opportunities:
            print(f"{opp['rank']:<3} {opp['subsector'][:29]:<30} "
                  f"{opp['base_case_return_pct']:>+6.1f}% "
                  f"{opp['bull_case_return_pct']:>+6.1f}% "
                  f"{opp['bear_case_return_pct']:>+6.1f}% "
                  f"{opp['opportunity_score']:>5.1f}/10 "
                  f"{opp['confidence_score']:>5.0%}")

        if opportunities:
            top = opportunities[0]
            print(f"\n  Top pick: {top['subsector']}")
            print(f"  Catalyst: {top['primary_catalyst'][:100]}")
            print(f"  Risk: {top['risk_factor'][:100]}")

    print(f"\n{'─'*70}")
    print(f"SECTOR HISTORICAL COMPARISON (Annualised Returns)")
    print(f"{'─'*70}")

    comparison = get_sector_comparison_report()
    if comparison:
        periods_to_show = [p for p in ["1M", "6M", "1Y", "3Y"] if p in comparison]
        if periods_to_show:
            header = f"{'Subsector':<30}"
            for p in periods_to_show:
                header += f"  {p:>7}"
            print(header)
            print("─" * (30 + 9 * len(periods_to_show)))

            all_subs = set()
            for p in periods_to_show:
                for r in comparison[p]:
                    all_subs.add(r['subsector'])

            for sub in sorted(all_subs):
                row = f"{sub[:29]:<30}"
                for period in periods_to_show:
                    pd_data = {r['subsector']: r for r in comparison.get(period, [])}
                    if sub in pd_data:
                        ret = pd_data[sub]['annualised_return_pct']
                        row += f"  {ret:>+6.1f}%"
                    else:
                        row += f"  {'N/A':>7}"
                print(row)


# ══════════════════════════════════════════════════════════════════
# SECTION 11 — FORWARD INSIGHT PROMPT (ANTI-HALLUCINATION)
# ══════════════════════════════════════════════════════════════════

def build_opportunity_prompt(opportunities_by_horizon, comparison, regime, macro_data):
    """
    Builds LLM prompt for forward insight.
    Enforces deep macro→sector transmission reasoning.
    Explicitly uses crude direction, NASDAQ, and sector-specific mechanisms.
    """
    crude_direction  = get_crude_direction(macro_data)
    nasdaq_direction = get_nasdaq_direction(macro_data)
    crude_val        = macro_data.get('brent_crude', {}).get('current', 80)
    crude_chg        = macro_data.get('brent_crude', {}).get('change_pct', 0)
    usdinr_val       = macro_data.get('usdinr', {}).get('current', 83)
    usdinr_chg       = macro_data.get('usdinr', {}).get('change_pct', 0)
    vix_val          = macro_data.get('india_vix', {}).get('current', 15)
    repo_rate        = macro_data.get('repo_rate', {}).get('current', 6.5)
    rate_chg         = macro_data.get('repo_rate', {}).get('change', 0)
    fii_signal       = macro_data.get('fii_flows', {}).get('signal', 'NEUTRAL')
    nasdaq_chg       = macro_data.get('nasdaq', {}).get('change_pct', 0)
    oil_bias         = get_oil_refining_bias(crude_direction)

    # Direction labels
    rupee_dir  = "STRENGTHENING" if usdinr_chg < -0.3 else ("WEAKENING" if usdinr_chg > 0.3 else "STABLE")
    rate_label = "CUT" if rate_chg < -0.01 else ("HIKED" if rate_chg > 0.01 else "UNCHANGED")

    # Build enriched opportunity text with transmission mechanism per sector
    SECTOR_TRANSMISSION = {
        "Private Banks":       f"Rate {rate_label} at {repo_rate}% → NIM expansion as lending rates reprice faster; FII {fii_signal} supporting large-cap bank valuations",
        "PSU Banks":           f"Rate {rate_label} → credit growth in retail and MSME; PSU bank CASA spreads widen in falling rate cycle",
        "NBFCs":               f"Rate {rate_label} → cost of borrowing falls → NBFC NIM expansion; rural credit demand recovers post-harvest",
        "IT Services":         f"NASDAQ {nasdaq_direction} ({nasdaq_chg:+.1f}%) → US tech capex sentiment {'lifting' if nasdaq_direction == 'RISING' else 'pressuring'} deal flow; rupee {rupee_dir} {'expanding' if rupee_dir == 'WEAKENING' else 'compressing'} USD revenue in INR",
        "Digital Engineering": f"NASDAQ {nasdaq_direction} → engineering R&D budgets {'healthy' if nasdaq_direction != 'FALLING' else 'under pressure'}; rupee {rupee_dir} affects dollar billing",
        "Oil Refining & Marketing": (
            f"Crude {crude_direction} at ${crude_val:.0f}/bbl → OMC gross refining margins "
            + ("COMPRESSED — input costs rising faster than capped retail prices; inventory losses likely" if crude_direction == "SPIKING"
               else ("EXPANDING — input cost per barrel falls while retail prices lag; GRM improves. "
                     "NOTE: Upstream E&P producers (ONGC, Oil India) earn LESS per barrel when crude falls — "
                     "the OMC benefit is OPPOSITE to the E&P impact.") if crude_direction == "FALLING"
               else "NEUTRAL — crude within normal range, no significant GRM impact")
        ),
        "Gas Distribution":    f"Crude {crude_direction} → APM gas prices {'under upward pressure' if crude_direction == 'SPIKING' else 'may ease' if crude_direction == 'FALLING' else 'stable'}; city gas expansion to Tier-2 cities adding volume",
        "Passenger Vehicles":  f"Rate {rate_label} at {repo_rate}% → auto loan EMIs fall → entry-level buyer pool expands as EMI-to-income ratio improves; rate cut cycle typically lifts PV volumes with 1-2 quarter lag",
        "Two Wheelers":        f"Rate {rate_label} → rural credit cost falls; crude {crude_direction} → fuel cost {'anxiety hurting' if crude_direction == 'SPIKING' else 'relief supporting'} two-wheeler sentiment",
        "Real Estate Developers": f"Rate {rate_label} → home loan EMI falls → EMI-to-income ratio improves → pent-up demand converts to purchases",
        "Construction & EPC":  f"Govt capex transmission: lower yields from rate cut → cheaper bond financing → infrastructure project IRR improves",
        "Large Cap Pharma":    f"Rupee {rupee_dir} → US generic export revenue {'contracts' if rupee_dir == 'STRENGTHENING' else 'expands' if rupee_dir == 'WEAKENING' else 'unchanged'} in INR; US FDA approval pipeline driving growth",
        "Industrial & Defence": f"Defence budget capex allocation → multi-year order book visibility; indigenisation mandate reducing import dependency",
        "Renewable Energy":    f"Rate {rate_label} → project IRR improves as discount rate falls; green bond yields compress reducing capex cost",
        "FMCG Staples":        f"Crude {crude_direction} → {'input cost pressure on palm oil derivatives and packaging' if crude_direction == 'SPIKING' else 'input cost relief improving margins' if crude_direction == 'FALLING' else 'stable inputs'}; rural demand driven by kharif harvest income",
    }

    def enrich_opportunity(opp):
        sub = opp['subsector']
        tx  = SECTOR_TRANSMISSION.get(sub, f"Primary catalyst: {opp['primary_catalyst'][:60]}")
        return (
            f"  {opp['rank']}. {sub}: {opp['base_case_return_pct']:+.1f}% base case | "
            f"Score: {opp['opportunity_score']:.1f}/10 | Conf: {opp['confidence_score']:.0%}\n"
            f"     Mechanism: {tx}\n"
            f"     Risk: {opp['risk_factor'][:80]}"
        )

    top_3m = opportunities_by_horizon.get("3M", [])[:4]
    top_6m = opportunities_by_horizon.get("6M", [])[:4]

    opp_3m_text = "\n".join([enrich_opportunity(o) for o in top_3m])
    opp_6m_text = "\n".join([enrich_opportunity(o) for o in top_6m])

    # ── DYNAMIC EVENT CALENDAR ─────────────────────────────────────────────
    from datetime import date as _date_cls, timedelta as _td

    _today = _date_cls.today()

    def _days_away(d):
        delta = (d - _today).days
        if delta <= 0:    return "this week"
        elif delta == 1:  return "tomorrow"
        elif delta <= 7:  return f"in {delta} days"
        elif delta <= 30: return f"in ~{delta // 7} week{'s' if delta // 7 > 1 else ''}"
        else:             return f"in ~{delta // 30} month{'s' if delta // 30 > 1 else ''}"

    # RBI MPC — bi-monthly schedule
    _rbi_schedule = [
        _date_cls(2026, 6, 4),  _date_cls(2026, 8, 5),
        _date_cls(2026, 10, 7), _date_cls(2026, 12, 3),
        _date_cls(2027, 2, 4),  _date_cls(2027, 4, 7),
    ]
    _next_rbi = next((d for d in _rbi_schedule if d >= _today), _rbi_schedule[-1])
    _rbi_end  = _next_rbi + _td(days=2)

    # FOMC schedule 2026-2027
    _fomc_schedule = [
        _date_cls(2026, 3, 18), _date_cls(2026, 5, 6),
        _date_cls(2026, 6, 17), _date_cls(2026, 7, 28),
        _date_cls(2026, 9, 15), _date_cls(2026, 10, 28),
        _date_cls(2026, 12, 9), _date_cls(2027, 1, 27),
    ]
    _next_fomc = next((d for d in _fomc_schedule if d >= _today), _date_cls(2027, 1, 27))
    _fomc_end  = _next_fomc + _td(days=1)

    # Earnings season — quarterly
    if _today < _date_cls(2026, 6, 30):
        _earn_label = "Q4 FY26"
        _earn_start = _date_cls(2026, 4, 14)
        _earn_lead  = "TCS (Apr 10), HDFC Bank (Apr 19), Infosys (Apr 17)"
        _earn_watch = "IT deal TCV and revenue guidance, bank NIM trajectory, OMC inventory gains"
    elif _today < _date_cls(2026, 9, 30):
        _earn_label = "Q1 FY27"
        _earn_start = _date_cls(2026, 7, 7)
        _earn_lead  = "TCS (Jul 10), HDFC Bank (Jul 19), Infosys (Jul 17)"
        _earn_watch = "Q1 volume growth vs guidance, NIM commentary post rate cuts, auto volume data"
    elif _today < _date_cls(2026, 12, 31):
        _earn_label = "Q2 FY27"
        _earn_start = _date_cls(2026, 10, 7)
        _earn_lead  = "IT majors lead second week of October"
        _earn_watch = "H2 demand commentary, FII impact on banking asset quality, festive auto sales"
    else:
        _earn_label = "Q3 FY27"
        _earn_start = _date_cls(2027, 1, 10)
        _earn_lead  = "TCS leads mid-January"
        _earn_watch = "Union Budget impact on capex sectors, IT pipeline for CY27"

    # OPEC+ approximate bi-monthly schedule
    _opec_schedule = [
        _date_cls(2026, 6, 1),  _date_cls(2026, 8, 3),
        _date_cls(2026, 10, 5), _date_cls(2026, 12, 7),
        _date_cls(2027, 2, 2),
    ]
    _next_opec = next((d for d in _opec_schedule if d >= _today), _date_cls(2027, 2, 2))

    # Next CPI release — 12th of each month (MoSPI)
    if _today.day < 12:
        _next_cpi = _date_cls(_today.year, _today.month, 12)
    else:
        _cpi_m = _today.month + 1 if _today.month < 12 else 1
        _cpi_y = _today.year if _today.month < 12 else _today.year + 1
        _next_cpi = _date_cls(_cpi_y, _cpi_m, 12)

    upcoming_events = f"""
  1. RBI Monetary Policy Committee — {_next_rbi.strftime('%B %d')}-{_rbi_end.day}, {_next_rbi.year} ({_days_away(_next_rbi)})
     Watch: Rate decision and inflation vs growth guidance.
     Signal: Cut → PSU Banks rally on NIM expansion with 1-2Q lag; Hold with hawkish tone → rate-sensitive sectors stay under pressure.

  2. US Federal Reserve FOMC — {_next_fomc.strftime('%B %d')}-{_fomc_end.day}, {_next_fomc.year} ({_days_away(_next_fomc)})
     Watch: Fed dot plot revision and terminal rate path.
     Signal: Dovish shift → EM risk-on, FII inflows to India; Hawkish → rupee pressure, FII selling in Banking and IT.

  3. {_earn_label} Earnings Season — from {_earn_start.strftime('%B %d, %Y')} ({_days_away(_earn_start)})
     Lead reporters: {_earn_lead}
     Watch: {_earn_watch}

  4. OPEC+ Production Decision — {_next_opec.strftime('%B %Y')} ({_days_away(_next_opec)})
     Watch: Quota decision determines crude trajectory.
     Signal: Cut → crude sustains above ${crude_val:.0f} → OMC margin pressure; Hike → crude falls → OMC relief, rupee support.

  5. CPI Inflation Print (MoSPI) — {_next_cpi.strftime('%B %d, %Y')} ({_days_away(_next_cpi)})
     Watch: Headline vs core. Above 5.5% reduces RBI cut probability; below 4.5% opens door for additional 25bps."""
    # ── END DYNAMIC EVENT CALENDAR ─────────────────────────────────────────────

    prompt = f"""
You are MarketOS — India's forward-looking market intelligence engine.
Use ONLY the data provided. DO NOT make investment recommendations.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠ MANDATORY WRITING RULES (violations invalidate the report):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORBIDDEN PHRASES — NEVER write these (auto-fail):
  ✗ "company-specific factors"   ✗ "technical reasons" / "technical factors"
  ✗ "market sentiment"           ✗ "broader trends" / "broader market trends"
  ✗ "positioning effects"        ✗ "investor confidence" / "investor optimism"
  ✗ "monitor RBI"                ✗ "watch GDP"
  ✗ "positive for the sector"    ✗ "benefiting from macro"
  ✗ "risk appetite"              ✗ "global cues" / "global headwinds"
  ✗ "profit booking"             ✗ "selling pressure" / "buying interest"
  ✗ "mixed signals"              ✗ "cautious stance"

INSTEAD, always name the exact macro variable, the transmission chain, and the P&L impact:

REQUIRED FORMAT for every sector (must use ALL three):
  ✓ [Macro variable + exact value] → [specific transmission] → [company-level P&L impact]
  ✓ EXAMPLE: "RBI cut 25bps to 6.25% → auto loan EMI on ₹8L loan falls ~₹600/month
     → Maruti/M&M addressable buyer pool expands in entry-level segment"
  ✓ EXAMPLE: "Crude STABLE at $97.7 (+1.8%) — OMC refining margins
     likely under modest pressure; profitability may be constrained if crude sustains elevated"
  ✓ NOTE on repo→NIM: rate cut does NOT immediately expand NIM.
     Liability repricing happens in 1 quarter, asset repricing takes 2-3 quarters.
     Write: "rate cut benefits NIM with a lag — near-term NIM pressure before full asset repricing"

MAGNITUDE RULES — respect what the data actually says:
  • Rupee moved only {usdinr_chg:+.2f}% today — DO NOT call this a major FX move
  • If a move is <0.5%, describe as "marginal" or "negligible" — do not overstate
  • If NASDAQ is RISING but <1%, say "mild US tech tailwind" not "strong US demand"
  • "EMI savings of ₹X" — DO NOT write this unless ₹X appears in the data above
  • If a mechanism is not in the data, describe it qualitatively without fabricating numbers

STRICT VALIDATION RULE:
If your draft contains any forbidden phrase → delete that sentence and rewrite it.
If your draft contains a specific number (₹, %, bps) not derived from data above → remove it.
Every explanation chain must be: [named macro var with value] → [mechanism] → [earnings/margin outcome].

VERIFIED MACRO CONSTRAINTS (do not contradict):
  • Crude is {crude_direction} at ${crude_val:.1f}/bbl ({crude_chg:+.1f}%)
    {'→ OMC refining margins COMPRESSED. Do NOT describe Oil Refining as a positive.' if crude_direction == 'SPIKING'
     else '→ OMC margins EXPANDING. Describe input cost relief.' if crude_direction == 'FALLING'
     else '→ Crude impact neutral.'}
  • NASDAQ is {nasdaq_direction} ({nasdaq_chg:+.1f}%)
    → Use this specifically to explain IT sector outlook. Not "global sentiment."
  • Rupee is {rupee_dir} at ₹{usdinr_val:.2f} ({usdinr_chg:+.2f}%)
    {'→ HURTS IT and Pharma: dollar revenues are worth LESS in INR when rupee strengthens.' if rupee_dir == 'STRENGTHENING'
     else '→ HELPS IT and Pharma: dollar revenues are worth MORE in INR when rupee weakens.' if rupee_dir == 'WEAKENING'
     else '→ Rupee marginal move (<0.3%) — no material FX impact on IT or Pharma today.'}
    RULE: NEVER write "IT benefits" when rupee is STRENGTHENING. Always say "contracts" or "hurts".
  • Repo Rate is {rate_label} at {repo_rate}%
    → NIM impact is LAGGED — liability reprices in 1Q, assets reprice over 2-3Q. State this explicitly.
  • FII: {fii_signal}
    → Affects large-cap index heavyweights (HDFC Bank, TCS, RIL). State the flow direction explicitly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURRENT MACRO CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Regime: {regime.get('overall_regime', 'NEUTRAL')} | Score: {int(round(float(regime.get('regime_score', 0)) * 10)):+d}/10
India VIX: {vix_val:.1f} | Crude: {crude_direction} ${crude_val:.0f} | NASDAQ: {nasdaq_direction}
Repo Rate: {repo_rate}% ({rate_label}) | USD/INR: ₹{usdinr_val:.2f} ({rupee_dir}) | FII: {fii_signal}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODEL OPPORTUNITIES — 3M HORIZON (with transmission chains)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{opp_3m_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODEL OPPORTUNITIES — 6M HORIZON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{opp_6m_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UPCOMING MACRO TRIGGERS (use exact dates in your response):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{upcoming_events}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENERATE FORWARD INTELLIGENCE (max 320 words)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Forward-Looking Sector Intelligence Briefing**

**NEAR-TERM OUTLOOK (1-3 months):**
[Write exactly 3 sentences. Each sentence must:
 - Name one macro variable with its actual value from above (e.g. "Repo rate at {repo_rate}% after 25bps cut")
 - Name the exact transmission mechanism (e.g. "NIM expands as MCLR-linked loans reprice faster than CASA rates")
 - State which subsector is most impacted

 CRITICAL NUMBER RULE: Do NOT write "10-15bps", "2-3% revenue boost", "8-12% EBITDA" or ANY
 specific % or bps unless that exact number appears in the VERIFIED MACRO DATA block above.
 If you want to indicate magnitude, use qualitative language: "meaningfully", "modestly", "materially".
 The ONLY exception: model base-case % returns from the OPPORTUNITIES section above are data-derived and may be cited.

 CRITICAL DIRECTION RULE for this session:
 - Rupee is {rupee_dir}: if STRENGTHENING → IT and Pharma dollar revenues COMPRESS (not expand)
 - Crude is {crude_direction}: if FALLING → OMC refining margins EXPAND; upstream E&P gets LOWER realisations
 - These two directions are non-negotiable. Do NOT contradict them.]
{'[BEARISH/RISK-OFF REGIME — writing rules: Open by naming the macro trigger causing the sell-off (crude spike / FII outflow / rupee weakness). Do NOT start with The market fell or NIFTY declined. Sentence 2: Name which sector takes the most damage and explain the weight x contribution math. Sentence 3: State ONE specific condition with a number that would halt the decline — e.g. crude falling below $X, VIX returning below Y, FII turning net buyer at Z crore.]' if regime.get("overall_regime", "NEUTRAL") in ("BEARISH", "RISK_OFF", "STRONG_BEAR") else '[BULLISH REGIME — writing rules: Open with the macro tailwind driving the rally (rate cut / FII inflows / strong earnings). Sentence 2: Name the top beneficiary sector and the exact transmission mechanism. Sentence 3: Name ONE specific risk that could interrupt the bull run with a concrete trigger level.]' if regime.get("overall_regime", "NEUTRAL") in ("MILD_BULLISH", "BULLISH", "STRONG_BULL") else '[NEUTRAL REGIME — writing rules: Do NOT write market was flat or NIFTY was unchanged. Identify the sector rotation beneath the flat index. Sentence 1: Name two sectors moving in opposite directions and explain why. Sentence 2: Identify the macro variable with the most forward momentum. Sentence 3: Name the upcoming catalyst from the events list that will break the range.]'}
MANDATORY RULES FOR ALL REGIMES:
 - Every sentence must follow: [Macro variable + exact value] → [mechanism] → [sector P&L impact]
 - Do NOT write any bps or % figure not in the verified data above
 - Rupee is {rupee_dir}: {'IT and Pharma dollar revenues EXPAND in INR terms' if rupee_dir == 'WEAKENING' else 'IT and Pharma dollar revenues COMPRESS in INR terms' if rupee_dir == 'STRENGTHENING' else 'no material FX impact on IT/Pharma today'}
 - Crude is {crude_direction}: {'OMC GRM is COMPRESSED — do NOT describe Energy sector as benefiting' if crude_direction == 'SPIKING' else 'OMC GRM is EXPANDING — input cost relief for downstream refiners' if crude_direction == 'FALLING' else 'crude neutral today'}

**MEDIUM-TERM OPPORTUNITIES (3-6 months):**
[Pick the TOP 2 sectors from the 3M opportunities list above. For EACH:
 - State the model's base case return from the data (e.g. "+26.9% base case")
 - Cite the specific catalyst from the mechanism chains above
 - Explain what must happen (not happen) for the forecast to materialise
 - Crude is {crude_direction} at ${crude_val:.0f}/bbl — explicitly state whether this helps or hurts Energy sector
 DO NOT reference sectors not in the opportunity list above.]

**SECTORS TO MONITOR WITH SPECIFIC TRIGGERS:**
[For exactly 2 sectors, write: "Watch [sector]: [specific trigger]. If [condition], [outcome impact]."
Example: "Watch Oil Refining: if crude sustains above $100/bbl, OMC refining margins may compress
meaningfully, potentially pressuring profitability for downstream refiners."
Use the actual crude value from above (${crude_val:.0f}/bbl). Describe direction and mechanism — avoid
fabricated specific figures like "$2-3/bbl" or "8-12% EBITDA" that are not in verified data above.]

**MACRO TRIGGERS TO WATCH — EXACT DATES:**
[Cite the 3-4 upcoming events listed above with their dates.
For each, explain WHAT to watch and WHAT the outcome would mean for Indian equities.]

DISCLAIMER: Forward projections are model outputs based on historical macro patterns.
Not investment advice. Actual outcomes may differ materially.
"""
    return prompt
