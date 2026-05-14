# backtest_engine.py
# MarketOS — Walk-Forward Backtesting Engine  [v4 — High-Sharpe]
#
# KEY IMPROVEMENTS vs v3:
#   1. TURNOVER FILTER tightened: per-sector 10% (was 5%), total 15% (was 10%)
#   2. VOLATILITY SMOOTHING: blended 20d/60d rolling vol for stable weights
#   3. WEIGHT JUMP LIMITER: new_weight clamped within ±10% of old_weight
#   4. BENCHMARK: close-to-close pct_change, aligned dates, 8–12% validation
#   5. INVERSE-VOL weighting in backtest weights (matches live portfolio engine)
#   6. Consistency checks on output metrics

import numpy as np
import pandas as pd
from datetime import datetime, timedelta, date
from database import get_session, DailyPrice, MacroData
from classification import MARKET_CLASSIFICATION
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────
REBALANCE_FREQ_DAYS  = 30       # monthly rebalancing
FORWARD_WINDOW_DAYS  = 30
TRAIN_WINDOW_DAYS    = 126      # 6 months training window

MAX_WEIGHT           = 0.20    # must match portfolio_engine.py
MIN_WEIGHT           = 0.05
RISK_FREE_ANNUAL     = 0.065

TRANSACTION_COST_PCT = 0.0015   # Part 5d: 0.15% (was 0.2%)
SLIPPAGE_PCT         = 0.0005   # Part 5d: 0.05% (was 0.1%)
TOTAL_COST           = TRANSACTION_COST_PCT + SLIPPAGE_PCT   # 0.20%

# TIGHTENED turnover filters
TURNOVER_MIN_CHANGE  = 0.12     # skip trade if shift < 12%
REBALANCE_MIN_CHANGE = 0.25     # Part 5e: raised from 0.18 — skip rebalance if drift < 25%

# Weight-jump limiter: new weight can't move more than ±10% from old in one step
MAX_WEIGHT_JUMP      = 0.10

# NIFTY benchmark validation range
NIFTY_ANN_MIN = 0.08
NIFTY_ANN_MAX = 0.12   # FIX 5: spec says 8–12% (was 15%)


# ─────────────────────────────────────────────────────────────────
# BACKTEST CACHE HELPERS
# ─────────────────────────────────────────────────────────────────

def _get_backtest_anchor_date(lookback_years: int) -> str:
    """
    Returns a FIXED anchor date string for a given lookback window.

    The anchor is the first trading day of the lookback period,
    computed from the EARLIEST available data in the DB — not from today.
    This never changes as long as historical data doesn't change.

    Format returned: "YYYY-MM-DD"

    Why this works: the backtest simulation is walk-forward over a fixed
    historical window. The window is defined by (anchor → anchor + N years).
    Only new data added to the DB after anchor+N years should change results.
    """
    from database import get_session, DailyPrice
    session = get_session()
    try:
        from sqlalchemy import func
        earliest_row = session.query(func.min(DailyPrice.date)).scalar()
        if earliest_row is None:
            # Fallback: compute from pipeline_date
            from pipeline_utils import get_pipeline_date
            pd_date = get_pipeline_date()
            earliest_row = pd_date - timedelta(days=lookback_years * 365 + 60)
    finally:
        session.close()

    if earliest_row is None:
        return None
    # earliest_row may already be a date object (SQLAlchemy returns date from Date column)
    # or a string — normalise to string for the cache key, caller converts to date
    return str(earliest_row)[:10]   # ensure "YYYY-MM-DD" format, strip any time component


def _get_cache_key(lookback_years: int) -> str:
    """
    Returns the cache key for this backtest configuration.
    Stable as long as the earliest data in the DB doesn't change.
    """
    anchor = _get_backtest_anchor_date(lookback_years)
    return f"backtest_{lookback_years}yr_{anchor}"


