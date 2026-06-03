# alpha_engine.py
# MarketOS — Alpha Signal Engine  [UPGRADED v3]
#
# SECTION 9 UPGRADES:
#   1. Macro alignment scaled to [0.4, 1.0] — floor raised from 0.3 to 0.4
#      MACRO_DIVERGENT → 0.40 (was 0.30)
#      NEUTRAL         → 0.65
#      MACRO_ALIGNED   → 1.00
#   2. Alpha exclusion threshold raised: 0.5 → 0.6
#      Stronger signal filter — only high-conviction sectors pass
#   3. Composite weights unchanged:
#        alpha = 0.4*momentum + 0.2*mean_reversion + 0.2*vol + 0.2*macro
#
# Usage:
#   from alpha_engine import compute_alpha_scores
#   alpha = compute_alpha_scores(moderated_output, macro_data, regime)

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from database import get_session, DailyPrice
from classification import MARKET_CLASSIFICATION
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────
WEIGHTS = {
    "momentum":       0.30,
    "mean_reversion": 0.15,
    "vol_breakout":   0.15,
    "macro_align":    0.20,
    "sentiment":      0.20,
}
LOOKBACK_LONG  = 90
MOMENTUM_SHORT = 20
MOMENTUM_LONG  = 60
MEAN_REV_WIN   = 50
VOL_SHORT_WIN  = 10
VOL_LONG_WIN   = 60

# SECTION 9: Lowered back from 0.60 to 0.52 because 0.60 was excluding 85% of the market.
ALPHA_EXCLUSION_THRESHOLD = 0.52

# SECTION 9: macro floor raised from 0.30 → 0.40
MACRO_ALIGNMENT_SCALE = {
    "MACRO_ALIGNED":   1.00,
    "NEUTRAL":         0.65,
    "MACRO_DIVERGENT": 0.40,   # was 0.30 — now [0.4, 1.0] range
}


# ─────────────────────────────────────────────────────────────────
# SECTION 1 — PRICE DATA LOADER
# ─────────────────────────────────────────────────────────────────

def _load_sector_returns(lookback_days: int = LOOKBACK_LONG) -> pd.DataFrame:
    """Returns a date × subsector DataFrame of weighted daily returns."""
    from pipeline_utils import get_pipeline_date
    pipeline_dt = get_pipeline_date()
    since   = pipeline_dt - timedelta(days=lookback_days + 10)

    session = get_session()
    try:
        rows = session.query(DailyPrice).filter(
            DailyPrice.date >= since,
            DailyPrice.daily_return.isnot(None)
        ).all()
    except Exception:
        rows = []
    finally:
        session.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "date":         pd.Timestamp(r.date),
        "subsector":    r.subsector,
        "daily_return": float(r.daily_return or 0.0),
        "nifty_weight": float(r.nifty_weight or 0.001),
    } for r in rows])

    def _wm(g):
        w = g["nifty_weight"].sum()
        return (g["daily_return"] * g["nifty_weight"]).sum() / w if w > 0 else g["daily_return"].mean()

    pivot = (
        df.groupby(["date", "subsector"])
        .apply(_wm)
        .unstack("subsector")
        .sort_index()
    )
    return pivot


# ─────────────────────────────────────────────────────────────────
# SECTION 2 — INDIVIDUAL SIGNALS
# ─────────────────────────────────────────────────────────────────

def _signal_momentum(price_df: pd.DataFrame) -> pd.Series:
    """Momentum: 0.6×20d + 0.4×60d cumulative returns."""
    scores = {}
    for col in price_df.columns:
        series = price_df[col].dropna()
        if len(series) >= MOMENTUM_LONG:
            ret_20d = float((1 + series.iloc[-MOMENTUM_SHORT:]).prod() - 1) * 100
            ret_60d = float((1 + series.iloc[-MOMENTUM_LONG:]).prod() - 1) * 100
            scores[col] = 0.6 * ret_20d + 0.4 * ret_60d
        elif len(series) >= MOMENTUM_SHORT:
            scores[col] = float((1 + series.iloc[-MOMENTUM_SHORT:]).prod() - 1) * 100
        else:
            scores[col] = 0.0
    return pd.Series(scores)


def _signal_mean_reversion(price_df: pd.DataFrame) -> pd.Series:
    """Mean reversion: sectors below 50-day MA get positive signal."""
    scores = {}
    for col in price_df.columns:
        series = price_df[col].dropna()
        if len(series) >= MEAN_REV_WIN:
            cum_price = (1 + series / 100).cumprod() * 100
            ma_50     = float(cum_price.rolling(MEAN_REV_WIN).mean().iloc[-1])
            curr      = float(cum_price.iloc[-1])
            deviation = (ma_50 - curr) / ma_50 * 100
            scores[col] = deviation
        else:
            scores[col] = 0.0
    return pd.Series(scores)


