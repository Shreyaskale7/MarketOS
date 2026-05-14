# risk_engine.py
# MarketOS — Risk Management Layer  [UPGRADED v4]
#
# FIX 3 — Stop-loss & drawdown control:
#   sector_drawdown > 8% → weight *= 0.5
#   portfolio_drawdown > 12% → total_exposure *= 0.7
#   volatility > historical_avg × 1.5 → reduce exposure
#
# FIX 4 — Turnover control: thresholds now in risk layer (per-sector 10%, total 15%)

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from database import get_session, DailyPrice, MacroData
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────
VIX_THRESHOLD              = 20.0
VIX_REDUCTION_FACTOR       = 0.75    # moderate — was 0.70
DRAWDOWN_SOFT_THRESHOLD    = 6.0
DRAWDOWN_HARD_THRESHOLD    = 12.0    # FIX 1: portfolio drawdown > 12%
DRAWDOWN_HARD_FACTOR       = 0.75    # FIX 1: exposure *= 0.75 (was 0.60)
# FIX 2: sector return < -7% → weight * 0.7
SECTOR_DRAWDOWN_THRESHOLD  = -7.0    # was -5%
SECTOR_DRAWDOWN_FACTOR     = 0.70    # was 0.50 — less aggressive
# FIX 1: portfolio_drawdown > 12% → total_exposure *= 0.75
PORT_DRAWDOWN_HARD         = -12.0   # was -8%
PORT_DRAWDOWN_HARD_FACTOR  = 0.75    # was 0.60
# FIX 3: vol spike > 1.5× rolling avg → exposure *= 0.85
VOL_SPIKE_MULTIPLIER       = 1.5
VOL_SPIKE_REDUCTION        = 0.85    # was 0.80 — less aggressive
STOP_LOSS_THRESHOLD        = -7.0    # aligned with sector drawdown
STOP_LOSS_FACTOR           = 0.70    # was 0.50
MAX_SECTOR_WEIGHT          = 0.28    # aligned with portfolio_engine FIX 3
TOP3_CAP                   = 0.65    # slightly relaxed — allows more return
HIGH_VOL_THRESHOLD         = 28.0    # moderate vol threshold
BEARISH_EXPOSURE_FACTOR    = 0.65    # was 0.60 — less severe


# ─────────────────────────────────────────────────────────────────
# PORTFOLIO DRAWDOWN
# ─────────────────────────────────────────────────────────────────

def _compute_portfolio_drawdown(weights: dict, lookback_days: int = 30) -> float:
    """Computes rolling max drawdown of portfolio over last lookback_days.
    PART 1: uses get_pipeline_date() — single date authority.
    """
    from pipeline_utils import get_pipeline_date
    since   = get_pipeline_date() - timedelta(days=lookback_days + 5)
    session = get_session()
    try:
        rows = session.query(DailyPrice).filter(
            DailyPrice.date >= since,
            DailyPrice.subsector.in_(list(weights.keys())),
            DailyPrice.daily_return.isnot(None)
        ).all()
    except Exception:
        rows = []
    finally:
        session.close()

    if not rows:
        return 0.0

    df = pd.DataFrame([{
        "date":         pd.Timestamp(r.date),
        "subsector":    r.subsector,
        "daily_return": float(r.daily_return or 0.0),
        "nifty_weight": float(r.nifty_weight or 0.001),
    } for r in rows])

    def _wm(g):
        w = g["nifty_weight"].sum()
        return (g["daily_return"] * g["nifty_weight"]).sum() / w if w > 0 else g["daily_return"].mean()

    daily_sub = df.groupby(["date", "subsector"]).apply(_wm).reset_index()
    daily_sub.columns = ["date", "subsector", "ret"]

    port_daily = []
    for dt, grp in daily_sub.groupby("date"):
        sub_map  = dict(zip(grp["subsector"], grp["ret"]))
        port_ret = sum(
            weights.get(sub, {}).get("adjusted_weight", 0.0) * ret
            for sub, ret in sub_map.items()
        )
        port_daily.append({"date": dt, "port_ret": port_ret})

    if not port_daily:
        return 0.0

    port_df     = pd.DataFrame(port_daily).sort_values("date")
    cum_ret     = (1 + port_df["port_ret"] / 100).cumprod()
    rolling_max = cum_ret.cummax()
    drawdowns   = (cum_ret - rolling_max) / rolling_max * 100
    return float(drawdowns.min())


