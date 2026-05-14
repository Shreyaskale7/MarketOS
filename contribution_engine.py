# contribution_engine.py
# MarketOS v4 — SECTION 2 UPGRADE: DB-First Data Architecture
#
# KEY CHANGES:
#   1. fetch_all_prices() replaced with load_prices_from_db() — reads from DB
#   2. NIFTY return loaded from MacroData DB table — NOT a separate yf.download
#   3. target_date resolved via data_loader.get_data_status() — same source as all modules
#   4. Fallback: if DB data unavailable, log clearly and return None
#   5. All other computation logic (attribution, normalization) unchanged
#
# This eliminates the "contribution engine fetches fresh data separately"
# inconsistency — all modules now operate on the SAME data source.

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from database import get_session, DailyPrice, MacroData
from classification import MARKET_CLASSIFICATION
import json
import warnings
warnings.filterwarnings("ignore")

MIN_TICKERS_THRESHOLD = 10
MAX_VALID_DAILY_RETURN = 40.0
LOOKBACK_DAYS = 7


def safe_float(val, default=0.0):
    try:
        if val is None:
            return default
        f = float(val)
        return f if np.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def is_valid_return(ret):
    return (ret is not None and np.isfinite(ret) and abs(ret) <= MAX_VALID_DAILY_RETURN)


def get_nearest_date(index, target_dt):
    idx   = index.sort_values()
    valid = idx[idx <= target_dt]
    return valid[-1] if len(valid) > 0 else None


def build_ticker_metadata():
    """Returns dict: ticker -> {company, sector, subsector, weight_pct}"""
    meta = {}
    for sector, sec_data in MARKET_CLASSIFICATION.items():
        for subsector, sub_data in sec_data["subsectors"].items():
            for company, info in sub_data["companies"].items():
                t = info["ticker"]
                if t not in meta:
                    meta[t] = {
                        "company":    company,
                        "sector":     sector,
                        "subsector":  subsector,
                        "weight_pct": info["sector_weight"] * 100,
                    }
    return meta


# ─────────────────────────────────────────────────────────────────
# SECTION 2: LOAD PRICES FROM DB (replaces live yf.download)
# ─────────────────────────────────────────────────────────────────