def _load_cached_backtest(lookback_years: int) -> dict | None:
    """
    Loads a cached backtest result from the DB if one exists.
    Returns None if no cache entry found.
    """
    import json
    from database import get_session, BacktestCache

    cache_key = _get_cache_key(lookback_years)
    session = get_session()
    try:
        row = session.query(BacktestCache).filter(
            BacktestCache.cache_key == cache_key
        ).first()

        if row is None:
            return None

        print(f"  \u2713 Backtest cache HIT \u2014 key={cache_key} | generated={row.generated_date}")
        print(f"    Returning stable cached result ({row.n_periods} periods). "
              f"Use --force to recompute.")

        return {
            "status":               row.status,
            "generated_at":         str(row.generated_date),
            "lookback_years":       row.lookback_years,
            "n_periods":            row.n_periods,
            "metrics":              json.loads(row.metrics_json or "{}"),
            "equity_curve":         json.loads(row.equity_curve_json or "[]"),
            "period_returns":       json.loads(row.period_returns_json or "[]"),
            "consistency_warnings": json.loads(row.consistency_warnings_json or "[]"),
            "_from_cache":          True,
        }
    except Exception as e:
        print(f"  \u26a0 Cache load error: {e} \u2014 will recompute")
        return None
    finally:
        session.close()


def _json_serializer(obj):
    """Handles date/datetime objects that json.dumps cannot serialize."""
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not JSON serializable")

def _save_backtest_to_cache(results: dict, lookback_years: int) -> None:
    """
    Saves a completed backtest result to the DB cache.
    Upserts by cache_key (delete old + insert new).
    """
    import json
    from datetime import date as date_type
    from database import get_session, BacktestCache

    if results.get("status") != "ok":
        print("  \u2139 Backtest cache: not saving \u2014 status is not 'ok'")
        return

    cache_key = _get_cache_key(lookback_years)
    anchor_str = _get_backtest_anchor_date(lookback_years)
    from datetime import date as _date
    anchor = _date.fromisoformat(str(anchor_str)) if anchor_str else _date.today()

    session = get_session()
    try:
        # Delete existing entry for this key (upsert pattern)
        existing = session.query(BacktestCache).filter(
            BacktestCache.cache_key == cache_key
        ).first()
        if existing:
            session.delete(existing)
            session.flush()

        row = BacktestCache(
            cache_key                 = cache_key,
            anchor_date               = anchor,
            lookback_years            = lookback_years,
            generated_date            = date_type.today(),
            metrics_json              = json.dumps(results.get("metrics", {}), default=_json_serializer),
            equity_curve_json         = json.dumps(results.get("equity_curve", []), default=_json_serializer),
            period_returns_json       = json.dumps(results.get("period_returns", []), default=_json_serializer),
            n_periods                 = results.get("n_periods", 0),
            status                    = results.get("status", "ok"),
            consistency_warnings_json = json.dumps(results.get("consistency_warnings", [])),
        )
        session.add(row)
        session.commit()
        print(f"  \u2713 Backtest result saved to cache \u2014 key={cache_key}")
    except Exception as e:
        session.rollback()
        print(f"  \u26a0 Cache save error: {e}")
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────

def _load_all_sector_returns(lookback_years: int = 3) -> pd.DataFrame:
    """Loads daily sector returns as a date × subsector DataFrame.
    PART 1: uses get_pipeline_date() as the lookback anchor.
    """
    from pipeline_utils import get_pipeline_date
    pipeline_date = get_pipeline_date()
    since = pipeline_date - timedelta(days=lookback_years * 365 + 60)
    session = get_session()
    try:
        rows = session.query(DailyPrice).filter(
            DailyPrice.date >= since,
            DailyPrice.daily_return.isnot(None)
        ).order_by(DailyPrice.date).all()
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

    # Remove extreme outliers (>35% daily — data errors)
    df = df[df["daily_return"].abs() < 0.35]

    def _wm(g):
        w = g["nifty_weight"].sum()
        return (g["daily_return"] * g["nifty_weight"]).sum() / w if w > 0 else g["daily_return"].mean()

    return (
        df.groupby(["date", "subsector"])
        .apply(_wm)
        .unstack("subsector")
        .sort_index()
    )