def _signal_volatility_breakout(price_df: pd.DataFrame) -> pd.Series:
    """Volatility signal: short_vol / long_vol ratio."""
    scores = {}
    for col in price_df.columns:
        series = price_df[col].dropna()
        if len(series) >= VOL_LONG_WIN:
            vol_short = float(series.iloc[-VOL_SHORT_WIN:].std() * np.sqrt(252)) if len(series) >= VOL_SHORT_WIN else 0.0
            vol_long  = float(series.iloc[-VOL_LONG_WIN:].std() * np.sqrt(252))
            ratio     = vol_short / vol_long if vol_long > 0 else 1.0
            scores[col] = (ratio - 1.0) * 100
        else:
            scores[col] = 0.0
    return pd.Series(scores)


def _signal_sentiment(moderated_output: dict) -> pd.Series:
    """Fetches live LLM sentiment per sector and maps to subsectors."""
    try:
        from sentiment_engine import get_live_sentiment_all_sectors
        sentiment_data = get_live_sentiment_all_sectors(force_refresh=False)
    except Exception:
        sentiment_data = {}

    sub_scores = {}
    for sector_name, sec_data in MARKET_CLASSIFICATION.items():
        # Score is -1.0 to 1.0, scale it to 0.0 to 100.0 (where 0.0 is neutral 50)
        raw_score = sentiment_data.get(sector_name, {}).get("sentiment_score", 0.0)
        scaled_score = (raw_score + 1.0) / 2.0 * 100.0
        
        for sub_name in sec_data["subsectors"]:
            sub_scores[sub_name] = scaled_score
    return pd.Series(sub_scores)

def _signal_macro_alignment(moderated_output: dict) -> pd.Series:
    """
    SECTION 7 FIX: macro ∈ [0.4, 1.0] with REAL VARIATION per sector.
    Reads macro_score from moderated output (set by _compute_scaled_macro_score
    in macro_engine). Falls back to MACRO_ALIGNMENT_SCALE for legacy paths.
    Prevents flat 1.0 for all sectors.
    """
    sector_align = {}
    for sector_name, data in moderated_output.get("moderated_sectors", {}).items():
        # Prefer pre-computed macro_score (varied, data-driven)
        if "macro_score" in data:
            sector_align[sector_name] = float(data["macro_score"])
        else:
            # Legacy fallback: string alignment → scale
            align = data.get("macro_alignment", "NEUTRAL")
            sector_align[sector_name] = MACRO_ALIGNMENT_SCALE.get(align, 0.65)

    sub_scores = {}
    for sector_name, sec_data in MARKET_CLASSIFICATION.items():
        align_score = sector_align.get(sector_name, 0.65)
        for sub_name in sec_data["subsectors"]:
            sub_scores[sub_name] = align_score * 100
    return pd.Series(sub_scores)


# ─────────────────────────────────────────────────────────────────
# NORMALISATION
# ─────────────────────────────────────────────────────────────────

def _normalise(series: pd.Series) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx - mn < 1e-8:
        return pd.Series(0.5, index=series.index)
    return (series - mn) / (mx - mn)


# ─────────────────────────────────────────────────────────────────
# COMPOSITE ALPHA SCORE
# ─────────────────────────────────────────────────────────────────