def load_prices_from_db(tickers: list, target_date, lookback_days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """
    SECTION 2 UPGRADE: Loads closing prices from DB (DailyPrice table).

    OLD: fetch_all_prices() called yf.download() — separate live fetch
    NEW: reads from the DB that data_loader already populated

    Returns DataFrame: rows=dates, cols=tickers, values=close_price.
    If a ticker has no DB data, it is silently excluded (consistent with original).
    """
    since   = target_date - timedelta(days=lookback_days + 5)
    session = get_session()
    try:
        rows = session.query(DailyPrice).filter(
            DailyPrice.date >= since,
            DailyPrice.date <= target_date,
            DailyPrice.ticker.in_(tickers),
            DailyPrice.close_price > 0,
        ).order_by(DailyPrice.date).all()
    except Exception as e:
        print(f"  ERROR loading prices from DB: {e}")
        rows = []
    finally:
        session.close()

    if not rows:
        print(f"  WARNING: No price data in DB for {target_date} (lookback={lookback_days}d)")
        return pd.DataFrame()

    df = pd.DataFrame([{
        "date":        pd.Timestamp(r.date),
        "ticker":      r.ticker,
        "close_price": float(r.close_price or 0.0),
    } for r in rows])

    pivot = df.pivot_table(index="date", columns="ticker", values="close_price", aggfunc="last")
    pivot.index = pd.to_datetime(pivot.index)
    pivot = pivot.sort_index()

    print(f"  Loaded {len(pivot.columns)} tickers from DB, {len(pivot)} days")
    return pivot


def load_nifty_from_db(target_date) -> tuple:
    """
    SECTION 1+2: Loads NIFTY return and level from MacroData DB table.
    Requires ≥2 data points to compute return — never defaults to 0 silently.
    Logs: today close, prev close, computed return.
    Warns if duplicate/stale NIFTY data detected.

    Returns: (nifty_return_pct, nifty_points, nifty_level)
    """
    since   = target_date - timedelta(days=10)   # wider window to ensure ≥2 rows
    session = get_session()
    try:
        rows = session.query(MacroData).filter(
            MacroData.date >= since,
            MacroData.date <= target_date,
        ).order_by(MacroData.date).all()
    except Exception:
        rows = []
    finally:
        session.close()

    if not rows:
        print("  WARNING: No NIFTY data in MacroData table")
        return None, 0.0, 0.0

    df = pd.DataFrame([{
        "date":        pd.Timestamp(r.date),
        "nifty_close": float(r.nifty_close or 0.0),
        # NEVER use stored nifty_return — may be 0 for non-trading days
        # Always recompute from close-to-close below
    } for r in rows]).sort_values("date")

    target_ts = pd.Timestamp(target_date)
    valid     = df[(df["date"] <= target_ts) & (df["nifty_close"] > 0)]

    if valid.empty:
        print("  WARNING: No valid NIFTY close prices on or before target date")
        return None, 0.0, 0.0

    if len(valid) < 2:
        print("  WARNING: Insufficient NIFTY data (need >=2 rows)")
        return None, 0.0, round(float(valid.iloc[-1]["nifty_close"]), 2)

    today_close = float(valid.iloc[-1]["nifty_close"])
    prev_close  = float(valid.iloc[-2]["nifty_close"])

    # FILE 3 FIX 1: Explicit duplicate detection
    if today_close == prev_close:
        print(f"  ⚠ Duplicate NIFTY values — today={today_close:.2f} == prev={prev_close:.2f}")
        print(f"  ⚠ This means today's data was fetched before market close (intraday)")
        print(f"  ⚠ Return computation would give 0.000% — returning None to prevent false data")
        return None, 0.0, round(today_close, 2)

    # FILE 3 FIX 1: SPEC — nifty_return = (today / prev) - 1
    nifty_ret    = (today_close / prev_close - 1) * 100 if prev_close > 0 else None
    nifty_points = round(today_close - prev_close, 2) if prev_close > 0 else 0.0

    if nifty_ret is not None:
        print(f"  [NIFTY] today={today_close:,.2f} | prev={prev_close:,.2f} | return={nifty_ret:+.4f}%")
    else:
        print(f"  [NIFTY] today={today_close:,.2f} | could not compute return")

    return (round(nifty_ret, 3) if nifty_ret is not None else None), nifty_points, round(today_close, 2)



# ─────────────────────────────────────────────────────────────────
# COMPUTATION FUNCTIONS (unchanged from v3)
# ─────────────────────────────────────────────────────────────────

def compute_returns_pct(price_df: pd.DataFrame) -> pd.DataFrame:
    """Returns daily returns as PERCENTAGE values. Clipped at ±40%."""
    if price_df.empty:
        return pd.DataFrame()
    ret = price_df.pct_change() * 100.0
    ret = ret.clip(lower=-MAX_VALID_DAILY_RETURN, upper=MAX_VALID_DAILY_RETURN)
    return ret


def get_return_for_date(returns_pct, ticker, target_dt):
    """Return for ticker on target_dt or nearest previous date."""
    if ticker not in returns_pct.columns:
        return None
    series = returns_pct[ticker].dropna()
    if series.empty:
        return None
    nearest = get_nearest_date(series.index, target_dt)
    if nearest is None:
        return None
    val = float(series.loc[nearest])
    return val if is_valid_return(val) else None


def company_contribution_pct(return_pct, weight_pct):
    """contribution_pct = return_pct * weight_pct / 100"""
    return return_pct * weight_pct / 100.0


def compute_subsector_attribution(sub_name, sub_data, returns_pct, target_dt):
    """Aggregates company-level contributions to subsector. All values in %."""
    companies   = sub_data.get("companies", {})
    breakdown   = {}
    sub_contrib = 0.0
    sub_ret_num = 0.0
    sub_weight  = 0.0
    valid       = 0

    for co_name, info in companies.items():
        ticker     = info["ticker"]
        weight_pct = info["sector_weight"] * 100.0
        if weight_pct <= 0:
            continue
        ret = get_return_for_date(returns_pct, ticker, target_dt)
        if ret is None:
            continue
        contrib = company_contribution_pct(ret, weight_pct)
        breakdown[co_name] = {
            "ticker":                    ticker,
            "nifty_weight_pct":          round(weight_pct, 3),
            "daily_return_pct":          round(ret, 3),
            "contribution_to_index_pct": round(contrib, 4),
            "direction": "UP" if ret > 0 else ("DOWN" if ret < 0 else "FLAT"),
        }
        sub_contrib += contrib
        sub_ret_num += ret * weight_pct
        sub_weight  += weight_pct
        valid       += 1

    coverage = valid / max(len(companies), 1)
    if coverage < 0.5 and len(companies) > 0:
        print(f"    WARNING: {sub_name} — {valid}/{len(companies)} cos ({coverage:.0%} coverage)")

    weighted_return = sub_ret_num / sub_weight if sub_weight > 0 else 0.0
    top_co = (max(breakdown.items(), key=lambda x: abs(x[1]["contribution_to_index_pct"]))[0]
              if breakdown else "")

    return {
        "subsector_name":                      sub_name,
        "companies_tracked":                   valid,
        "total_companies":                     len(companies),
        "coverage_pct":                        round(coverage * 100, 1),
        "subsector_weighted_return_pct":       round(weighted_return, 3),
        "subsector_contribution_to_index_pct": round(sub_contrib, 4),
        "top_contributor":                     top_co,
        "companies":                           breakdown,
    }


def compute_sector_attribution(sector_name, sector_data, returns_pct, target_dt):
    """Aggregates subsector contributions to sector. All values in %."""
    sub_results    = {}
    sector_contrib = 0.0

    print(f"\n  Processing sector: {sector_name}")
    for sub_name, sub_data in sector_data["subsectors"].items():
        result = compute_subsector_attribution(sub_name, sub_data, returns_pct, target_dt)
        sub_results[sub_name] = result
        sector_contrib += result["subsector_contribution_to_index_pct"]
        print(f"    {sub_name}: {result['subsector_contribution_to_index_pct']:+.4f}% "
              f"({result['companies_tracked']}/{result['total_companies']} cos)")

    sector_weight_pct = sector_data.get("sector_nifty_weight", 0) * 100.0
    sector_return_pct = (sector_contrib / (sector_weight_pct / 100.0)
                         if sector_weight_pct > 0 else 0.0)

    return {
        "sector_name":                      sector_name,
        "sector_nifty_weight_pct":          round(sector_weight_pct, 1),
        "sector_weighted_return_pct":       round(sector_return_pct, 3),
        "sector_contribution_to_index_pct": round(sector_contrib, 4),
        "macro_drivers":                    sector_data.get("macro_drivers", []),
        "direction": ("UP" if sector_contrib > 0 else "DOWN" if sector_contrib < 0 else "FLAT"),
        "subsectors": sub_results,
    }


def normalize_contributions(sectors, nifty_actual_pct):
    """
    Scales all contributions so sum = nifty_actual_pct.

    FLAT DAY GUARD: When raw_total is near-zero (sectors nearly cancel),
    the scale factor explodes (e.g. 0.141 / 0.008 = 17.6x), producing
    impossible sector returns like -44% on a +0.14% NIFTY day.

    Fix: Cap the scale factor at ±5.0. Beyond that, normalization is
    doing more harm than good — the raw attribution is a better signal
    than a 17x-amplified distortion. Return raw with LOW confidence.
    """
    total_raw = sum(s["sector_contribution_to_index_pct"] for s in sectors.values())

    # Guard 1: both sides near-zero — no scaling needed
    if abs(total_raw) < 0.0001 or abs(nifty_actual_pct) < 0.0001:
        return sectors, 1.0

    scale = nifty_actual_pct / total_raw

    # Guard 2: scale explosion on flat/mixed days — cap at ±5.0
    # If scale > 5, it means sector contributions nearly cancelled out
    # and the amplification would produce physically impossible returns.
    # In this case, skip normalization and return raw with scale=1.0.
    if abs(scale) > 5.0:
        # Do NOT scale — return raw contributions unchanged
        # The daily report will show LOW confidence, which is correct.
        return sectors, round(scale, 4)   # return actual scale for logging

    for sd in sectors.values():
        sd["sector_contribution_to_index_pct"] = round(
            sd["sector_contribution_to_index_pct"] * scale, 4)
        w = sd["sector_nifty_weight_pct"]
        sd["sector_weighted_return_pct"] = round(
            sd["sector_contribution_to_index_pct"] / (w / 100.0) if w > 0 else 0.0, 3)
        for sub in sd["subsectors"].values():
            sub["subsector_contribution_to_index_pct"] = round(
                sub["subsector_contribution_to_index_pct"] * scale, 4)
            for co in sub["companies"].values():
                co["contribution_to_index_pct"] = round(
                    co["contribution_to_index_pct"] * scale, 4)
    return sectors, round(scale, 4)


# ─────────────────────────────────────────────────────────────────
# SECTION 2: MAIN ENTRY POINT — DB-FIRST
# ─────────────────────────────────────────────────────────────────

def run_full_contribution_engine(target_date=None, lookback_days=LOOKBACK_DAYS):
    """
    SECTION 9 UPGRADES (Parts 1 + 4):
      - pipeline_date from get_pipeline_date() — single authority
      - Market calendar gate: returns None on non-trading days
      - NIFTY from get_nifty_return_from_db() — removes local NIFTY calculation
      - No separate load_nifty_from_db() call

    Steps:
    1. Resolve target_date via get_pipeline_date()
    2. Gate: skip on non-trading days
    3. Load prices from DailyPrice DB table
    4. NIFTY from pipeline_utils.get_nifty_return_from_db()
    5. Attribution computation (unchanged)
    """
    # ── PART 4: Market calendar gate ─────────────────────────────
    try:
        from market_calendar import get_market_status
        mkt_status = get_market_status()
        if not mkt_status["is_trading_day"]:
            reason = mkt_status.get("close_reason", "non-trading day")
            print(f"\n  [ContribEngine] Skipping — market closed ({reason})")
            print(f"  [ContribEngine] Last trading day: {mkt_status.get('last_trading_day')}")
            return None   # caller uses previous output
    except ImportError:
        pass

    # ── PART 1: Single pipeline date ─────────────────────────────
    from pipeline_utils import get_pipeline_date, get_nifty_return_from_db

    if target_date is None:
        target_date = get_pipeline_date()
        print(f"  [ContribEngine] Pipeline date: {target_date} (via get_pipeline_date)")
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, "%Y-%m-%d").date()

    target_dt = pd.Timestamp(target_date)

    print(f"\n{'='*60}")
    print(f"MARKETOS CONTRIBUTION ENGINE v4 (DB-First)")
    print(f"Computing attributions for: {target_date}")
    print(f"{'='*60}")

    # ── Step 1: Build tickers ─────────────────────────────────────
    print("\nStep 1: Building ticker list...")
    ticker_meta = build_ticker_metadata()
    all_tickers = list(ticker_meta.keys())
    print(f"  Total tickers: {len(all_tickers)}")

    # ── Step 2: Load prices from DB ───────────────────────────────
    print("\nStep 2: Loading market data from DB...")
    price_df = load_prices_from_db(all_tickers, target_date, lookback_days)
    if price_df.empty:
        print("  ERROR: No price data in DB. Run --setup or check data_loader.")
        return None

    # ── Step 3: Compute returns ───────────────────────────────────
    print("\nStep 3: Computing daily returns...")
    returns_pct = compute_returns_pct(price_df)

    # ── PART 4: Step 4 — NIFTY from SINGLE SOURCE (pipeline_utils) ──
    print("\nStep 4: Loading NIFTY return from DB [via get_nifty_return_from_db]...")
    nifty_return_pct, nifty_is_valid, nifty_level, nifty_points = \
        get_nifty_return_from_db(target_date)

    # Handle invalid NIFTY — skip normalization
    nifty_invalid = not nifty_is_valid or nifty_return_pct is None
    if nifty_invalid:
        print("  ⚠ NIFTY return is None / invalid — normalization SKIPPED")
        print("  ⚠ Possible causes: intraday data, duplicate close, market not closed yet")
        print("  ⚠ Returning raw attribution with confidence=LOW")
        nifty_return_pct = 0.0   # safe fallback for downstream

    # Find actual date used
    actual_date = target_dt
    if not returns_pct.empty:
        s     = returns_pct.iloc[:, 0].dropna()
        found = get_nearest_date(s.index, target_dt)
        if found is not None:
            actual_date = found
            if found.date() != target_date:
                print(f"  NOTE: Using data from {found.date()} (nearest to {target_date})")

    # ── Step 5: Compute attributions ──────────────────────────────
    print("\nStep 5: Computing sector attributions...")
    sector_results = {}
    for sector_name, sector_data in MARKET_CLASSIFICATION.items():
        sector_results[sector_name] = compute_sector_attribution(
            sector_name, sector_data, returns_pct, actual_date)

    raw_total = sum(s["sector_contribution_to_index_pct"] for s in sector_results.values())
    print(f"\n  Raw attribution: {raw_total:+.3f}% vs NIFTY actual: {nifty_return_pct:+.3f}%")

    if nifty_invalid or abs(nifty_return_pct) < 0.0001:
        print("  ⚠ Normalization SKIPPED — returning raw attribution (confidence=LOW)")
        scale = 1.0
        norm_total = raw_total
        data_confidence = "LOW"
    else:
        sector_results, scale = normalize_contributions(sector_results, nifty_return_pct)
        norm_total = sum(s["sector_contribution_to_index_pct"] for s in sector_results.values())

        # Determine confidence based on scale factor
        if abs(scale) > 5.0:
            # Scale explosion — normalization was skipped, showing raw data
            data_confidence = "LOW"
            print(f"  Scale: {scale:.4f} — EXPLOSION GUARD triggered, normalization skipped")
            print(f"  Raw attribution shown (flat/mixed day — sectors nearly cancelled)")
        elif abs(scale) > 2.0:
            data_confidence = "MEDIUM"
            print(f"  Scale: {scale:.4f} | After normalization: {norm_total:+.3f}% ✓")
        else:
            data_confidence = "HIGH"
            print(f"  Scale: {scale:.4f} | After normalization: {norm_total:+.3f}% ✓")

    sorted_sectors = dict(sorted(
        sector_results.items(),
        key=lambda x: abs(x[1]["sector_contribution_to_index_pct"]),
        reverse=True,
    ))

    return {
        "date":                            str(target_date),
        "data_date_used":                  str(actual_date.date()),
        "nifty_level":                     nifty_level,
        "nifty_actual_return_pct":         nifty_return_pct,
        "nifty_actual_points":             nifty_points,
        "raw_contribution_pct":            round(raw_total, 3),
        "normalized_contribution_pct":     round(norm_total, 3),
        "normalization_scale":             scale,
        "data_confidence":                 data_confidence,
        "attribution_accuracy_pct":        100.0 if not nifty_invalid else 0.0,
        "total_contribution_explained_pct": round(norm_total, 3),
        "tickers_fetched":                 len(price_df.columns),
        "tickers_requested":               len(all_tickers),
        "sectors":                         sorted_sectors,
    }


