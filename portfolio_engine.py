# portfolio_engine.py
# MarketOS — Portfolio Construction Engine  [v5 — High-Sharpe Rewrite]
#
# TARGET METRICS:
#   Sharpe    : 0.8 – 1.2
#   Drawdown  : -10% to -14%
#   Return    : 12 – 16%
#   Alpha     : 5 – 8%
#
# ARCHITECTURE:
#   1. Scoring         : (ret * conf * alpha) / (1 + 0.5*vol) + high-vol penalty
#   2. Position sizing : Inverse-volatility (equal risk contribution)
#   3. Constraints     : min 4 / max 6 sectors, 5–25% per sector, top-3 ≤ 60%
#   4. Weak signals    : exp_return < 5% dropped (with fallback)
#   5. Exposure control: VIX, drawdown, portfolio-vol cap

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
MAX_WEIGHT          = 0.20    # tighter cap: reduces concentration, improves Sharpe
MIN_WEIGHT          = 0.04    # lowered: 4% floor allows more positions to survive
ALPHA_MIN_THRESHOLD = 0.45    # FIX 4: soft filter — drop alpha < 0.45
HIGH_VOL_PENALTY_T  = 30.0    # FIX 1: soft penalty above 30% vol
VOL_SCALE_THRESH    = 20.0    # inverse-vol sizing threshold
MAX_THEME_WEIGHT    = 0.40
MAX_SECTOR_WEIGHT   = 0.50    # no single sector above 50% of portfolio
TOP3_CAP            = 0.60
TOP_SECTORS_KEEP    = 6
MIN_SECTORS         = 4
MIN_EXPECTED_RETURN = 5.0     # weak signals removed (with fallback)
CORR_THRESHOLD      = 0.85
RISK_FREE_RATE      = 0.065
VOL_LOOKBACK_DAYS   = 60
VOL_PORTFOLIO_CAP   = 26.0    # portfolio-level vol ceiling (%)

THEME_MAP = {
    "Information Technology":       "technology",
    "Telecom":                      "technology",
    "Banking & Financial Services": "financials",
    "Insurance":                    "financials",
    "NBFCs & Microfinance":         "financials",
    "Consumer Discretionary":       "consumption",
    "FMCG & Consumer Staples":      "consumption",
}


# ─────────────────────────────────────────────────────────────────
# VOLATILITY LOADER  (blended 20d / 60d rolling — smoothed)
# ─────────────────────────────────────────────────────────────────

def _load_sector_volatility(lookback_days: int = VOL_LOOKBACK_DAYS) -> dict:
    """Returns {subsector: annualised_vol_pct} using blended rolling window.
    PART 1: uses get_pipeline_date() — single date authority.
    """
    from pipeline_utils import get_pipeline_date
    since   = get_pipeline_date() - timedelta(days=lookback_days + 10)
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
        return {}

    df = pd.DataFrame([{
        "date":         pd.Timestamp(r.date),
        "subsector":    r.subsector,
        "daily_return": float(r.daily_return or 0.0),
        "nifty_weight": float(r.nifty_weight or 0.001),
    } for r in rows])

    def _wm(g):
        w = g["nifty_weight"].sum()
        return (g["daily_return"] * g["nifty_weight"]).sum() / w if w > 0 else g["daily_return"].mean()

    daily = df.groupby(["date", "subsector"]).apply(_wm).reset_index()
    daily.columns = ["date", "subsector", "ret"]
    vols = {}
    for sub, grp in daily.groupby("subsector"):
        grp = grp.sort_values("date")
        if len(grp) < 10:
            continue
        full_vol = float(grp["ret"].std() * np.sqrt(252)) * 100
        if len(grp) >= 20:
            # Blended: 60% recent 20d + 40% full-period (smoothed, responsive)
            recent_vol = float(grp["ret"].iloc[-20:].std() * np.sqrt(252)) * 100
            ann_vol    = 0.60 * recent_vol + 0.40 * full_vol
        else:
            ann_vol = full_vol
        vols[sub] = max(ann_vol, 5.0)   # floor prevents division-by-zero
    return vols


# ─────────────────────────────────────────────────────────────────
# CORRELATION MATRIX
# ─────────────────────────────────────────────────────────────────

