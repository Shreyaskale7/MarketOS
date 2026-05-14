# market_calendar.py
# MarketOS — Market State Awareness Layer
#
# Provides:
#   is_trading_day(date)     → bool
#   get_market_status(date)  → dict with full market context
#
# Design principles:
#   - Overlay layer only — does NOT modify any existing engine
#   - Engines call get_market_status() at their entry point and
#     adjust behaviour via the returned flags
#   - Extendable: add new holidays to NSE_HOLIDAYS or plug in
#     a live NSE holiday API without touching any other file
#
# Usage:
#   from market_calendar import get_market_status, is_trading_day
#   status = get_market_status()          # today
#   status = get_market_status(some_date) # specific date

from datetime import date, datetime, timedelta
from typing import Union

# ─────────────────────────────────────────────────────────────────
# NSE HOLIDAY CALENDAR
# Official NSE holidays — extend as new dates are announced.
# Format: "YYYY-MM-DD"
# Source: NSE India official holiday calendar
# ─────────────────────────────────────────────────────────────────

NSE_HOLIDAYS: set[str] = {
    # ── 2025 NSE Holidays ────────────────────────────────────────
    "2025-01-26",   # Republic Day
    "2025-02-26",   # Mahashivratri
    "2025-03-14",   # Holi
    "2025-03-31",   # Id-Ul-Fitr (Ramzan Id)
    "2025-04-10",   # Shri Ram Navami
    "2025-04-14",   # Dr. Baba Saheb Ambedkar Jayanti
    "2025-04-18",   # Good Friday
    "2025-05-01",   # Maharashtra Day
    "2025-08-15",   # Independence Day
    "2025-08-27",   # Ganesh Chaturthi
    "2025-10-02",   # Mahatma Gandhi Jayanti / Dussehra
    "2025-10-20",   # Diwali Laxmi Pujan (Muhurat Trading — treat as HOLIDAY)
    "2025-10-21",   # Diwali (Balipratipada)
    "2025-11-05",   # Prakash Gurpurb Sri Guru Nanak Dev Ji
    "2025-12-25",   # Christmas

    # ── 2026 NSE Holidays ────────────────────────────────────────
    "2026-01-26",   # Republic Day
    "2026-02-17",   # Mahashivratri (tentative — confirm on official NSE calendar)
    "2026-03-03",   # Holi (tentative)
    "2026-03-20",   # Id-Ul-Fitr (Ramzan Id) (tentative)
    "2026-03-30",   # Shri Ram Navami (tentative)
    "2026-04-03",   # Good Friday (tentative)
    "2026-04-14",   # Dr. Baba Saheb Ambedkar Jayanti
    "2026-05-01",   # Maharashtra Day
    "2026-08-15",   # Independence Day
    "2026-10-02",   # Mahatma Gandhi Jayanti
    "2026-10-08",   # Dussehra (tentative)
    "2026-10-26",   # Diwali Laxmi Pujan (tentative)
    "2026-10-27",   # Diwali (Balipratipada) (tentative)
    "2026-11-24",   # Prakash Gurpurb Sri Guru Nanak Dev Ji (tentative)
    "2026-12-25",   # Christmas
}

# NSE trading hours (IST = UTC+5:30)
NSE_OPEN_HOUR    = 9
NSE_OPEN_MINUTE  = 15
NSE_CLOSE_HOUR   = 15
NSE_CLOSE_MINUTE = 30


# ─────────────────────────────────────────────────────────────────
# CORE FUNCTIONS
# ─────────────────────────────────────────────────────────────────

def is_trading_day(d: Union[date, datetime, str, None] = None) -> bool:
    """
    Returns True if d is a valid NSE trading day.
    A trading day is:
      - Not Saturday (weekday 5) or Sunday (weekday 6)
      - Not in NSE_HOLIDAYS
    """
    if d is None:
        d = datetime.today().date()
    elif isinstance(d, datetime):
        d = d.date()
    elif isinstance(d, str):
        d = datetime.strptime(d, "%Y-%m-%d").date()

    if d.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    if d.strftime("%Y-%m-%d") in NSE_HOLIDAYS:
        return False
    return True


def get_last_trading_day(from_date: Union[date, datetime, None] = None) -> date:
    """
    Returns the most recent completed trading day on or before from_date.
    Walks back up to 10 calendar days (covers long holiday weekends).
    """
    if from_date is None:
        from_date = datetime.today().date()
    elif isinstance(from_date, datetime):
        from_date = from_date.date()

    d = from_date
    for _ in range(10):
        if is_trading_day(d):
            return d
        d -= timedelta(days=1)

    # Fallback — return from_date - 1 if nothing found (shouldn't happen)
    return from_date - timedelta(days=1)


