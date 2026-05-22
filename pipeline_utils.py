# pipeline_utils.py
# MarketOS — Central Pipeline Utilities  [SECTION 9 — Single Source of Truth]
#
# MANDATORY: Every engine imports from here — NO LOCAL OVERRIDES.
#
# Provides:
#   get_pipeline_date()             → date  (single calendar authority)
#   get_nifty_return_from_db(date)  → (ret_pct, is_valid, nifty_level, nifty_pts)
#   validate_nifty_return(ret)      → bool  (Part 8 — global guard)
#
# Design rules:
#   - get_pipeline_date() uses market_calendar.get_last_trading_day()
#   - get_nifty_return_from_db() is the ONLY place NIFTY return is computed
#   - All engines call these functions — never derive NIFTY independently
#   - duplicate-close detection built in (returns None on stale intraday data)

from __future__ import annotations
import sys
from datetime import date, datetime, timedelta
from typing import Optional, Tuple
import warnings
warnings.filterwarnings("ignore")

# Ensure UTF-8 output on standard streams (especially on Windows)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────
# PART 1 — SINGLE PIPELINE DATE
# ─────────────────────────────────────────────────────────────────

def get_pipeline_date() -> date:
    """
    SINGLE SOURCE OF TRUTH for the pipeline date.

    Returns the last completed NSE trading day from market_calendar.
    ALL engines must call this instead of:
      - datetime.today().date()
      - get_data_status()["pipeline_date"]
      - any local date derivation

    Falls back to datetime.today().date() - 1 if market_calendar unavailable.
    """
    try:
        from market_calendar import get_last_trading_day
        pipeline_dt = get_last_trading_day()
        return pipeline_dt
    except ImportError:
        # Fallback: walk back from today to find a weekday
        d = datetime.today().date() - timedelta(days=1)
        for _ in range(7):
            if d.weekday() < 5:
                return d
            d -= timedelta(days=1)
        return datetime.today().date() - timedelta(days=1)


# ─────────────────────────────────────────────────────────────────
# PART 2 — SINGLE NIFTY SOURCE
# ─────────────────────────────────────────────────────────────────

def get_nifty_return_from_db(
    pipeline_date: Optional[date] = None,
) -> Tuple[Optional[float], bool, float, float]:
    """
    SINGLE NIFTY COMPUTATION — the ONLY authorised place to compute NIFTY return.

    Queries the MacroData table for the 2 most recent rows on or before
    pipeline_date, then computes close-to-close return.

    Returns:
        (nifty_ret_pct, is_valid, nifty_level, nifty_points)

        nifty_ret_pct : float | None   — percentage return, e.g. -0.74
        is_valid      : bool           — False if data is stale/duplicate/missing
        nifty_level   : float          — today's NIFTY close
        nifty_points  : float          — today_close - prev_close

    Failure modes (all return (None, False, 0.0, 0.0)):
        - Fewer than 2 rows in DB
        - today_close == prev_close  (duplicate / intraday stale data)
        - today_close <= 0 (corrupt data)

    Part 8 guard: if abs(nifty_ret_pct) >= 5.0 → marks is_valid = False
                  (a ≥5% single-day NIFTY move is almost certainly a data error)
    """
    if pipeline_date is None:
        pipeline_date = get_pipeline_date()

    from database import get_session, MacroData

    session = get_session()
    try:
        rows = (
            session.query(MacroData)
            .filter(MacroData.date <= pipeline_date)
            .order_by(MacroData.date.desc())
            .limit(5)           # fetch 5, take first 2 valid closes
            .all()
        )
    except Exception as exc:
        print(f"  [pipeline_utils] DB error loading MacroData: {exc}")
        return None, False, 0.0, 0.0
    finally:
        session.close()

    if not rows:
        print("  [pipeline_utils] [WARNING] No MacroData rows found")
        return None, False, 0.0, 0.0

    # Filter to rows with valid close prices
    valid_rows = [r for r in rows if (r.nifty_close or 0.0) > 0]

    if len(valid_rows) < 2:
        print(f"  [pipeline_utils] [WARNING] Insufficient valid NIFTY closes "
              f"(need >=2, found {len(valid_rows)})")
        level = float(valid_rows[0].nifty_close) if valid_rows else 0.0
        return None, False, level, 0.0

    # rows are ordered DESC — index 0 is the most recent
    today_row = valid_rows[0]
    prev_row  = valid_rows[1]

    today_close = float(today_row.nifty_close)
    prev_close  = float(prev_row.nifty_close)
    today_date  = today_row.date
    prev_date   = prev_row.date

    # ── Duplicate / stale detection ──────────────────────────────
    if abs(today_close - prev_close) < 0.01:
        print(f"  [pipeline_utils] [WARNING] Duplicate NIFTY values detected: "
              f"{today_date}={today_close:.2f} == {prev_date}={prev_close:.2f}")
        print(f"  [pipeline_utils] [WARNING] Intraday or stale data — returning None")
        return None, False, today_close, 0.0

    # ── Compute return ────────────────────────────────────────────
    nifty_ret_pct = ((today_close / prev_close) - 1.0) * 100.0
    nifty_points  = today_close - prev_close

    print(f"  [pipeline_utils] NIFTY {prev_date}={prev_close:,.2f} -> "
          f"{today_date}={today_close:,.2f} | return={nifty_ret_pct:+.4f}%")

    # ── Part 8: Plausibility guard ────────────────────────────────
    if abs(nifty_ret_pct) >= 5.0:
        print(f"  [pipeline_utils] [WARNING] NIFTY return {nifty_ret_pct:+.2f}% >= 5% — "
              f"likely data error. Marking is_valid=False.")
        return nifty_ret_pct, False, today_close, nifty_points

    return round(nifty_ret_pct, 4), True, round(today_close, 2), round(nifty_points, 2)