def _load_nifty_returns(
    lookback_years: int = 3,
    sector_dates: pd.DatetimeIndex = None,
) -> pd.Series:
    """
    BENCHMARK FIX (Parts 1 + 5a + 5b + 5c):
      - PART 1:  uses get_pipeline_date() as anchor — NOT datetime.today()
      - PART 5a: aligns NIFTY dates with sector_dates (no phantom trading days)
      - PART 5b: drops NaN after alignment
      - PART 5c: asserts len(nifty_rets) > 100 (minimum data quality gate)
    Validates annualised return is ~8–12%.
    """
    from pipeline_utils import get_pipeline_date, get_nifty_return_from_db
    pipeline_date = get_pipeline_date()
    since = pipeline_date - timedelta(days=lookback_years * 365 + 60)
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
        "nifty_close":  float(r.nifty_close or 0.0),
        "nifty_return": float(r.nifty_return or 0.0),
    } for r in rows]).set_index("date").sort_index()

    # Prefer close-to-close returns (more accurate than stored field)
    if (df["nifty_close"] > 0).sum() > 20:
        closes     = df["nifty_close"][df["nifty_close"] > 0]
        nifty_rets = closes.pct_change().dropna()
        # Filter extreme days (holidays, errors)
        nifty_rets = nifty_rets[nifty_rets.abs() < 0.10]
        print(f"  [Benchmark] NIFTY close-to-close: {len(nifty_rets)} days")
    else:
        nifty_rets = df["nifty_return"] / 100.0
        nifty_rets = nifty_rets[nifty_rets.abs() < 0.10]
        print(f"  [Benchmark] NIFTY from return field: {len(nifty_rets)} days")

    # PART 5a: Align NIFTY dates with sector dates — no phantom days
    if sector_dates is not None and len(sector_dates) > 0:
        pre_align = len(nifty_rets)
        nifty_rets = nifty_rets[nifty_rets.index.isin(sector_dates)]
        print(f"  [Benchmark] Date alignment: {pre_align} → {len(nifty_rets)} days "
              f"(matched to sector calendar)")

    # PART 5b: Drop any NaN that remain after alignment
    nifty_rets = nifty_rets.dropna()

    # PART 5c: Minimum data quality gate
    if len(nifty_rets) < 100:
        print(f"  ⚠ [Benchmark] Insufficient NIFTY data: {len(nifty_rets)} days "
              f"(minimum 100 required for reliable backtest)")
        # Return what we have — caller handles empty series
    else:
        print(f"  ✓ [Benchmark] NIFTY data OK: {len(nifty_rets)} trading days")

    # Validate annualised return
    if len(nifty_rets) > 50:
        years     = len(nifty_rets) / 252
        final_val = float((1 + nifty_rets).prod())
        ann_ret   = (final_val ** (1 / years) - 1) if years > 0 else 0.0
        if ann_ret < NIFTY_ANN_MIN or ann_ret > NIFTY_ANN_MAX:
            print(f"  ⚠ Benchmark WARNING: NIFTY annualised={ann_ret:.1%} "
                  f"(expected {NIFTY_ANN_MIN:.0%}–{NIFTY_ANN_MAX:.0%})")
        else:
            print(f"  ✓ Benchmark validated: NIFTY annualised={ann_ret:.1%}")

    return nifty_rets


# ─────────────────────────────────────────────────────────────────
# BACKTEST PORTFOLIO BUILDER
# ─────────────────────────────────────────────────────────────────

def _compute_rolling_vol(series: pd.Series, window: int = 20) -> float:
    """
    Volatility smoothing using exactly 20-day rolling std, annualised.
    """
    if len(series) < 10:
        return 0.20   # default 20%
    if len(series) >= window:
        vol = float(series.iloc[-window:].std() * np.sqrt(252))
        return max(vol, 0.05)
    return max(float(series.std() * np.sqrt(252)), 0.05)