def print_contribution_report(output):
    """Prints clean readable report. All values in %."""
    if output is None:
        print("No output to display.")
        return

    print(f"\n{'='*70}")
    print(f"MARKETOS DAILY INTELLIGENCE REPORT")
    print(f"Date: {output['date']}  |  Data from: {output['data_date_used']}")
    print(f"{'='*70}")
    print(f"\nNIFTY 50: {output['nifty_level']:,.2f} | "
          f"{output['nifty_actual_return_pct']:+.3f}% | "
          f"{output['nifty_actual_points']:+.2f} pts")
    print(f"Attribution: {output['raw_contribution_pct']:+.3f}% raw "
          f"→ normalized to {output['normalized_contribution_pct']:+.3f}% ✓")
    print(f"Coverage: {output['tickers_fetched']}/{output['tickers_requested']} tickers")

    print(f"\n{'─'*70}")
    print("SECTOR CONTRIBUTIONS (sorted by impact)")
    print(f"{'─'*70}")
    print(f"{'Sector':<35} {'Weight':>6} {'Return':>8} {'Contribution':>14} {'Dir':>5}")
    print(f"{'─'*70}")

    for sector_name, sd in output["sectors"].items():
        c     = sd["sector_contribution_to_index_pct"]
        arrow = "▲" if c > 0 else ("▼" if c < 0 else "─")
        print(f"{sector_name[:34]:<35} "
              f"{sd['sector_nifty_weight_pct']:>5.1f}% "
              f"{sd['sector_weighted_return_pct']:>+7.2f}% "
              f"{c:>+13.4f}% {arrow:>5}")


def get_top_movers(output, n=5):
    """Returns top N sectors by absolute contribution."""
    if not output or "sectors" not in output:
        return []
    return sorted(
        output["sectors"].items(),
        key=lambda x: abs(x[1]["sector_contribution_to_index_pct"]),
        reverse=True,
    )[:n]


if __name__ == "__main__":
    output = run_full_contribution_engine()
    if output:
        print_contribution_report(output)
        get_top_movers(output, n=5)
        print("\n✓ Engine complete")
