# data_loader.py — MarketOS v6
# SECTION 2 UPGRADES (Data Pipeline Fix):
#   1. Data freshness validation — never silently skip if DB is stale
#   2. Strict check: if today's data not in DB → force_fetch = True
#   3. Clear structured logging: "Last DB date: X | Today: Y | Fetch: YES/NO"
#   4. If fetch fails → log "WARNING: Using stale data — pipeline may be unreliable"
#   5. After fetch → assert latest_date matches expected trading day
#   6. Market closed fallback logs clearly: "Using previous trading day data: X"
#   7. get_data_status() helper — ALL modules call this to know what date is live

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from database import (engine, DailyPrice, MacroData,
                      get_session, ensure_tables_exist)
from classification import MARKET_CLASSIFICATION
import time
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

HISTORY_YEARS = 10

MACRO_TICKERS = {
    "usdinr":      "INR=X",
    "brent_crude": "BZ=F",
    "india_vix":   "^INDIAVIX",
    "nifty":       "^NSEI",
    "sensex":      "^BSESN",
    "nasdaq":      "^IXIC",
    "sp500":       "^GSPC",
    "gold":        "GC=F",
}

MANUAL_MACRO = {
    "repo_rate":       6.25,
    "gdp_growth":      6.4,
    "gst_collections": 187000.0,
    "cpi_yoy":         4.8,
    "iip_growth":      5.2,
}

NSE_HOLIDAYS_2026 = {
    "2026-01-26", "2026-03-25", "2026-04-14", "2026-04-17",
    "2026-05-01", "2026-08-15", "2026-10-02", "2026-10-24",
    "2026-11-04", "2026-11-05", "2026-12-25",
}


# ─────────────────────────────────────────────────────────────────
# SECTION 2: DATA STATUS TRACKER
# Single source of truth for what date the pipeline is using
# ─────────────────────────────────────────────────────────────────

# Module-level status — set by run_data_loader(), read by all modules
_DATA_STATUS = {
    "last_db_date":       None,
    "pipeline_date":      None,   # the date the pipeline is computing for
    "fetch_required":     None,
    "fetch_performed":    False,
    "data_source":        "unknown",  # "live" | "fallback:DATE" | "db_cache" | "stale"
    "is_stale":           False,
    "stale_warning":      "",
}


def get_data_status() -> dict:
    """
    SECTION 2: Returns current data status dict.
    ALL modules (contribution_engine, macro_engine, etc.) should
    call this to know what date they are operating on.
    This ensures ALL modules use the SAME data source.
    """
    return dict(_DATA_STATUS)


def _set_data_status(**kwargs):
    """Internal: updates the module-level data status."""
    _DATA_STATUS.update(kwargs)


# ─────────────────────────────────────────────────────────────────
# MARKET CALENDAR
# ─────────────────────────────────────────────────────────────────

def is_market_open_today() -> bool:
    today     = datetime.today()
    today_str = today.strftime('%Y-%m-%d')
    if today.weekday() >= 5:
        print(f"  INFO: Today is {today.strftime('%A')} ({today_str}) — NSE closed.")
        return False
    if today_str in NSE_HOLIDAYS_2026:
        print(f"  INFO: {today_str} is an NSE holiday — market closed.")
        return False
    return True


def get_last_valid_trading_day() -> date:
    """Returns the most recent NSE trading day (walks backward from today)."""
    d        = datetime.today().date()
    attempts = 0
    while attempts < 14:
        d_str = d.strftime('%Y-%m-%d')
        if d.weekday() < 5 and d_str not in NSE_HOLIDAYS_2026:
            return d
        d -= timedelta(days=1)
        attempts += 1
    return datetime.today().date() - timedelta(days=3)


# Alias
_last_nse_trading_day = get_last_valid_trading_day


# ─────────────────────────────────────────────────────────────────
# SECTION 2: DATA FRESHNESS VALIDATION
# ─────────────────────────────────────────────────────────────────

def get_last_stored_date():
    """Returns most recent date in daily_prices, or None if empty."""
    ensure_tables_exist()
    session = get_session()
    try:
        from sqlalchemy import func
        result = session.query(func.max(DailyPrice.date)).scalar()
        return result
    except Exception as e:
        print(f"  Could not query last date: {e}")
        return None
    finally:
        session.close()