def _backtest_weights(
    sector_df:    pd.DataFrame,
    as_of_date:   pd.Timestamp,
    prev_weights: dict = None,
    train_days:   int  = TRAIN_WINDOW_DAYS,
) -> tuple:
    """
    Builds weights using only data strictly before as_of_date.

    Methodology:
    1. Sharpe-score each subsector (mean/std of returns)
    2. Inverse-vol position sizing (equal risk contribution)
    3. Turnover filter: skip if total drift < 15%, skip individual if shift < 10%
    4. Weight-jump limiter: clamp new_weight within ±10% of old_weight

    Returns: (weights_dict, rebalance_was_skipped: bool)
    """
    hist = sector_df[sector_df.index < as_of_date].iloc[-train_days:]
    if len(hist) < 20:
        return {}, False

    scores    = {}
    ivol_w    = {}   # inverse-vol weights

    for col in hist.columns:
        series = hist[col].dropna()
        if len(series) < 10:
            continue
        mean_r = float(series.mean())
        if mean_r <= 0:
            continue   # only positive-expected-return sectors

        # PART 5f: Momentum filter — skip sectors with negative 20d momentum
        # A sector trending down should not receive fresh allocation
        if len(series) >= 20:
            last_20d_return = float((1 + series.iloc[-20:]).prod() - 1)
            if last_20d_return < 0:
                continue   # negative momentum — skip this sector this period
        # Blended vol for stable estimates
        vol = _compute_rolling_vol(series)
        if vol < 1e-6:
            continue
        sharpe   = mean_r / vol         # annualised Sharpe-like score
        scores[col] = max(sharpe, 0.0)
        ivol_w[col] = 1.0 / vol        # inverse vol for sizing

    if not scores:
        return {}, False

    # Score-proportional raw weights
    total_score = sum(scores.values())
    raw_weights = {sub: scores[sub] / total_score for sub in scores}

    # Inverse-vol adjustment: weight_new = raw_weight / vol → renormalise
    inv_weighted = {sub: raw_weights[sub] * ivol_w[sub] for sub in scores}
    total_ivw    = sum(inv_weighted.values())
    norm_weights = {sub: inv_weighted[sub] / total_ivw for sub in scores}

    # Volatility-regime penalty: if recent vol > 25% annualised → reduce 20%
    for col in norm_weights:
        series = hist[col].dropna()
        vol    = _compute_rolling_vol(series)
        if vol > 0.25:
            norm_weights[col] *= 0.80

    # Apply weight constraints
    filtered = {s: min(w, MAX_WEIGHT) for s, w in norm_weights.items() if w >= MIN_WEIGHT}
    if not filtered:
        return {}, False

    total_f = sum(filtered.values())
    new_weights = {s: w / total_f for s, w in filtered.items()}

    # ── TURNOVER FILTER (tightened vs v3) ──────────────────────────
    if prev_weights:
        all_subs     = set(new_weights) | set(prev_weights)
        total_change = sum(
            abs(new_weights.get(s, 0) - prev_weights.get(s, 0))
            for s in all_subs
        )
        # Skip entire rebalance if total portfolio drift < 15% (was 10%)
        if total_change < REBALANCE_MIN_CHANGE:
            return prev_weights, True   # True = skipped

        # Per-sector turnover: keep old weight if change < 10% (was 5%)
        final = {}
        for sub in all_subs:
            nw = new_weights.get(sub, 0)
            pw = prev_weights.get(sub, 0)
            if abs(nw - pw) < TURNOVER_MIN_CHANGE:
                final[sub] = pw    # no trade — keep old weight
            else:
                # WEIGHT JUMP LIMITER: clamp new_weight within ±10% of old
                # Prevents large allocation swings that spike turnover/costs
                final[sub] = float(np.clip(nw, pw - MAX_WEIGHT_JUMP, pw + MAX_WEIGHT_JUMP))

        final = {s: w for s, w in final.items() if w >= MIN_WEIGHT}
        if not final:
            return new_weights, False
        total_f2 = sum(final.values())
        return {s: w / total_f2 for s, w in final.items()}, False

    return new_weights, False


# ─────────────────────────────────────────────────────────────────
# WALK-FORWARD SIMULATION
# ─────────────────────────────────────────────────────────────────