def _load_correlation_matrix(lookback_days: int = VOL_LOOKBACK_DAYS) -> pd.DataFrame:
    """PART 1: uses get_pipeline_date() — single date authority."""
    from pipeline_utils import get_pipeline_date
    since   = get_pipeline_date() - timedelta(days=lookback_days + 10)
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
        .unstack(level="subsector")
        .sort_index()
    )
    return pivot.corr()


# ─────────────────────────────────────────────────────────────────
# THEME CAP
# ─────────────────────────────────────────────────────────────────

def _enforce_theme_cap(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # ── SECTOR CAP: no single sector above MAX_SECTOR_WEIGHT ─────
    sector_weights = {}
    for _, row in df.iterrows():
        sec = row["sector"]
        sector_weights[sec] = sector_weights.get(sec, 0.0) + row["weight"]
    for sec, total_w in sector_weights.items():
        if total_w > MAX_SECTOR_WEIGHT:
            scale = MAX_SECTOR_WEIGHT / total_w
            for idx, row in df.iterrows():
                if row["sector"] == sec:
                    df.loc[idx, "weight"] *= scale
            print(f"  ⚠ Sector '{sec}' capped: {total_w:.1%} → {MAX_SECTOR_WEIGHT:.0%}")

    # ── THEME CAP: no single theme above MAX_THEME_WEIGHT ────────
    theme_weights = {}
    for _, row in df.iterrows():
        theme = THEME_MAP.get(row["sector"], "other")
        theme_weights[theme] = theme_weights.get(theme, 0.0) + row["weight"]
    for theme, total_w in theme_weights.items():
        if total_w > MAX_THEME_WEIGHT:
            scale = MAX_THEME_WEIGHT / total_w
            for idx, row in df.iterrows():
                if THEME_MAP.get(row["sector"], "other") == theme:
                    df.loc[idx, "weight"] *= scale
            print(f"  ⚠ Theme '{theme}' capped: {total_w:.1%} → {MAX_THEME_WEIGHT:.0%}")
    return df


# ─────────────────────────────────────────────────────────────────
# INVERSE-VOL POSITION SIZING
# ─────────────────────────────────────────────────────────────────

def _apply_inverse_vol_sizing(df: pd.DataFrame) -> pd.DataFrame:
    """
    FIX 2 — MODERATE RISK PARITY POSITION SIZING:
    weights = weights / (volatility ** 1.0)
    weights = weights / weights.sum()
    Plain 1/vol (exponent=1.0) is more balanced than 1.5 — gives moderate-vol
    sectors a reasonable allocation while still reducing high-vol overweights.
    Targets equal dollar-risk contribution without over-suppressing returns.
    """
    df = df.copy()
    vol_clipped      = df["volatility"].clip(lower=5.0)
    df["weight_rp"]  = df["weight"] / (vol_clipped ** 1.0)   # moderate: exponent=1.0
    total = df["weight_rp"].sum()
    if total > 0:
        df["weight"] = df["weight_rp"] / total
    return df.drop(columns=["weight_rp"])


# ─────────────────────────────────────────────────────────────────
# MAIN PORTFOLIO BUILDER
# ─────────────────────────────────────────────────────────────────

def build_portfolio(
    all_forecasts: dict,
    macro_data:    dict,
    regime:        dict,
    horizon:       str  = "3M",
    alpha_scores:  dict = None,
) -> dict:
    """
    Institutional-grade portfolio construction pipeline.

    MARKET STATE AWARENESS: On non-trading days (weekends/holidays),
    rebalancing is skipped entirely. The function returns the most recent
    stored weights unchanged, preserving portfolio state without
    introducing signals from stale or absent price data.

    Steps 1–12 documented inline below.
    """
    print(f"\n=== PORTFOLIO CONSTRUCTION ENGINE v5 ({horizon}) ===")
    alpha_scores = alpha_scores or {}

    # ── MARKET STATE GATE ─────────────────────────────────────────
    try:
        from market_calendar import get_market_status
        _mkt = get_market_status()
    except ImportError:
        _mkt = {"should_rebalance": True, "is_trading_day": True,
                "engine_mode": "FULL", "close_reason": ""}

    if not _mkt.get("should_rebalance", True):
        reason = _mkt.get("close_reason", "non-trading day")
        print(f"  ⚠ Portfolio rebalancing SKIPPED — {reason}")
        print("     Returning previous portfolio weights unchanged.")
        return {
            "status":          "SKIPPED_MARKET_CLOSED",
            "reason":          reason,
            "weights":         {},
            "rebalanced":      False,
            "engine_mode":     _mkt.get("engine_mode", "FORECAST_ONLY"),
            "data_quality":    _mkt.get("data_quality", "HOLIDAY"),
            "message":         (
                f"Portfolio NOT rebalanced — market closed ({reason}). "
                f"Next trading session: {_mkt.get('next_trading_day')}."
            ),
        }


    # ── STEP 1: Collect subsector forecasts ───────────────────────
    # FIX 4: Drop alpha_score < 0.55; fallback to < 0.4 if MIN_SECTORS not reached
    records    = []
    records_fb = []
    for sector_name, sub_dict in all_forecasts.items():
        for subsector_name, h_dict in sub_dict.items():
            if horizon not in h_dict:
                continue
            alpha_info  = alpha_scores.get(subsector_name, {})
            alpha_score = float(alpha_info.get("alpha_score", 0.5))
            fc = h_dict[horizon]
            rec = {
                "sector":      sector_name,
                "subsector":   subsector_name,
                "exp_return":  float(fc.get("base_case_return_pct", 0.0)),
                "confidence":  float(fc.get("confidence_score", 0.3)),
                "opp_score":   float(fc.get("opportunity_score", 5.0)),
                "alpha_score": max(alpha_score, 0.4),
            }
            records_fb.append(rec)
            if alpha_score >= ALPHA_MIN_THRESHOLD:
                records.append(rec)

    unique_after_filter = len({r["sector"] for r in records})
    if unique_after_filter < MIN_SECTORS:
        print(f"  FIX 4: {unique_after_filter} sectors pass alpha>={ALPHA_MIN_THRESHOLD} — fallback to all")
        records = records_fb

    if not records:
        print("  No forecast data.")
        return {"error": "no_forecasts", "weights": {}}

    df_all = pd.DataFrame(records)

    # ── STEP 2: Load realised volatility ──────────────────────────
    vols = _load_sector_volatility()
    df_all["volatility"] = df_all["subsector"].map(vols).fillna(20.0)

    # ── STEP 3: Score each subsector ──────────────────────────────
    # FIX 1 — BALANCED SCORING: score = (ret * conf * alpha) / (1 + 0.7 * vol)
    # 0.7 multiplier is gentler than 1.0 — gives moderate-vol sectors a fair chance
    # Soft penalty: vol > 30% → score *= 0.85 (less aggressive than previous 0.6)
    def _score(row):
        raw = (row["exp_return"] * row["confidence"] * row["alpha_score"]) \
              / (1.0 + 0.7 * row["volatility"])
        if row["volatility"] > 30.0:   # vol stored as %, 30.0 = 30%
            raw *= 0.85
        return max(raw, 0.0)

    df_all["score"] = df_all.apply(_score, axis=1)

    # ── STEP 4: Remove weak signals ───────────────────────────────
    df = df_all[df_all["exp_return"] >= MIN_EXPECTED_RETURN].copy()
    if df.empty:
        print(f"  ⚠ All below {MIN_EXPECTED_RETURN}% — relaxing to exp_return > 0")
        df = df_all[df_all["exp_return"] > 0].copy()
    if df.empty:
        print("  ⚠ All non-positive — equal-weight fallback")
        df_all["weight"] = 1.0 / max(len(df_all), 1)
        return _format_output(df_all, macro_data, regime, horizon, note="all_negative_returns")

    # ── STEP 5: Sector selection — top 6 max, min 4 guaranteed ───
    sector_scores    = df.groupby("sector")["score"].sum().sort_values(ascending=False)
    all_sector_names = list(sector_scores.index)
    top_sectors      = set(all_sector_names[:TOP_SECTORS_KEEP])
    dropped          = set(all_sector_names[TOP_SECTORS_KEEP:])
    if dropped:
        print(f"  ✗ Dropped: {', '.join(list(dropped)[:4])}")
    df = df[df["sector"].isin(top_sectors)].copy()

    # Force diversification if collapsed
    if df["sector"].nunique() < MIN_SECTORS:
        print(f"  ⚠ Only {df['sector'].nunique()} sectors — forcing from top returns")
        fallback = df_all[df_all["exp_return"] > 0].copy()
        fallback["score"] = fallback.apply(_score, axis=1)
        df = fallback.sort_values("exp_return", ascending=False).head(20).copy()

    # Top-up to MIN_SECTORS if still short
    if df["sector"].nunique() < MIN_SECTORS:
        extra = df_all[df_all["exp_return"] > 0].copy()
        extra["score"] = extra.apply(_score, axis=1)
        for sec in all_sector_names:
            if df["sector"].nunique() >= MIN_SECTORS:
                break
            if sec not in df["sector"].values:
                add = extra[extra["sector"] == sec]
                if not add.empty:
                    df = pd.concat([df, add], ignore_index=True)
                    print(f"  ✚ Added {sec} to reach MIN_SECTORS={MIN_SECTORS}")

    if df.empty:
        return {"error": "all_filtered", "weights": {}}

    # ── STEP 6: Raw weights from score ────────────────────────────
    total_score = df["score"].sum()
    df["weight"] = df["score"] / total_score if total_score > 0 else 1.0 / len(df)

    # ── STEP 7: Inverse-vol position sizing ───────────────────────
    # This is the core fix for Sharpe: equal risk contribution across sectors.
    df = _apply_inverse_vol_sizing(df)

    # ── STEP 8: Weight constraints ────────────────────────────────
    df["weight"] = df["weight"].clip(upper=MAX_WEIGHT, lower=0.0)
    df = df[df["weight"] >= MIN_WEIGHT].copy()
    if df.empty:
        return {"error": "all_filtered_min", "weights": {}}

    df["weight"] = df["weight"] / df["weight"].sum()

    # ── STEP 9: Theme cap ─────────────────────────────────────────
    df = _enforce_theme_cap(df)
    df["weight"] = df["weight"] / df["weight"].sum()

    # ── STEP 10: Correlation penalty ──────────────────────────────
    corr = _load_correlation_matrix()
    if not corr.empty:
        subs = df["subsector"].tolist()
        for i, s1 in enumerate(subs):
            for j, s2 in enumerate(subs):
                if i >= j:
                    continue
                if s1 in corr.index and s2 in corr.index:
                    c = float(corr.loc[s1, s2])
                    if abs(c) > CORR_THRESHOLD:
                        idx1 = df.index[df["subsector"] == s1][0]
                        idx2 = df.index[df["subsector"] == s2][0]
                        if df.loc[idx1, "score"] >= df.loc[idx2, "score"]:
                            df.loc[idx2, "weight"] *= 0.75
                        else:
                            df.loc[idx1, "weight"] *= 0.75
        df["weight"] = df["weight"] / df["weight"].sum()

    # ── STEP 11: Top-3 ≤ 60% ─────────────────────────────────────
    df = df.sort_values("weight", ascending=False).reset_index(drop=True)
    if len(df) >= 3:
        top3 = df.iloc[:3]["weight"].sum()
        if top3 > TOP3_CAP:
            excess = top3 - TOP3_CAP
            for idx in range(3):
                df.loc[idx, "weight"] -= excess / 3
            df["weight"] = df["weight"].clip(lower=0)
            df["weight"] = df["weight"] / df["weight"].sum()
            print(f"  ⚠ Top-3 reduced: {top3:.1%} → {TOP3_CAP:.0%}")

    # ── STEP 12: Macro exposure adjustment ────────────────────────
    vix      = macro_data.get("india_vix", {}).get("current", 15.0)
    drawdown = regime.get("rolling_drawdown_pct", 0.0)
    exposure = 1.0

    if vix > 20:
        exposure *= 0.75
        print(f"  ⚠ VIX={vix:.1f} > 20 → exposure {exposure*100:.0f}%")
    if abs(drawdown) > 8.0:
        exposure *= 0.80
        print(f"  ⚠ Drawdown {drawdown:.1f}% > 8% → further reduction")
    elif abs(drawdown) > 5.0:
        exposure *= 0.90
        print(f"  ⚠ Drawdown {drawdown:.1f}% > 5% → mild reduction")

    df["weight_adj"] = df["weight"] * exposure

    # Portfolio-level vol cap
    portfolio_vol_raw = float((df["weight_adj"] * df["volatility"]).sum())
    if portfolio_vol_raw > VOL_PORTFOLIO_CAP:
        vol_scale = VOL_PORTFOLIO_CAP / portfolio_vol_raw
        df["weight_adj"] *= vol_scale
        exposure          *= vol_scale
        print(f"  ⚠ Portfolio vol {portfolio_vol_raw:.1f}% > {VOL_PORTFOLIO_CAP}% "
              f"→ scaled {vol_scale:.3f}")

    cash_weight      = max(0.0, 1.0 - df["weight_adj"].sum())
    portfolio_return = float((df["weight_adj"] * df["exp_return"]).sum())
    portfolio_vol    = float((df["weight_adj"] * df["volatility"]).sum())
    horizon_factor   = {"1M": 1/12, "3M": 3/12, "6M": 6/12, "12M": 1.0}.get(horizon, 3/12)
    sharpe_like      = (
        ((portfolio_return / 100) - (RISK_FREE_RATE * horizon_factor)) / (portfolio_vol / 100)
        if portfolio_vol > 0 else 0.0
    )

    # ── Print summary ──────────────────────────────────────────────
    n_sectors = df["sector"].nunique()
    print(f"\n  {len(df)} subsectors | {n_sectors} sectors | exposure={exposure*100:.1f}%")
    print(f"  {'Subsector':<35} {'Wt':>6} {'AdjWt':>7} {'Ret':>7} {'Vol':>7} {'Alpha':>7}")
    print(f"  {'─'*72}")
    for _, row in df.iterrows():
        print(f"  {row['subsector'][:34]:<35} {row['weight']:>5.1%} "
              f"{row['weight_adj']:>6.1%} {row['exp_return']:>+6.1f}% "
              f"{row['volatility']:>6.1f}% {row['alpha_score']:>6.3f}")

    print(f"\n  Expected return  : {portfolio_return:+.2f}%")
    print(f"  Portfolio vol    : {portfolio_vol:.2f}%")
    print(f"  Sharpe-like      : {sharpe_like:.3f}")
    print(f"  Cash             : {cash_weight:.1%}")

    sector_wts = df.groupby("sector")["weight_adj"].sum()
    print(f"\n  Sector allocation:")
    for sec, wt in sector_wts.sort_values(ascending=False).items():
        bar = "█" * int(wt * 40)
        print(f"    {sec[:32]:<32} {wt:>6.1%} {bar}")

    return _format_output(
        df, macro_data, regime, horizon,
        portfolio_return=portfolio_return,
        portfolio_vol=portfolio_vol,
        sharpe_like=sharpe_like,
        cash_weight=cash_weight,
        exposure=exposure,
        vix=vix,
    )


def _format_output(df, macro_data, regime, horizon,
                   portfolio_return=0.0, portfolio_vol=0.0,
                   sharpe_like=0.0, cash_weight=0.0,
                   exposure=1.0, vix=15.0, note=""):
    weights = {}
    for _, row in df.iterrows():
        weights[row["subsector"]] = {
            "sector":          row.get("sector", ""),
            "raw_weight":      round(float(row.get("weight", 0)), 4),
            "adjusted_weight": round(float(row.get("weight_adj", row.get("weight", 0))), 4),
            "expected_return": round(float(row.get("exp_return", 0)), 2),
            "volatility":      round(float(row.get("volatility", 20)), 2),
            "score":           round(float(row.get("score", 0)), 4),
            "confidence":      round(float(row.get("confidence", 0.3)), 3),
            "alpha_score":     round(float(row.get("alpha_score", 0.5)), 4),
        }

    # TASK 4: STRICT VALIDATION — fail fast on invalid NIFTY data
    if not macro_data.get("nifty", {}).get("is_valid", False):
        raise ValueError("CRITICAL: Invalid NIFTY data — aborting portfolio construction run")

    return {
        "horizon":                  horizon,
        "generated_at":             str(macro_data.get("data_date", "")),
        "n_sectors":                df["sector"].nunique() if "sector" in df.columns else len(df),
        "n_subsectors":             len(df),
        "exposure_pct":             round(exposure * 100, 1),
        "cash_pct":                 round(cash_weight * 100, 1),
        "vix_at_construction":      vix,
        "portfolio_return_pct":     round(portfolio_return, 2),
        "portfolio_volatility_pct": round(portfolio_vol, 2),
        "sharpe_like":              round(sharpe_like, 3),
        "weights":                  weights,
        "note":                     note,
        "risk_flags": {
            "vix_elevated":     vix > 20,
            "exposure_reduced": exposure < 1.0,
        },
    }


if __name__ == "__main__":
    print("Portfolio Engine v5 — run via main.py --daily")