def _get_recent_sector_returns(weights: dict, lookback_days: int = 21) -> dict:
    """
    SECTION 7: Computes 21-day cumulative return per sector for stop-loss check.
    Returns { subsector: cumulative_return_pct }
    PART 1: uses get_pipeline_date() — single date authority.
    """
    from pipeline_utils import get_pipeline_date
    since   = get_pipeline_date() - timedelta(days=lookback_days + 5)
    session = get_session()
    try:
        rows = session.query(DailyPrice).filter(
            DailyPrice.date >= since,
            DailyPrice.subsector.in_(list(weights.keys())),
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

    results = {}
    grouped = df.groupby(["date", "subsector"]).apply(_wm).reset_index()
    grouped.columns = ["date", "subsector", "ret"]
    for sub, grp in grouped.groupby("subsector"):
        grp     = grp.sort_values("date").iloc[-lookback_days:]
        cum_ret = float((1 + grp["ret"]).prod() - 1) * 100
        results[sub] = cum_ret
    return results


def _detect_vol_spike(weights: dict, lookback_short: int = 10, lookback_long: int = 60) -> dict:
    """
    FIX 3: Detects volatility spikes per sector.
    Spike = short-window vol > long-window vol × VOL_SPIKE_MULTIPLIER (1.5×).
    Returns { subsector: is_spiking (bool) }
    PART 1: uses get_pipeline_date() — single date authority.
    """
    from pipeline_utils import get_pipeline_date
    since   = get_pipeline_date() - timedelta(days=lookback_long + 5)
    session = get_session()
    try:
        rows = session.query(DailyPrice).filter(
            DailyPrice.date >= since,
            DailyPrice.subsector.in_(list(weights.keys())),
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

    grouped = df.groupby(["date", "subsector"]).apply(_wm).reset_index()
    grouped.columns = ["date", "subsector", "ret"]

    spikes = {}
    for sub, grp in grouped.groupby("subsector"):
        grp = grp.sort_values("date")
        if len(grp) < lookback_short:
            spikes[sub] = False
            continue
        vol_short = float(grp["ret"].iloc[-lookback_short:].std()) * np.sqrt(252)
        vol_long  = float(grp["ret"].std()) * np.sqrt(252)
        spikes[sub] = (vol_long > 0 and vol_short > vol_long * VOL_SPIKE_MULTIPLIER)

    return spikes


# ─────────────────────────────────────────────────────────────────
# RISK FLAGS
# ─────────────────────────────────────────────────────────────────

def compute_risk_flags(portfolio: dict, macro_data: dict, regime: dict) -> dict:
    """
    Evaluates portfolio against risk thresholds. Returns GREEN/AMBER/RED.

    MARKET STATE AWARENESS: On non-trading days, drawdown recalculation
    and exposure adjustments are skipped. The function returns the previous
    risk state with a CLOSED status flag, preventing false risk signals
    from stale or absent intraday price data.
    """
    # ── MARKET STATE GATE ─────────────────────────────────────────
    try:
        from market_calendar import get_market_status
        _mkt = get_market_status()
    except ImportError:
        _mkt = {"should_run_risk": True, "is_trading_day": True,
                "engine_mode": "FULL", "close_reason": ""}

    if not _mkt.get("should_run_risk", True):
        reason = _mkt.get("close_reason", "non-trading day")
        print(f"\n  ⚠ RISK ENGINE: Drawdown + exposure recalculation SKIPPED — {reason}")
        print("     Returning static risk state — no adjustments on non-trading days.")
        return {
            "status":        "SKIPPED_MARKET_CLOSED",
            "reason":        reason,
            "overall_risk":  "GREEN",
            "engine_mode":   _mkt.get("engine_mode", "FORECAST_ONLY"),
            "data_quality":  _mkt.get("data_quality", "HOLIDAY"),
            "flags": {
                "vix_elevated":         False,
                "drawdown_soft":        False,
                "drawdown_hard":        False,
                "concentration_breach": False,
                "max_weight_breach":    False,
                "high_vol_sectors":     0,
                "n_sectors":            len(portfolio.get("weights", {})),
            },
            "metrics": {
                "rolling_drawdown_pct": 0.0,
                "vix":                  macro_data.get("india_vix", {}).get("current", 0),
                "top3_weight":          0.0,
                "max_single_weight":    0.0,
            },
            "message": (
                f"Risk engine skipped — market closed ({reason}). "
                "No drawdown recalculation or exposure adjustment applied."
            ),
        }
    weights  = portfolio.get("weights", {})
    vix      = macro_data.get("india_vix", {}).get("current", 15.0)
    drawdown = _compute_portfolio_drawdown(weights)

    adj_weights = [w.get("adjusted_weight", 0) for w in weights.values()]
    sorted_w    = sorted(adj_weights, reverse=True)
    top3_weight = sum(sorted_w[:3]) if len(sorted_w) >= 3 else sum(sorted_w)
    max_single  = max(adj_weights) if adj_weights else 0
    high_vol_count = sum(1 for w in weights.values() if w.get("volatility", 0) > HIGH_VOL_THRESHOLD)

    flags = {
        "vix_elevated":         vix > VIX_THRESHOLD,
        "drawdown_soft":        abs(drawdown) > DRAWDOWN_SOFT_THRESHOLD,
        "drawdown_hard":        abs(drawdown) > DRAWDOWN_HARD_THRESHOLD,
        "concentration_breach": top3_weight > TOP3_CAP,
        "max_weight_breach":    max_single > MAX_SECTOR_WEIGHT,
        "high_vol_sectors":     high_vol_count,
        "n_sectors":            len(weights),
    }

    metrics = {
        "vix":                   round(vix, 2),
        "rolling_drawdown_pct":  round(drawdown, 3),
        "top3_weight_pct":       round(top3_weight * 100, 1),
        "max_single_weight_pct": round(max_single * 100, 1),
    }

    breach_count = sum([
        flags["vix_elevated"],
        flags["drawdown_soft"],
        flags["concentration_breach"],
        flags["max_weight_breach"],
    ])
    severity = "GREEN" if breach_count == 0 else ("AMBER" if breach_count == 1 else "RED")

    return {"severity": severity, "breach_count": breach_count, "flags": flags, "metrics": metrics}


# ─────────────────────────────────────────────────────────────────
# APPLY RISK RULES
# ─────────────────────────────────────────────────────────────────

def apply_risk_rules(portfolio: dict, macro_data: dict, regime: dict) -> dict:
    """
    FIX 3+4 UPGRADED RULES:
      Rule 1 — VIX > 20 → exposure ×0.70
      Rule 2 — Portfolio drawdown > 12% → exposure ×0.70          [FIX 3]
      Rule 3 — Sector drawdown > 8% → sector weight ×0.50         [FIX 3]
      Rule 4 — Volatility spike (>1.5× hist avg) → sector ×0.80  [FIX 3]
      Rule 5 — Stop-loss (21d return < -8%) → halve weight
      Rule 6 — Soft drawdown (5–10%) → high-vol trimmed
      Rule 7 — BEARISH regime → exposure ×0.60
      Rule 8 — Sector cap 25%
      Rule 9 — Top-3 ≤ 60%
      Rule 10 — Severity-linked exposure reduction
      Rule 11 — Low-diversification penalty

    MARKET STATE AWARENESS: On non-trading days, all exposure adjustments
    are bypassed. The portfolio is returned as-is to avoid acting on
    absent or stale price data.
    """
    print("\n=== RISK MANAGEMENT LAYER [v4 — FIX 3+4] ===")

    # ── MARKET STATE GATE ─────────────────────────────────────────
    try:
        from market_calendar import get_market_status
        _mkt = get_market_status()
    except ImportError:
        _mkt = {"should_run_risk": True, "close_reason": "",
                "engine_mode": "FULL"}

    if not _mkt.get("should_run_risk", True):
        reason = _mkt.get("close_reason", "non-trading day")
        print(f"  ⚠ Risk rules SKIPPED — {reason}")
        print("     Exposure adjustments bypassed. Portfolio weights unchanged.")
        return {
            **portfolio,
            "applied_rules":   [],
            "status":          "SKIPPED_MARKET_CLOSED",
            "reason":          reason,
            "engine_mode":     _mkt.get("engine_mode", "FORECAST_ONLY"),
            "data_quality":    _mkt.get("data_quality", "HOLIDAY"),
        }

    if not portfolio or "weights" not in portfolio:
        print("  No portfolio — risk layer skipped.")
        return {"error": "no_portfolio", "weights": {}, "risk_flags": {}}

    weights       = {k: dict(v) for k, v in portfolio.get("weights", {}).items()}
    vix           = macro_data.get("india_vix", {}).get("current", 15.0)
    drawdown      = _compute_portfolio_drawdown(weights)
    exposure      = portfolio.get("exposure_pct", 100.0) / 100.0
    regime_label  = regime.get("overall_regime", "NEUTRAL") if regime else "NEUTRAL"
    applied_rules = []

    # ── Rule 1: VIX ───────────────────────────────────────────────
    if vix > VIX_THRESHOLD:
        for sub in weights:
            weights[sub]["adjusted_weight"] *= VIX_REDUCTION_FACTOR
        exposure *= VIX_REDUCTION_FACTOR
        applied_rules.append(f"VIX={vix:.1f} → exposure ×{VIX_REDUCTION_FACTOR}")
        print(f"  ⚠ Rule 1 [VIX={vix:.1f}]: exposure cut to {VIX_REDUCTION_FACTOR*100:.0f}%")

    # ── Rule 2: FIX 3 — Portfolio drawdown > 12% ──────────────────
    if drawdown <= PORT_DRAWDOWN_HARD:
        for sub in weights:
            weights[sub]["adjusted_weight"] *= PORT_DRAWDOWN_HARD_FACTOR
        exposure *= PORT_DRAWDOWN_HARD_FACTOR
        applied_rules.append(f"Portfolio DD={drawdown:.1f}% > 12% → ALL ×{PORT_DRAWDOWN_HARD_FACTOR}")
        print(f"  🔴 Rule 2 [FIX 3 Port DD={drawdown:.1f}%]: ALL weights cut 30%")

    # ── Rule 3: FIX 3 — Sector drawdown > 8% → halve weight ───────
    recent_returns = _get_recent_sector_returns(weights, lookback_days=21)
    for sub, cum_ret in recent_returns.items():
        if cum_ret <= SECTOR_DRAWDOWN_THRESHOLD and sub in weights:
            old_w = weights[sub]["adjusted_weight"]
            weights[sub]["adjusted_weight"] *= SECTOR_DRAWDOWN_FACTOR
            applied_rules.append(f"Sector DD: {sub[:28]} {cum_ret:.1f}% → ×{SECTOR_DRAWDOWN_FACTOR}")
            print(f"  🛑 Rule 3 [FIX 3 Sector DD]: {sub[:30]} {cum_ret:.1f}% → {old_w:.1%}→{weights[sub]['adjusted_weight']:.1%}")

    # ── Rule 4: FIX 3 — Volatility spike detection ────────────────
    vol_spikes = _detect_vol_spike(weights)
    for sub, is_spiking in vol_spikes.items():
        if is_spiking and sub in weights:
            old_w = weights[sub]["adjusted_weight"]
            weights[sub]["adjusted_weight"] *= VOL_SPIKE_REDUCTION
            applied_rules.append(f"Vol spike: {sub[:28]} → ×{VOL_SPIKE_REDUCTION}")
            print(f"  ⚡ Rule 4 [FIX 3 Vol spike]: {sub[:30]} → {old_w:.1%}→{weights[sub]['adjusted_weight']:.1%}")

    # ── Rule 5: Stop-loss (21d cumulative return < -8%) ───────────
    for sub, cum_ret in recent_returns.items():
        if cum_ret < STOP_LOSS_THRESHOLD and sub in weights:
            old_w = weights[sub]["adjusted_weight"]
            weights[sub]["adjusted_weight"] *= STOP_LOSS_FACTOR
            applied_rules.append(f"Stop-loss: {sub[:28]} {cum_ret:.1f}% → halved")
            print(f"  🛑 Rule 5 [Stop-loss]: {sub[:30]} {cum_ret:.1f}% → {old_w:.1%}→{weights[sub]['adjusted_weight']:.1%}")

    # ── Rule 6: Soft drawdown 5–12%: trim high-vol ────────────────
    if DRAWDOWN_SOFT_THRESHOLD < abs(drawdown) <= abs(PORT_DRAWDOWN_HARD):
        for sub, w in weights.items():
            if w.get("volatility", 0) > HIGH_VOL_THRESHOLD:
                weights[sub]["adjusted_weight"] *= 0.85
        applied_rules.append(f"Soft DD={drawdown:.1f}%: high-vol trimmed")
        print(f"  ⚠ Rule 6 [Soft DD={drawdown:.1f}%]: high-vol sectors trimmed")

    # ── Rule 7: BEARISH regime ────────────────────────────────────
    if "BEARISH" in regime_label.upper():
        for sub in weights:
            weights[sub]["adjusted_weight"] *= BEARISH_EXPOSURE_FACTOR
        exposure *= BEARISH_EXPOSURE_FACTOR
        applied_rules.append(f"Regime={regime_label} → ×{BEARISH_EXPOSURE_FACTOR}")
        print(f"  🐻 Rule 7 [BEARISH]: exposure cut to {BEARISH_EXPOSURE_FACTOR*100:.0f}%")

    # ── Rule 8: Sector cap ────────────────────────────────────────
    for sub in weights:
        if weights[sub]["adjusted_weight"] > MAX_SECTOR_WEIGHT:
            weights[sub]["adjusted_weight"] = MAX_SECTOR_WEIGHT

    # ── Rule 9: Top-3 concentration ───────────────────────────────
    sorted_subs = sorted(weights.items(), key=lambda x: x[1]["adjusted_weight"], reverse=True)
    top3_total  = sum(w["adjusted_weight"] for _, w in sorted_subs[:3])
    if top3_total > TOP3_CAP:
        excess  = top3_total - TOP3_CAP
        per_sub = excess / 3
        for sub, _ in sorted_subs[:3]:
            weights[sub]["adjusted_weight"] = max(0, weights[sub]["adjusted_weight"] - per_sub)
        applied_rules.append(f"Top-3 {top3_total:.1%} → {TOP3_CAP:.0%}")
        print(f"  ⚠ Rule 9: top-3 {top3_total:.1%} → {TOP3_CAP:.0%}")

    # ── Renormalise ───────────────────────────────────────────────
    total_w = sum(w["adjusted_weight"] for w in weights.values())
    cash_w  = 1.0 - min(exposure, 1.0)
    if total_w > 0:
        for sub in weights:
            weights[sub]["adjusted_weight"] = weights[sub]["adjusted_weight"] / total_w * min(exposure, 1.0)

    risk_flags = compute_risk_flags({"weights": weights}, macro_data, regime)

    # ── Rule 10: FIX 4 — Severity-linked exposure ────────────────
    if risk_flags["severity"] == "RED":
        exposure *= 0.70    # FIX 4: RED → ×0.70
        for sub in weights:
            weights[sub]["adjusted_weight"] *= 0.70
        applied_rules.append("Severity=RED → exposure ×0.70")
        print(f"  🔴 Rule 10 [Severity=RED]: exposure cut to {exposure*100:.0f}%")
    elif risk_flags["severity"] == "AMBER":
        exposure *= 0.85    # FIX 4: AMBER → ×0.85
        for sub in weights:
            weights[sub]["adjusted_weight"] *= 0.85
        applied_rules.append("Severity=AMBER → exposure ×0.85")
        print(f"  🟡 Rule 10 [Severity=AMBER]: exposure cut to {exposure*100:.0f}%")

    total_w = sum(w["adjusted_weight"] for w in weights.values())
    cash_w  = max(0.0, 1.0 - total_w)

    # ── Rule 11: Low-diversification penalty ─────────────────────
    if len(weights) < 4:
        exposure *= 0.70
        for sub in weights:
            weights[sub]["adjusted_weight"] *= 0.70
        cash_w = max(0.0, 1.0 - sum(w["adjusted_weight"] for w in weights.values()))
        applied_rules.append(f"Low diversification ({len(weights)} sectors) → ×0.70")
        print(f"  ⚠ Rule 11 [Low div={len(weights)}]: exposure cut to {exposure*100:.0f}%")

    print(f"\n  {'Sector':<35} {'Adj.Wt':>8} {'Vol':>7} {'Status'}")
    print(f"  {'─'*58}")
    for sub, w in sorted(weights.items(), key=lambda x: x[1]["adjusted_weight"], reverse=True):
        vol    = w.get("volatility", 20)
        status = "HIGH_VOL" if vol > HIGH_VOL_THRESHOLD else "OK"
        print(f"  {sub[:34]:<35} {w['adjusted_weight']:>7.1%} {vol:>6.1f}%  {status}")

    print(f"\n  Regime     : {regime_label}")
    print(f"  Severity   : {risk_flags['severity']}")
    print(f"  Rules fired: {len(applied_rules)}")
    for r in applied_rules[:10]:
        print(f"    → {r}")

    return {
        "weights":       weights,
        "risk_flags":    risk_flags,
        "rules_applied": applied_rules,
        "cash_pct":      round(cash_w * 100, 1),
        "exposure_pct":  round(min(exposure, 1.0) * 100, 1),
        "drawdown_pct":  round(drawdown, 3),
        "regime":        regime_label,
    }


if __name__ == "__main__":
    print("Risk Engine v3 — run via main.py --daily")