def get_next_trading_day(from_date: Union[date, datetime, None] = None) -> date:
    """Returns the next trading day after from_date."""
    if from_date is None:
        from_date = datetime.today().date()
    elif isinstance(from_date, datetime):
        from_date = from_date.date()

    d = from_date + timedelta(days=1)
    for _ in range(10):
        if is_trading_day(d):
            return d
        d += timedelta(days=1)
    return d


def _get_close_reason(d: date) -> str:
    """Returns a human-readable reason the market is closed on d."""
    if d.weekday() == 5:
        return "Saturday — NSE closed on weekends"
    if d.weekday() == 6:
        return "Sunday — NSE closed on weekends"
    if d.strftime("%Y-%m-%d") in NSE_HOLIDAYS:
        return "NSE public holiday"
    return "Market closed"


def _is_market_currently_open(now_ist: datetime) -> bool:
    """Returns True if the market is currently in trading hours on this IST datetime."""
    open_time  = now_ist.replace(hour=NSE_OPEN_HOUR,  minute=NSE_OPEN_MINUTE,  second=0, microsecond=0)
    close_time = now_ist.replace(hour=NSE_CLOSE_HOUR, minute=NSE_CLOSE_MINUTE, second=0, microsecond=0)
    return open_time <= now_ist < close_time


# ─────────────────────────────────────────────────────────────────
# MAIN STATUS FUNCTION
# ─────────────────────────────────────────────────────────────────

def get_market_status(d: Union[date, datetime, str, None] = None) -> dict:
    """
    Returns a complete market status dict for date d (defaults to today).

    Return schema:
    {
        "date":                 date,       # the date being queried
        "is_trading_day":       bool,       # True if NSE trading day
        "market_status":        str,        # "OPEN" | "CLOSED" | "PRE_OPEN" | "POST_CLOSE"
        "session_state":        str,        # "LIVE" | "HOLIDAY" | "WEEKEND" | "AFTER_HOURS"
        "close_reason":         str,        # human-readable reason if closed
        "data_quality":         str,        # "VALID" | "HOLIDAY" | "STALE"
        "nifty_is_valid":       bool,       # False if holiday/weekend
        "last_trading_day":     date,       # most recent completed trading day
        "next_trading_day":     date,       # next upcoming trading day
        "should_rebalance":     bool,       # True only on live trading days after close
        "should_run_risk":      bool,       # True only on live trading days
        "should_run_alpha":     bool,       # True only on live trading days
        "should_run_forecast":  bool,       # True always (ML forecast runs even on holidays)
        "should_run_macro":     bool,       # True always (macro context always available)
        "engine_mode":          str,        # "FULL" | "FORECAST_ONLY" | "READONLY"
        "market_closed_text":   str,        # display text for insight engine
    }
    """
    # ── Resolve target date ───────────────────────────────────────
    if d is None:
        target_date = datetime.today().date()
    elif isinstance(d, datetime):
        target_date = d.date()
    elif isinstance(d, str):
        target_date = datetime.strptime(d, "%Y-%m-%d").date()
    else:
        target_date = d

    # ── IST time (UTC+5:30) ───────────────────────────────────────
    now_utc = datetime.utcnow()
    now_ist = now_utc + timedelta(hours=5, minutes=30)
    today   = now_ist.date()

    trading_day   = is_trading_day(target_date)
    last_td       = get_last_trading_day(target_date - timedelta(days=1))
    next_td       = get_next_trading_day(target_date)
    close_reason  = "" if trading_day else _get_close_reason(target_date)

    # ── Determine session state ───────────────────────────────────
    if not trading_day:
        if target_date.weekday() >= 5:
            session_state  = "WEEKEND"
            market_status  = "CLOSED"
        else:
            session_state  = "HOLIDAY"
            market_status  = "CLOSED"
    elif target_date == today:
        # Today is a trading day — check intraday clock
        if now_ist.hour < NSE_OPEN_HOUR or (now_ist.hour == NSE_OPEN_HOUR and now_ist.minute < NSE_OPEN_MINUTE):
            session_state = "AFTER_HOURS"    # Before market opens
            market_status = "PRE_OPEN"
        elif _is_market_currently_open(now_ist):
            session_state = "LIVE"
            market_status = "OPEN"
        else:
            session_state = "AFTER_HOURS"   # After 15:30
            market_status = "POST_CLOSE"
    else:
        # Past trading day — settled
        session_state = "AFTER_HOURS"
        market_status = "POST_CLOSE"

    # ── Data quality flag ─────────────────────────────────────────
    if not trading_day:
        data_quality = "HOLIDAY"
        nifty_valid  = False
    elif session_state == "LIVE":
        data_quality = "STALE"    # Intraday — not yet settled
        nifty_valid  = False
    else:
        data_quality = "VALID"
        nifty_valid  = True

    # ── Engine execution flags ────────────────────────────────────
    # Full price-driven engines run only on valid settled trading days
    price_engines_ok = trading_day and session_state in ("AFTER_HOURS",) and market_status == "POST_CLOSE"
    # For historical dates (already past), always treat as settled
    if target_date < today:
        price_engines_ok = trading_day
    # Macro + ML forecast run every day (they use DB data, not live prices)
    macro_ok    = True
    forecast_ok = True

    if trading_day and data_quality == "VALID":
        engine_mode = "FULL"
    elif not trading_day:
        engine_mode = "FORECAST_ONLY"
    else:
        engine_mode = "READONLY"    # Live intraday — read-only, no rebalancing

    # ── Closed-day display text for insight engine ────────────────
    if not trading_day:
        dow = target_date.strftime("%A")
        if target_date.weekday() >= 5:
            closed_text = (
                f"Market closed — {dow}. NSE does not trade on weekends. "
                f"Last trading session: {last_td.strftime('%d %b %Y')}. "
                f"Next trading session: {next_td.strftime('%d %b %Y')}."
            )
        else:
            closed_text = (
                f"Market closed — NSE public holiday ({dow} {target_date.strftime('%d %b %Y')}). "
                f"No trading activity today. "
                f"Last trading session: {last_td.strftime('%d %b %Y')}. "
                f"Next trading session: {next_td.strftime('%d %b %Y')}."
            )
    elif session_state == "LIVE":
        closed_text = (
            f"Market currently OPEN (NSE trading hours 09:15–15:30 IST). "
            f"Live intraday data — final close prices not yet settled."
        )
    else:
        closed_text = ""

    status = {
        "date":                target_date,
        "is_trading_day":      trading_day,
        "market_status":       market_status,
        "session_state":       session_state,
        "close_reason":        close_reason,
        "data_quality":        data_quality,
        "nifty_is_valid":      nifty_valid,
        "last_trading_day":    last_td,
        "next_trading_day":    next_td,
        "should_rebalance":    price_engines_ok,
        "should_run_risk":     price_engines_ok,
        "should_run_alpha":    price_engines_ok,
        "should_run_forecast": forecast_ok,
        "should_run_macro":    macro_ok,
        "engine_mode":         engine_mode,
        "market_closed_text":  closed_text,
    }

    return status