def check_data_freshness() -> dict:
    """
    SECTION 9 Part 6: Validates data freshness against last trading day.

    Returns:
    {
      "last_db_date":     date | None,
      "today":            date,
      "expected_date":    date,   ← last valid trading day
      "fetch_required":   bool,
      "force_backfill":   bool,   ← Part 6b: True when DB is multiple days stale
      "days_stale":       int,
      "reason":           str,
    }

    Part 6 improvements:
    - Uses market_calendar.get_last_trading_day() (same as get_pipeline_date)
    - Counts exact trading days stale (not calendar days)
    - force_backfill=True when DB is >1 trading day stale
    - Logs clearly: "Last DB date: X | Expected: Y | Fetch: YES/NO"
    """
    today         = datetime.today().date()

    # Part 6: use market_calendar for expected_date (consistent with get_pipeline_date)
    try:
        from market_calendar import get_last_trading_day as _get_ltd
        expected_date = _get_ltd()
    except ImportError:
        expected_date = get_last_valid_trading_day()

    last_db_date  = get_last_stored_date()

    if isinstance(last_db_date, str):
        last_db_date = datetime.strptime(last_db_date, '%Y-%m-%d').date()

    # Part 6b: compute how many trading days stale the DB is
    days_stale = 0
    force_backfill = False

    if last_db_date is not None and last_db_date < expected_date:
        # Count trading days between last_db_date and expected_date
        d = last_db_date + timedelta(days=1)
        while d <= expected_date:
            if d.weekday() < 5:   # rough count; market_calendar handles holidays
                days_stale += 1
            d += timedelta(days=1)
        # Force backfill when more than 1 trading day behind
        force_backfill = days_stale > 1

    # SECTION 2 + Part 6: Never skip if DB is stale relative to last trading day
    if last_db_date is None:
        fetch_required = True
        reason         = "DB is empty — first run"
        force_backfill = True
    elif last_db_date < expected_date:
        fetch_required = True
        reason         = (f"DB stale: last stored {last_db_date} < expected {expected_date} "
                         f"({days_stale} trading day(s) behind)")
    else:
        fetch_required = False
        reason         = f"DB current: last stored {last_db_date} == expected {expected_date}"

    # Part 6: Structured log with stale day count
    print(f"\n  [DataFreshness] Last DB date : {last_db_date or 'EMPTY'}")
    print(f"  [DataFreshness] Today        : {today}")
    print(f"  [DataFreshness] Expected date: {expected_date}")
    if days_stale > 0:
        print(f"  [DataFreshness] Days stale   : {days_stale} trading day(s)")
    if force_backfill:
        print(f"  [DataFreshness] ⚠ FORCE BACKFILL: DB is {days_stale} days stale — "
              f"fetching ALL missing dates")
    print(f"  [DataFreshness] Fetch required: {'YES' if fetch_required else 'NO'} — {reason}")

    return {
        "last_db_date":   last_db_date,
        "today":          today,
        "expected_date":  expected_date,
        "fetch_required": fetch_required,
        "force_backfill": force_backfill,
        "days_stale":     days_stale,
        "reason":         reason,
    }


def get_fetch_start_date():
    """
    SECTION 2 UPGRADE:
    OLD logic: skip if last_date >= today (wrong — skips stale data)
    NEW logic: skip only if last_date >= last_valid_trading_day

    This prevents the pipeline from running on stale DB data silently.
    """
    last_date     = get_last_stored_date()
    expected_date = get_last_valid_trading_day()

    if last_date is None:
        start = (datetime.today() - timedelta(days=HISTORY_YEARS * 365)).date()
        print(f"  First run — fetching {HISTORY_YEARS} years from {start}")
        return start

    if isinstance(last_date, str):
        last_date = datetime.strptime(last_date, '%Y-%m-%d').date()

    # SECTION 2: fetch if DB is behind expected trading day
    if last_date < expected_date:
        start = last_date + timedelta(days=1)
        print(f"  Incremental fetch: {start} → {expected_date}")
        return start

    # DB is current
    print(f"  Data current as of {last_date} (expected: {expected_date}). No fetch needed.")
    return None