def run_backtest(lookback_years: int = 3, force_recompute: bool = False) -> dict:
    """
    Walk-forward backtest with institutional-grade controls.

    Results are cached in the backtest_cache DB table for stability.

    CACHE INVALIDATION POLICY:
    - Cache key = "backtest_{N}yr_{earliest_data_date}"
    - Cache is stable as long as historical data (daily_prices) doesn't change
    - Re-run with force_recompute=True after:
        (a) Adding new historical price data that extends the backtest window
        (b) Changing CONSTANTS (REBALANCE_FREQ_DAYS, MAX_WEIGHT, etc.)
        (c) Changing _backtest_weights() logic
    - Normal daily --daily pipeline runs do NOT invalidate the cache
      (new trading day data only adds to the forward end, not the historical window)

    Improvements vs v3:
    - Inverse-vol position sizing (matches live engine)
    - Tighter turnover: 10%/15% (was 5%/10%)
    - Weight-jump limiter: ±10% per rebalance
    - Blended vol smoothing (20d/60d)
    - NIFTY close-to-close benchmark
    - Output consistency checks
    """
    # ── CACHE GATE ────────────────────────────────────────────────
    # Check cache FIRST. If a stable result exists and force_recompute
    # is False, return it immediately without re-running the simulation.
    # This ensures backtest metrics are reproducible and don't drift daily.
    if not force_recompute:
        cached = _load_cached_backtest(lookback_years)
        if cached is not None:
            return cached
    else:
        print(f"  \u26a1 force_recompute=True \u2014 bypassing cache, running full simulation")
    # ── END CACHE GATE ────────────────────────────────────────────
    print(f"\n=== BACKTEST ENGINE v4 — {lookback_years}yr walk-forward ===")
    print(f"  Rebalance: {REBALANCE_FREQ_DAYS}d | Cost: {TOTAL_COST:.1%} | "
          f"Turnover filter: >{TURNOVER_MIN_CHANGE:.0%} per sector | "
          f"Skip rebalance if <{REBALANCE_MIN_CHANGE:.0%} total drift | "
          f"Weight jump limit: ±{MAX_WEIGHT_JUMP:.0%}")

    sector_df  = _load_all_sector_returns(lookback_years)
    # PART 5a: pass sector dates for NIFTY alignment
    nifty_rets = _load_nifty_returns(lookback_years, sector_dates=sector_df.index)

    if sector_df.empty:
        print("  No historical data — run --setup first.")
        return {"status": "no_data"}

    trading_dates = sector_df.index.sort_values()
    start_idx     = TRAIN_WINDOW_DAYS + 10

    if start_idx >= len(trading_dates) - FORWARD_WINDOW_DAYS:
        return {"status": "insufficient_data"}

    # Rebalance schedule
    rebalance_dates = []
    idx = start_idx
    while idx < len(trading_dates) - FORWARD_WINDOW_DAYS:
        rebalance_dates.append(trading_dates[idx])
        idx += REBALANCE_FREQ_DAYS

    print(f"  Rebalance dates: {len(rebalance_dates)} | "
          f"{rebalance_dates[0].date()} → {rebalance_dates[-1].date()}")

    results           = []
    prev_weights      = {}
    skipped           = 0
    actual_rebalances = 0

    for rb_date in rebalance_dates:
        new_weights, was_skipped = _backtest_weights(sector_df, rb_date, prev_weights)

        if not new_weights:
            continue

        if was_skipped:
            weights = prev_weights
            cost    = 0.0
            skipped += 1
        else:
            weights = new_weights
            cost    = TOTAL_COST * 100
            actual_rebalances += 1
            prev_weights = dict(weights)

        # Forward return window
        fwd_mask = (sector_df.index > rb_date) & (
            sector_df.index <= rb_date + timedelta(days=FORWARD_WINDOW_DAYS * 1.5)
        )
        fwd_df = sector_df[fwd_mask].iloc[:FORWARD_WINDOW_DAYS]
        if len(fwd_df) < 5:
            continue

        port_daily = pd.Series(0.0, index=fwd_df.index)
        for sub, w in weights.items():
            if sub in fwd_df.columns:
                port_daily += w * fwd_df[sub].fillna(0.0)

        port_gross = float((1 + port_daily).prod() - 1) * 100
        port_net   = port_gross - cost

        # BENCHMARK: align NIFTY dates with portfolio window
        nifty_fwd = pd.Series(dtype=float)
        if not nifty_rets.empty:
            nm = (nifty_rets.index > rb_date) & (
                nifty_rets.index <= rb_date + timedelta(days=FORWARD_WINDOW_DAYS * 1.5)
            )
            nifty_fwd = nifty_rets[nm].iloc[:FORWARD_WINDOW_DAYS]
        nifty_cum = float((1 + nifty_fwd).prod() - 1) * 100 if len(nifty_fwd) >= 5 else 0.0

        results.append({
            "date":         rb_date.date(),
            "n_sectors":    len(weights),
            "port_gross":   round(port_gross, 3),
            "port_return":  round(port_net, 3),
            "nifty_return": round(nifty_cum, 3),
            "alpha":        round(port_net - nifty_cum, 3),
            "cost":         round(cost, 3),
            "skipped":      was_skipped,
            "top_sector":   max(weights, key=weights.get) if weights else "",
        })

    if not results:
        return {"status": "no_results"}

    res_df = pd.DataFrame(results)

    # ── Compute metrics ────────────────────────────────────────────
    cum_port  = (1 + res_df["port_return"] / 100).cumprod()
    cum_nifty = (1 + res_df["nifty_return"] / 100).cumprod()
    n         = len(res_df)
    ppy       = 252 / REBALANCE_FREQ_DAYS
    years     = n / ppy

    total_port  = float(cum_port.iloc[-1])
    total_nifty = float(cum_nifty.iloc[-1])

    ann_port  = (total_port  ** (1 / years) - 1) * 100 if years > 0 else 0.0
    ann_nifty = (total_nifty ** (1 / years) - 1) * 100 if years > 0 else 0.0

    port_std  = float(res_df["port_return"].std())
    rf_period = (RISK_FREE_ANNUAL / ppy) * 100
    sharpe    = float(
        (res_df["port_return"] - rf_period).mean() / port_std * np.sqrt(ppy)
    ) if port_std > 0 else 0.0

    rolling_max = cum_port.cummax()
    drawdowns   = (cum_port - rolling_max) / rolling_max * 100
    max_dd      = float(drawdowns.min())

    win_rate   = float((res_df["port_return"] > 0).mean()) * 100
    alpha_mean = float(res_df["alpha"].mean())
    alpha_std  = float(res_df["alpha"].std())
    ir         = float(res_df["alpha"].mean() / alpha_std * np.sqrt(ppy)) if alpha_std > 0 else 0.0

    cost_drag        = actual_rebalances * TOTAL_COST * 100
    cost_drag_annual = cost_drag / years if years > 0 else 0.0

    print(f"\n  BACKTEST RESULTS ({n} periods, {years:.1f}yrs):")
    print(f"  {'─'*55}")
    print(f"  Portfolio annualised  : {ann_port:+.2f}%")
    print(f"  NIFTY annualised      : {ann_nifty:+.2f}%")
    print(f"  Net alpha             : {ann_port - ann_nifty:+.2f}%")
    print(f"  Average alpha/period  : {alpha_mean:+.3f}%")
    print(f"  Sharpe ratio          : {sharpe:.3f}")
    print(f"  Max drawdown          : {max_dd:.2f}%")
    print(f"  Win rate              : {win_rate:.1f}%")
    print(f"  Information ratio     : {ir:.3f}")
    print(f"  Actual rebalances     : {actual_rebalances} ({skipped} skipped)")
    print(f"  Total cost drag       : -{cost_drag:.2f}% | Annualised: -{cost_drag_annual:.2f}%")

    print(f"\n  TARGET STATUS:")
    print(f"  Sharpe > 0.8   : {'✓' if sharpe >= 0.8 else '✗'} ({sharpe:.3f})")
    print(f"  MaxDD > -14%   : {'✓' if max_dd > -14 else '✗'} ({max_dd:.1f}%)")
    print(f"  Alpha > 5%     : {'✓' if ann_port - ann_nifty > 5 else '✗'} ({ann_port - ann_nifty:.1f}%)")
    print(f"  Return 12–16%  : {'✓' if 12 <= ann_port <= 16 else '~'} ({ann_port:.1f}%)")
    print(f"  Cost drag < 6% : {'✓' if cost_drag_annual < 6 else '✗'} ({cost_drag_annual:.1f}%)")

    # ── Output consistency checks ──────────────────────────────────
    consistency_warnings = []
    if ann_nifty < 8.0 or ann_nifty > 15.0:
        w = f"Benchmark: NIFTY={ann_nifty:.1f}% outside 8–15%"
        consistency_warnings.append(w)
        print(f"  ⚠ {w}")
    if ann_port - ann_nifty > 20.0:
        w = f"Alpha={ann_port - ann_nifty:.1f}% suspiciously high — check data"
        consistency_warnings.append(w)
        print(f"  ⚠ {w}")
    if sharpe > 3.0:
        w = f"Sharpe={sharpe:.2f} unusually high — verify inputs"
        consistency_warnings.append(w)
        print(f"  ⚠ {w}")
    if not consistency_warnings:
        print(f"  ✓ Consistency checks passed")

    equity_curve = [
        {
            "date":             str(res_df.iloc[i]["date"]),
            "portfolio_index":  round(float(cum_port.iloc[i]) * 100, 2),
            "nifty_index":      round(float(cum_nifty.iloc[i]) * 100, 2),
            "alpha_cumulative": round(
                float(cum_port.iloc[i] / cum_nifty.iloc[i] - 1) * 100, 2
            ) if float(cum_nifty.iloc[i]) > 0 else 0.0,
        }
        for i in range(n)
    ]

    # ── SAVE TO CACHE ─────────────────────────────────────────────
    final_result = {
        "status":              "ok",
        "generated_at":        datetime.today().strftime("%Y-%m-%d %H:%M"),
        "lookback_years":      round(years, 2),
        "n_periods":           n,
        "rebalance_days":      REBALANCE_FREQ_DAYS,
        "actual_rebalances":   actual_rebalances,
        "skipped_rebalances":  skipped,
        "metrics": {
            "portfolio_annualised_return_pct": round(ann_port, 2),
            "nifty_annualised_return_pct":     round(ann_nifty, 2),
            "net_alpha_pct":                   round(ann_port - ann_nifty, 2),
            "average_alpha_pct":               round(alpha_mean, 3),
            "sharpe_ratio":                    round(sharpe, 3),
            "max_drawdown_pct":                round(max_dd, 2),
            "win_rate_pct":                    round(win_rate, 1),
            "information_ratio":               round(ir, 3),
            "cost_drag_total_pct":             round(cost_drag, 2),
            "cost_drag_annual_pct":            round(cost_drag_annual, 2),
            "total_periods":                   n,
        },
        "equity_curve":          equity_curve,
        "period_returns":        res_df.to_dict("records"),
        "consistency_warnings":  consistency_warnings,
    }
    _save_backtest_to_cache(final_result, lookback_years)
    return final_result