# ─────────────────────────────────────────────────────────────────
# CONVENIENCE HELPERS
# ─────────────────────────────────────────────────────────────────

def inject_market_status_into_macro(macro_data: dict, d=None) -> dict:
    """
    Injects market_status and nifty.is_valid flags into an existing
    macro_data dict. Called by fetch_live_macro_data() at end of fetch.
    Returns the same dict (mutated in-place for efficiency).
    """
    ms = get_market_status(d)
    macro_data["market_status"] = ms["market_status"]
    macro_data["engine_mode"]   = ms["engine_mode"]
    macro_data["data_quality"]  = ms["data_quality"]
    macro_data["session_state"] = ms["session_state"]

    # Augment nifty sub-dict with validity flag
    if "nifty" not in macro_data or not isinstance(macro_data["nifty"], dict):
        macro_data["nifty"] = {}
    macro_data["nifty"]["is_valid"] = ms["nifty_is_valid"]
    macro_data["nifty"]["market_status"] = ms["market_status"]

    return macro_data


def log_market_status(status: dict) -> None:
    """Prints a clean one-line market status summary."""
    d     = status["date"].strftime("%Y-%m-%d")
    ms    = status["market_status"]
    mode  = status["engine_mode"]
    dq    = status["data_quality"]
    valid = "✓" if status["nifty_is_valid"] else "✗"

    print(f"\n  ┌─ MARKET STATUS [{d}] ────────────────────────────")
    print(f"  │  Status       : {ms}")
    print(f"  │  Session      : {status['session_state']}")
    print(f"  │  Engine Mode  : {mode}")
    print(f"  │  Data Quality : {dq}")
    print(f"  │  NIFTY Valid  : {valid}")
    if status["close_reason"]:
        print(f"  │  Reason       : {status['close_reason']}")
    print(f"  │  Last Trade   : {status['last_trading_day']}")
    print(f"  │  Next Trade   : {status['next_trading_day']}")
    print(f"  └──────────────────────────────────────────────────")


# ─────────────────────────────────────────────────────────────────
# STANDALONE TEST
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from datetime import date

    test_dates = [
        date.today(),
        date.today() - timedelta(days=1),
        date(2026, 1, 26),    # Republic Day
        date(2026, 4, 3),     # Good Friday
    ]

    for td in test_dates:
        status = get_market_status(td)
        log_market_status(status)
        print(f"  is_trading_day : {status['is_trading_day']}")
        print(f"  should_rebalance: {status['should_rebalance']}")
        if status["market_closed_text"]:
            print(f"  Insight text   : {status['market_closed_text']}")
        print()