# ─────────────────────────────────────────────────────────────────
# PART 8 — GLOBAL VALIDATION GUARD
# ─────────────────────────────────────────────────────────────────

def validate_nifty_return(nifty_return: Optional[float], context: str = "") -> bool:
    """
    Part 8 — Global guard before any engine uses a NIFTY return.

    Asserts:
      - nifty_return is not None
      - abs(nifty_return) < 5.0%  (implausible threshold)

    Raises ValueError on hard failure; returns True on pass.
    context: caller name for logging (e.g. "macro_engine", "alpha_engine")
    """
    tag = f"[{context}] " if context else ""

    if nifty_return is None:
        raise ValueError(
            f"{tag}CRITICAL: nifty_return is None — "
            "pipeline cannot proceed with missing NIFTY data."
        )

    if abs(nifty_return) >= 5.0:
        raise ValueError(
            f"{tag}CRITICAL: nifty_return={nifty_return:+.2f}% exceeds ±5% guard — "
            "data integrity failure. Abort pipeline."
        )

    return True


# ─────────────────────────────────────────────────────────────────
# DIAGNOSTIC
# ─────────────────────────────────────────────────────────────────

def log_pipeline_state(context: str = "") -> dict:
    """
    Logs and returns current pipeline state.
    Call at the start of any engine for consistent diagnostics.
    """
    pipeline_date = get_pipeline_date()
    nifty_ret, is_valid, nifty_level, nifty_pts = get_nifty_return_from_db(pipeline_date)

    state = {
        "pipeline_date": pipeline_date,
        "nifty_return":  nifty_ret,
        "is_valid":      is_valid,
        "nifty_level":   nifty_level,
        "nifty_points":  nifty_pts,
    }

    tag = f"[{context}] " if context else ""
    print(f"\n  {tag}Pipeline state:")
    print(f"    Date        : {pipeline_date}")
    print(f"    NIFTY level : {nifty_level:,.2f}")
    print(f"    NIFTY return: {nifty_ret:+.4f}%" if nifty_ret is not None else "    NIFTY return: None")
    print(f"    is_valid    : {'YES' if is_valid else 'NO'}")

    return state


if __name__ == "__main__":
    print("=== pipeline_utils self-test ===")
    state = log_pipeline_state("self-test")
    print(f"\nResult: {state}")