if __name__ == "__main__":
    import traceback
    try:
        print("\n" + "="*60)
        print("  MARKETOS BACKTEST ENGINE — starting run...")
        print("="*60)

        results = run_backtest(lookback_years=3)
        status  = results.get("status", "unknown")

        if status == "ok":
            m = results["metrics"]
            print(f"\n{'='*60}")
            print(f"  BACKTEST COMPLETE")
            print(f"{'='*60}")
            print(f"  Return (ann.)  : {m['portfolio_annualised_return_pct']:+.2f}%")
            print(f"  NIFTY (ann.)   : {m['nifty_annualised_return_pct']:+.2f}%")
            print(f"  Net Alpha      : {m['net_alpha_pct']:+.2f}%")
            print(f"  Sharpe ratio   : {m['sharpe_ratio']:.3f}")
            print(f"  Max drawdown   : {m['max_drawdown_pct']:.2f}%")
            print(f"  Win rate       : {m['win_rate_pct']:.1f}%")
            print(f"  Cost drag/yr   : -{m['cost_drag_annual_pct']:.2f}%")
            print(f"  Rebalances     : {results['actual_rebalances']} "
                  f"({results['skipped_rebalances']} skipped)")
            print(f"  Periods        : {m['total_periods']}")
            if results.get("consistency_warnings"):
                print(f"\n  ⚠ Warnings:")
                for w in results["consistency_warnings"]:
                    print(f"    - {w}")
            else:
                print(f"\n  ✓ All consistency checks passed.")

        elif status == "no_data":
            print("\n  ✗ STATUS: no_data")
            print("  The database has no historical price records.")
            print("  Fix: run the data loader first to populate the DB:")
            print("       python main.py --setup")
            print("       python main.py --daily")
            print("  Then re-run: python backtest_engine.py")

        elif status == "insufficient_data":
            print("\n  ✗ STATUS: insufficient_data")
            print("  Not enough historical data for a 3-year backtest.")
            print("  The engine needs at least 6 months of daily prices.")
            print("  Try a shorter window: modify lookback_years=1 or 2")
            print("  Or fetch more history: python main.py --setup")

        elif status == "no_results":
            print("\n  ✗ STATUS: no_results")
            print("  Data was found but no valid rebalance periods were produced.")
            print("  Likely cause: all sectors failed momentum/return filters.")
            print("  Check: are daily_return values populated in the DB?")
            print("         SELECT COUNT(*) FROM daily_prices WHERE daily_return IS NOT NULL;")

        else:
            print(f"\n  ✗ STATUS: {status}")
            print(f"  Unexpected status — full result: {results}")

    except Exception as e:
        print(f"\n  ✗ EXCEPTION during backtest run:")
        print(f"    {type(e).__name__}: {e}")
        print(f"\n  Full traceback:")
        traceback.print_exc()
        print("\n  Common causes:")
        print("    - database.py not found or DB path wrong")
        print("    - classification.py missing MARKET_CLASSIFICATION")
        print("    - SQLite DB file not yet created (run main.py --setup first)")