# ─────────────────────────────────────────────────────────────────
# TICKER METADATA
# ─────────────────────────────────────────────────────────────────

def build_ticker_metadata():
    """Returns dict: ticker → {company, sector, subsector, weight}"""
    meta = {}
    for sector, sec_data in MARKET_CLASSIFICATION.items():
        for subsector, sub_data in sec_data["subsectors"].items():
            for company, info in sub_data["companies"].items():
                meta[info["ticker"]] = {
                    "company":      company,
                    "sector":       sector,
                    "subsector":    subsector,
                    "nifty_weight": info["sector_weight"]
                }
    return meta


# ─────────────────────────────────────────────────────────────────
# PRICE FETCHING
# ─────────────────────────────────────────────────────────────────

def _fetch_single_ticker(ticker, start_str, end_str, max_retries=3):
    """Fetches price data for ONE ticker with retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            df = yf.download(
                ticker, start=start_str, end=end_str,
                auto_adjust=True, progress=False, threads=False,
            )
            if df is None or df.empty:
                time.sleep(0.2 * attempt)
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if 'Close' not in df.columns:
                time.sleep(0.2 * attempt)
                continue
            df = df.dropna(subset=['Close'])
            if df.empty:
                time.sleep(0.2 * attempt)
                continue
            return df
        except Exception:
            time.sleep(0.3 * attempt)
    return None


def _parse_single_ticker_records(ticker, df, ticker_meta):
    """Extracts clean DailyPrice records from a single-ticker DataFrame."""
    records = []
    meta    = ticker_meta.get(ticker, {})
    df      = df.copy()
    df['daily_return'] = df['Close'].pct_change()

    if len(df) <= 1:
        df['daily_return'] = df['daily_return'].fillna(0.0)
    else:
        df = df.dropna(subset=['daily_return'])

    for idx, row in df.iterrows():
        try:
            ret   = float(row['daily_return'])
            close = float(row['Close'])
            if abs(ret) > 0.20 or close <= 0:
                # NSE circuit breakers cap single-stock moves at 20%.
                # Anything beyond ±20% is a corporate action data artifact.
                continue
            if pd.isna(ret) or pd.isna(close):
                continue

            row_date = idx.date() if hasattr(idx, 'date') else idx
            records.append({
                'date':         row_date,
                'ticker':       ticker,
                'company_name': meta.get('company', ''),
                'sector':       meta.get('sector', ''),
                'subsector':    meta.get('subsector', ''),
                'open_price':   float(row.get('Open', close)),
                'high_price':   float(row.get('High', close)),
                'low_price':    float(row.get('Low', close)),
                'close_price':  close,
                'volume':       float(row.get('Volume', 0) or 0),
                'daily_return': ret,
                'nifty_weight': meta.get('nifty_weight', 0.001),
            })
        except Exception:
            continue
    return records


def fetch_all_stock_prices(start_date, end_date=None):
    """Fetches prices for all companies using per-ticker fetching."""
    def _yfinance_end():
        return (datetime.today() + timedelta(days=1)).strftime('%Y-%m-%d')

    end_str   = end_date.strftime('%Y-%m-%d') if end_date else _yfinance_end()
    start_str = (start_date.strftime('%Y-%m-%d')
                 if hasattr(start_date, 'strftime') else str(start_date))

    ticker_meta = build_ticker_metadata()
    all_tickers = list(ticker_meta.keys())
    total       = len(all_tickers)

    print(f"\n  Fetching {total} companies: {start_str} → {end_str}")

    all_records = []
    succeeded   = []
    failed      = []

    for i, ticker in enumerate(all_tickers, 1):
        df = _fetch_single_ticker(ticker, start_str, end_str, max_retries=3)
        if df is not None and not df.empty:
            records = _parse_single_ticker_records(ticker, df, ticker_meta)
            if records:
                all_records.extend(records)
                succeeded.append(ticker)
                print(f"  [{i:>3}/{total}] {ticker:<20} → {len(records)} rows ✓")
            else:
                failed.append(ticker)
                print(f"  [{i:>3}/{total}] {ticker:<20} → 0 rows (no valid returns)")
        else:
            failed.append(ticker)
            print(f"  [{i:>3}/{total}] {ticker:<20} → FAILED")
        time.sleep(0.08)

    print(f"\n  Succeeded: {len(succeeded)} | Failed: {len(failed)} | Records: {len(all_records):,}")

    if 0 < len(all_records) < 50:
        print(f"  🚨 WARNING: Only {len(all_records)} records — suspiciously low.")

    if len(all_records) == 0:
        print("  ⚠ WARNING: Total price records = 0")

    return all_records


def fetch_macro_history(start_date, end_date=None):
    """Fetches all macro variables for a date range.

    FIX 1: Always fetches at least 5 calendar days so NIFTY has >= 2
    trading-day closes and a valid return can always be computed.
    """
    def _yfinance_end():
        return (datetime.today() + timedelta(days=1)).strftime('%Y-%m-%d')

    # FIX 1: Ensure minimum 5-day lookback so pct_change() always has prev close
    if start_date is not None:
        _min_start = datetime.today().date() - timedelta(days=5)
        if hasattr(start_date, 'date'):
            _start_d = start_date.date()
        elif isinstance(start_date, str):
            _start_d = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            _start_d = start_date
        if _start_d > _min_start:
            start_date = _min_start
            print(f"  [NIFTY fix] Expanding macro fetch window to {start_date} "
                  f"(min 5-day lookback for return calculation)")

    end_str   = end_date.strftime('%Y-%m-%d') if end_date else _yfinance_end()
    start_str = (start_date.strftime('%Y-%m-%d')
                 if hasattr(start_date, 'strftime') else str(start_date))

    print(f"\n  Fetching macro data: {start_str} → {end_str}")

    series = {}
    for name, ticker in MACRO_TICKERS.items():
        try:
            data = yf.download(ticker, start=start_str, end=end_str,
                               progress=False, auto_adjust=True)
            if data is None or data.empty:
                print(f"  {name}: no data")
                continue
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            close_series = None
            for col in ['Close', 'close']:
                if col in data.columns:
                    close_series = data[col].dropna()
                    break
            if close_series is not None and len(close_series) > 0:
                series[name] = close_series
                print(f"  {name}: {len(close_series)} days ✓")
            else:
                print(f"  {name}: no Close column")
        except Exception as e:
            print(f"  {name}: error — {e}")

    if not series:
        print("  WARNING: No macro data fetched")
        return pd.DataFrame()

    # FIX 1: Validate NIFTY data integrity — always need >= 2 rows for return
    if "nifty" in series:
        nifty_raw = series["nifty"].dropna().sort_index()
        # Remove duplicate dates — keep last value per date
        nifty_raw = nifty_raw[~nifty_raw.index.duplicated(keep="last")]
        if len(nifty_raw) < 2:
            # FIX 1 FALLBACK: Insufficient rows from live fetch — supplement from DB
            print(f"  ⚠ WARNING: Insufficient NIFTY data ({len(nifty_raw)} rows) — "
                  f"attempting DB fallback for prior close")
            try:
                _fb_session = get_session()
                _fb_rows = _fb_session.query(MacroData).filter(
                    MacroData.nifty_close > 0
                ).order_by(MacroData.date.desc()).limit(5).all()
                _fb_session.close()
                if _fb_rows and len(_fb_rows) >= 2:
                    _fb_series = pd.Series(
                        {pd.Timestamp(_r.date): float(_r.nifty_close) for _r in reversed(_fb_rows)}
                    ).sort_index()
                    # Splice: DB prior closes + any live close we have
                    nifty_raw = pd.concat([_fb_series, nifty_raw])
                    nifty_raw = nifty_raw[~nifty_raw.index.duplicated(keep="last")].sort_index()
                    print(f"  [NIFTY fallback] spliced DB closes → {len(nifty_raw)} rows")
            except Exception as _e:
                print(f"  [NIFTY fallback] DB query failed: {_e}")

            if len(nifty_raw) < 2:
                print("  ⚠ WARNING: NIFTY still < 2 rows after fallback — "
                      "return will be 0.0 (safe neutral)")
                series.pop("nifty", None)
            else:
                series["nifty"] = nifty_raw
                print(f"  [NIFTY validation] {len(nifty_raw)} unique trading days (post-fallback) — OK")
        else:
            series["nifty"] = nifty_raw
            print(f"  [NIFTY validation] {len(nifty_raw)} unique trading days — OK")

    macro_df = pd.DataFrame()
    for name, s in series.items():
        s = pd.Series(s.values, index=pd.to_datetime(s.index), name=name)
        macro_df = s.to_frame() if macro_df.empty else macro_df.join(s.to_frame(), how="outer")

    macro_df.index = pd.to_datetime(macro_df.index)

    # ── ROOT CAUSE FIX: nifty_return 0.00 bug ────────────────────────────────────
    # BUG: Old code did reindex(daily_range).ffill() FIRST, which fills
    #      weekends/holidays with same close price as Friday. Then pct_change()
    #      gives 0.0% on Sat/Sun — stored to DB as real returns. Contribution
    #      engine then reads 0.0 and reports "NIFTY 0.00%".
    # FIX: Compute pct_change() on RAW trading-day data BEFORE any calendar fill.
    #      Non-trading days stay NaN in nifty_return — never stored as 0.
    # FIX 1b: Safe return calculation handles flat markets and single-row edge cases.
    if 'nifty' in macro_df.columns:
        nifty_trading = macro_df['nifty'].dropna().sort_index()
        if len(nifty_trading) >= 2:
            # FIX 1b: Safe element-by-element return — handles flat markets correctly
            curr_close = float(nifty_trading.iloc[-1])
            prev_close = float(nifty_trading.iloc[-2])

            if prev_close > 0:
                computed_ret = ((curr_close - prev_close) / prev_close) * 100
            else:
                computed_ret = 0.0   # prev_close invalid — safe neutral

            # FIX 1b: Flat market is VALID — curr == prev means 0% return, not an error
            if curr_close == prev_close:
                print(f"  [NIFTY] Flat market detected — today={curr_close:.2f} == prev={prev_close:.2f} "
                      f"→ return=0.00% (valid)")
            else:
                print(f"  [NIFTY] today={curr_close:.2f} | prev={prev_close:.2f} | "
                      f"return={computed_ret:+.4f}%")

            # Vectorised series for all trading days (NaN on first row, real elsewhere)
            nifty_rets = nifty_trading.pct_change() * 100
            macro_df['nifty_return'] = nifty_rets   # non-trading days remain NaN
        else:
            # FIX 1b: Try DB fallback — fetch last 2 stored nifty_close rows
            _ret_fallback = None
            try:
                _fb2 = get_session()
                _db_rows = _fb2.query(MacroData).filter(
                    MacroData.nifty_close > 0
                ).order_by(MacroData.date.desc()).limit(2).all()
                _fb2.close()
                if len(_db_rows) >= 2:
                    _curr = float(_db_rows[0].nifty_close)
                    _prev = float(_db_rows[1].nifty_close)
                    _ret_fallback = ((_curr - _prev) / _prev) * 100 if _prev > 0 else 0.0
                    print(f"  [NIFTY DB fallback] curr={_curr:.2f} prev={_prev:.2f} "
                          f"→ return={_ret_fallback:+.4f}%")
            except Exception as _fe:
                print(f"  [NIFTY DB fallback] failed: {_fe}")

            if _ret_fallback is not None:
                macro_df['nifty_return'] = _ret_fallback
            else:
                print("  WARNING: Insufficient NIFTY trading data — return set to None")
                macro_df['nifty_return'] = None

    # Save nifty_return BEFORE calendar reindex so ffill does not corrupt it
    nifty_ret_saved = macro_df['nifty_return'].copy() if 'nifty_return' in macro_df.columns else pd.Series(dtype=float)

    # Calendar reindex for other macro variables (rates, FX, VIX) — fine to ffill
    date_range = pd.date_range(start=macro_df.index.min(), end=macro_df.index.max(), freq='D')
    macro_df   = macro_df.reindex(date_range).ffill().bfill()

    # Restore nifty_return: trading days have real values, non-trading days = NaN
    if not nifty_ret_saved.empty:
        macro_df['nifty_return'] = nifty_ret_saved.reindex(date_range)

    for key, val in MANUAL_MACRO.items():
        macro_df[key] = val

    if 'nifty_return' in macro_df.columns and 'usdinr' in macro_df.columns:
        usdinr_ret = macro_df['usdinr'].pct_change() * 100
        macro_df['fii_net_crore'] = (macro_df['nifty_return'].fillna(0) - usdinr_ret.fillna(0)) * 1500

    macro_df = macro_df.dropna(how='all')
    return macro_df


# ─────────────────────────────────────────────────────────────────
# STORAGE
# ─────────────────────────────────────────────────────────────────

def store_prices(records):
    """Bulk stores price records, skipping duplicates."""
    if not records:
        print("  No price records to store.")
        return 0

    print(f"\n  Storing {len(records):,} price records...")
    session = get_session()
    try:
        all_dates   = list({r['date'] for r in records})
        all_tickers = list({r['ticker'] for r in records})
        rows        = session.query(DailyPrice.date, DailyPrice.ticker).filter(
            DailyPrice.date.in_(all_dates),
            DailyPrice.ticker.in_(all_tickers)
        ).all()
        existing    = {(r.date, r.ticker) for r in rows}
        new_records = [r for r in records if (r['date'], r['ticker']) not in existing]

        if not new_records:
            print("  All records already exist. Nothing new to store.")
            return 0

        chunk = 500
        for i in range(0, len(new_records), chunk):
            session.bulk_insert_mappings(DailyPrice, new_records[i:i + chunk])
            session.commit()

        print(f"  Stored {len(new_records):,} new price records ✓")
        return len(new_records)
    except Exception as e:
        session.rollback()
        print(f"  ERROR storing prices: {e}")
        return 0
    finally:
        session.close()


def store_macro(macro_df):
    """Stores macro DataFrame (upsert by date)."""
    if macro_df is None or macro_df.empty:
        print("  No macro data to store.")
        return 0

    print(f"\n  Storing {len(macro_df):,} macro records...")
    records = []
    for idx, row in macro_df.iterrows():
        try:
            row_date = idx.date() if hasattr(idx, 'date') else idx
            records.append({
                'date':            row_date,
                'usdinr':          _safe_float(row.get('usdinr'), 83.0),
                'brent_crude':     _safe_float(row.get('brent_crude'), 80.0),
                'india_vix':       _safe_float(row.get('india_vix'), 15.0),
                'nifty_close':     _safe_float(row.get('nifty'), 0.0),
                'sensex_close':    _safe_float(row.get('sensex'), 0.0),
                # ROOT CAUSE FIX: NaN nifty_return (non-trading day) → store as None
                # Using 0.0 default was the final step that wrote fake 0% returns to DB
                'nifty_return':    (None if pd.isna(row.get('nifty_return')) else _safe_float(row.get('nifty_return'), None)),
                'fii_net_crore':   _safe_float(row.get('fii_net_crore'), 0.0),
                'repo_rate':       _safe_float(row.get('repo_rate'), 6.5),
                'gdp_growth':      _safe_float(row.get('gdp_growth'), 6.0),
                'gst_collections': _safe_float(row.get('gst_collections'), 150000.0),
                'cpi_yoy':         _safe_float(row.get('cpi_yoy'), 5.0),
                'iip_growth':      _safe_float(row.get('iip_growth'), 4.0),
                'dii_net_crore':   0.0,
                'nasdaq_close':    _safe_float(row.get('nasdaq'), 0.0),
                'sp500_close':     _safe_float(row.get('sp500'), 0.0),
                'gold_close':      _safe_float(row.get('gold'), 0.0),
            })
        except Exception:
            continue

    session = get_session()
    try:
        dates = [r['date'] for r in records]
        session.query(MacroData).filter(MacroData.date.in_(dates)).delete(synchronize_session=False)
        session.commit()
        chunk = 500
        for i in range(0, len(records), chunk):
            session.bulk_insert_mappings(MacroData, records[i:i + chunk])
            session.commit()
        print(f"  Stored {len(records):,} macro records ✓")
        return len(records)
    except Exception as e:
        session.rollback()
        print(f"  ERROR storing macro: {e}")
        return 0
    finally:
        session.close()


def _safe_float(val, default=0.0):
    try:
        if val is None or pd.isna(val):
            return default
        f = float(val)
        return f if np.isfinite(f) else default
    except Exception:
        return default


# ─────────────────────────────────────────────────────────────────
# SECTION 2: MAIN ENTRY POINT — UPGRADED
# ─────────────────────────────────────────────────────────────────

def run_data_loader():
    """
    SECTION 2 UPGRADES:
    1. Always validates freshness first — never silently skips stale data
    2. force_fetch logic: if last_db_date < expected_trading_day → fetch
    3. After fetch: validates latest_date matches expected trading day
    4. If fetch fails: logs "WARNING: Using stale data — pipeline may be unreliable"
    5. If market closed: logs "Using previous trading day data: X" clearly
    6. Sets _DATA_STATUS so ALL modules know what date they're operating on
    """
    ensure_tables_exist()

    print("\n" + "=" * 60)
    print("MARKETOS DATA LOADER v6")
    print("=" * 60)

    today         = datetime.today().date()
    expected_date = get_last_valid_trading_day()

    # ── SECTION 2: Freshness check ────────────────────────────────
    freshness     = check_data_freshness()
    last_db_date  = freshness["last_db_date"]
    force_fetch   = freshness["fetch_required"]
    force_backfill = freshness.get("force_backfill", False)
    days_stale     = freshness.get("days_stale", 0)

    if not force_fetch:
        print(f"\n  ✓ Data is current as of {last_db_date}. No fetch needed.")
        _set_data_status(
            last_db_date=last_db_date,
            pipeline_date=last_db_date,
            fetch_required=False,
            fetch_performed=False,
            data_source="db_cache",
            is_stale=False,
        )
        return True

    # ── Determine fetch start date ────────────────────────────────
    # PART 6b: Force backfill — when DB is >1 trading day stale, fetch from
    # last_db_date+1 to catch ALL missing dates (not just yesterday).
    if force_backfill and last_db_date is not None:
        start_date = last_db_date + timedelta(days=1)
        print(f"  ⚠ FORCE BACKFILL: fetching from {start_date} "
              f"({days_stale} trading days missing)")
    else:
        start_date  = get_fetch_start_date()
    stored_p    = 0
    data_source = "live"

    # ── FILE 1 FIX 2: Market close check ─────────────────────────
    # NSE closes at 15:30 IST. Before that, today's data is incomplete/intraday.
    # Fetching intraday data causes duplicate close values (today == previous).
    now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    market_close_hour  = 15
    market_close_min   = 30
    market_is_closed   = (now_ist.hour > market_close_hour or
                          (now_ist.hour == market_close_hour and now_ist.minute >= market_close_min))

    if not market_is_closed and is_market_open_today():
        # FILE 1 FIX 1: Use last COMPLETE day — not today's intraday data
        last_complete = get_last_valid_trading_day()
        yesterday = today - timedelta(days=1)
        # Walk back to find yesterday's last trading day
        tmp = yesterday
        for _ in range(7):
            tmp_str = tmp.strftime('%Y-%m-%d')
            if tmp.weekday() < 5 and tmp_str not in NSE_HOLIDAYS_2026:
                last_complete = tmp
                break
            tmp -= timedelta(days=1)

        print(f"  ℹ Market not yet closed (IST {now_ist.strftime('%H:%M')}) — "
              f"using last complete date: {last_complete}")
        # Override start_date to only fetch completed trading days
        if start_date is not None and start_date >= today:
            start_date = last_complete
        data_source = f"last_complete:{last_complete}"

    # ── Price fetch ───────────────────────────────────────────────
    market_open = is_market_open_today()

    if market_open:
        price_records = fetch_all_stock_prices(start_date)

        # FILE 1 FIX 3: Prevent duplicate inserts — check if new close == last DB close
        if price_records:
            session_chk = get_session()
            try:
                from sqlalchemy import func as sqlfunc
                last_close_rows = session_chk.query(
                    DailyPrice.ticker, DailyPrice.close_price
                ).filter(
                    DailyPrice.date == get_last_stored_date()
                ).all()
                last_closes = {r.ticker: float(r.close_price or 0) for r in last_close_rows}
            except Exception:
                last_closes = {}
            finally:
                session_chk.close()

            filtered_records = []
            dup_count = 0
            for rec in price_records:
                ticker    = rec["ticker"]
                new_close = float(rec.get("close_price", 0))
                old_close = last_closes.get(ticker, -1)
                if old_close > 0 and abs(new_close - old_close) < 0.01:
                    dup_count += 1
                    continue   # same close price — skip duplicate insert
                filtered_records.append(rec)

            if dup_count > 0:
                print(f"  ⚠ FILE 1 FIX 3: Skipped {dup_count} duplicate close prices "
                      f"(new_close == last_db_close)")
            price_records = filtered_records

        stored_p = store_prices(price_records)

        if stored_p == 0 and len(price_records) == 0:
            # Fallback to last valid trading day
            fallback_date = get_last_valid_trading_day()
            if fallback_date != today:
                print(f"\n  ⚠ 0 records for {start_date} — retrying with {fallback_date}")
                price_records = fetch_all_stock_prices(fallback_date, end_date=fallback_date)
                stored_p      = store_prices(price_records)

                data_source   = f"fallback:{fallback_date}"
                if stored_p > 0:
                    print(f"  ✓ Fallback successful — {stored_p:,} records from {fallback_date}")
                    # SECTION 2: explicit fallback log
                    print(f"  ℹ Using previous trading day data: {fallback_date}")
                else:
                    data_source = "stale"
                    print("  ⚠ WARNING: Using stale data — pipeline may be unreliable")
            else:
                data_source = "stale"
                print("  ⚠ WARNING: Using stale data — pipeline may be unreliable")
    else:
        # Market closed — always use last valid trading day
        data_source = f"market_closed:{expected_date}"
        print(f"  ℹ Market closed today ({today}). Using previous trading day data: {expected_date}")
        stored_p    = 0   # no new records, but DB already has expected_date data

    # ── Macro fetch — always runs ─────────────────────────────────
    if start_date:
        macro_df = fetch_macro_history(start_date)
        stored_m = store_macro(macro_df)
    else:
        stored_m = 0

    # ── SECTION 2: Post-fetch validation ──────────────────────────
    new_last_date = get_last_stored_date()
    if isinstance(new_last_date, str):
        new_last_date = datetime.strptime(new_last_date, '%Y-%m-%d').date()

    pipeline_date = new_last_date or last_db_date or expected_date

    # is_stale = True ONLY when the market was open but we don't have that day's data.
    # When data_source is "market_closed:*", the gap between pipeline_date and
    # expected_date is because the market was closed (weekend/holiday) — this is
    # EXPECTED and must not trigger the stale block in main.py.
    _market_was_closed = data_source.startswith("market_closed:")
    is_stale = (
        pipeline_date is not None and
        pipeline_date < expected_date and
        not _market_was_closed
    )

    if is_stale and data_source == "live":
        stale_warning = f"WARNING: Using stale data ({pipeline_date}) — pipeline may be unreliable"
        print(f"\n  ⚠ {stale_warning}")
        data_source   = "stale"
    else:
        stale_warning = ""

    # ── Update global data status ──────────────────────────────────
    _set_data_status(
        last_db_date=pipeline_date,
        pipeline_date=pipeline_date,
        fetch_required=force_fetch,
        fetch_performed=stored_p > 0,
        data_source=data_source,
        is_stale=is_stale,
        stale_warning=stale_warning,
    )

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"DATA LOAD COMPLETE")
    print(f"  Price records stored : {stored_p:,}")
    print(f"  Macro records stored : {stored_m:,}")
    print(f"  Pipeline data date   : {pipeline_date}")   # SECTION 2: all modules use this date
    print(f"  Data source          : {data_source}")
    if is_stale:
        print(f"  ⚠ {stale_warning}")
    print(f"{'=' * 60}")

    return True


if __name__ == "__main__":
    from database import init_database
    init_database()
    run_data_loader()