def compute_alpha_scores(
    moderated_output: dict,
    macro_data:       dict,
    regime:           dict,
    force_run:        bool = False,
) -> dict:
    """
    SECTION 9 UPGRADES:
    - macro ∈ [0.4, 1.0]
    - excluded threshold = 0.6 (raised from 0.5)
    - alpha = 0.4*momentum + 0.2*mean_reversion + 0.2*vol + 0.2*macro

    MARKET STATE AWARENESS: On non-trading days, momentum and volatility
    signals are suppressed (zeroed) to avoid misleading scores from
    stale or incomplete intraday prices. Only macro alignment is kept.
    """
    print("\n=== ALPHA SIGNAL ENGINE [v3 — macro∈[0.4,1.0], thresh=0.6] ===")

    # TASK 4: STRICT VALIDATION — fail fast on invalid NIFTY data
    if not macro_data.get("nifty", {}).get("is_valid", False) and not force_run:
        raise ValueError("CRITICAL: Invalid NIFTY data — aborting alpha scoring run")

    # ── MARKET STATE GATE ─────────────────────────────────────────
    try:
        from market_calendar import get_market_status
        _mkt = get_market_status()
    except ImportError:
        _mkt = {"is_trading_day": True, "engine_mode": "FULL",
                "nifty_is_valid": True, "close_reason": ""}

    if force_run:
        _market_open = True
    else:
        _market_open = _mkt.get("is_trading_day", True) and _mkt.get("nifty_is_valid", True)

    if not _market_open:
        print(f"  ⚠ Market closed ({_mkt.get('close_reason', 'non-trading day')}) "
              f"— momentum & volatility signals SUPPRESSED")
        print("     Alpha scoring from macro alignment only (price-independent signals)")

    price_df = _load_sector_returns()
    if price_df.empty:
        print("  No price data — alpha scores defaulted")
        return {}

    mom_raw = _signal_momentum(price_df)
    rev_raw = _signal_mean_reversion(price_df)
    vol_raw = _signal_volatility_breakout(price_df)
    mac_raw = _signal_macro_alignment(moderated_output)
    sen_raw = _signal_sentiment(moderated_output)

    # MARKET STATE: on closed days, zero price-driven signals so alpha
    # is driven only by the price-independent macro alignment component.
    if not _market_open:
        mom_raw = pd.Series(0.0, index=mom_raw.index)
        rev_raw = pd.Series(0.0, index=rev_raw.index)
        vol_raw = pd.Series(0.0, index=vol_raw.index)
        print("  ℹ Momentum / mean-reversion / vol signals zeroed (non-trading day)")

    all_subs = set(mom_raw.index) | set(rev_raw.index) | set(vol_raw.index) | set(mac_raw.index) | set(sen_raw.index)
    mom_raw  = mom_raw.reindex(all_subs).fillna(0.0)
    rev_raw  = rev_raw.reindex(all_subs).fillna(0.0)
    vol_raw  = vol_raw.reindex(all_subs).fillna(0.0)
    mac_raw  = mac_raw.reindex(all_subs).fillna(65.0)
    sen_raw  = sen_raw.reindex(all_subs).fillna(50.0)

    mom_norm = _normalise(mom_raw)
    rev_norm = _normalise(rev_raw)
    vol_norm = _normalise(vol_raw)
    # FIX: Do not normalize macro scores because normalization maps flat arrays (e.g., all 65.0) 
    # to 0.5, destroying the macro alignment value. Just divide by 100.
    mac_norm = mac_raw / 100.0

    alpha = (
        WEIGHTS["momentum"]       * mom_norm +
        WEIGHTS["mean_reversion"] * rev_norm +
        WEIGHTS["vol_breakout"]   * vol_norm +
        WEIGHTS["macro_align"]    * mac_norm
    )

    alpha_sorted = alpha.sort_values(ascending=False)
    rank_map     = {sub: int(i + 1) for i, sub in enumerate(alpha_sorted.index)}

    # ── REGIME-AWARE THRESHOLD ────────────────────────────────────
    _regime_label = regime.get("overall_regime", "NEUTRAL") if isinstance(regime, dict) else "NEUTRAL"
    if _regime_label in ("BEARISH", "RISK_OFF", "STRONG_BEAR"):
        _active_threshold = 0.52
    elif _regime_label in ("MILD_BEARISH",):
        _active_threshold = 0.55
    else:
        _active_threshold = ALPHA_EXCLUSION_THRESHOLD
    # ── END REGIME-AWARE THRESHOLD ────────────────────────────────

    result       = {}
    excluded_cnt = 0
    for sub in all_subs:
        score    = float(alpha.get(sub, 0.5))
        excluded = score < _active_threshold
        if excluded:
            excluded_cnt += 1
        result[sub] = {
            "alpha_score":      round(score, 4),
            "momentum":         round(float(mom_norm.get(sub, 0.5)), 4),
            "mean_reversion":   round(float(rev_norm.get(sub, 0.5)), 4),
            "vol_breakout":     round(float(vol_norm.get(sub, 0.5)), 4),
            "macro_alignment":  round(float(mac_norm.get(sub, 0.5)), 4),
            "raw_momentum_pct": round(float(mom_raw.get(sub, 0.0)), 2),
            "signal_rank":      rank_map.get(sub, len(all_subs)),
            "excluded":         excluded,
            "exclude_reason":   "alpha_below_threshold" if excluded else "",
        }

    print(f"\n  {'Rank':<5} {'Subsector':<35} {'Alpha':>7} {'Mom':>6} {'MRev':>6} {'Vol':>6} {'Mac':>6} {'Status'}")
    print(f"  {'─'*80}")
    for sub in list(alpha_sorted.index)[:10]:
        r      = result[sub]
        status = "PASS" if not r["excluded"] else "EXCL"
        print(f"  {r['signal_rank']:<5} {sub[:34]:<35} "
              f"{r['alpha_score']:>6.3f} {r['momentum']:>5.3f} "
              f"{r['mean_reversion']:>5.3f} {r['vol_breakout']:>5.3f} "
              f"{r['macro_alignment']:>5.3f}  {status}")

    total = len(all_subs)
    print(f"\n  Scored: {total} | Excluded (<{_active_threshold:.2f}, regime={_regime_label}): {excluded_cnt} | Active: {total - excluded_cnt}")
    return result


if __name__ == "__main__":
    print("Alpha Engine v3 — run via main.py --daily")
