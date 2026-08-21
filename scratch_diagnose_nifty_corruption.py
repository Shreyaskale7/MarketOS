# scratch_diagnose_nifty_corruption.py
# One-off diagnostic: every subsector's ML training target is computed as
# (sector forward return) - (NIFTY forward return) over the SAME window
# (ml_forecast_engine._compound_forward). If even one historical row in
# macro_data.nifty_return is a garbage/extreme value, it silently poisons
# every single sector's target that has a training window overlapping that
# date -- which explains near-identical catastrophic magnitudes appearing
# across unrelated sectors (Insurance, AMCs, IT all showing ~-870M% to
# -910M% target means).
#
# fetch_macro_history()'s pct_change() over the full 10-year backfill has
# NO per-row sanity check (the +-5% circuit breaker in data_loader.py only
# checks the single LATEST computed return on an incremental run, never the
# historical backfill) -- so a bad tick anywhere in a decade of free
# yfinance data sits in the DB forever undetected until something like this
# surfaces it.
#
# Run with DATABASE_URL already set in the shell:
#   python scratch_diagnose_nifty_corruption.py

from database import get_session, MacroData, DailyPrice

session = get_session()
try:
    rows = session.query(MacroData).order_by(MacroData.date).all()
    print(f"Total macro_data rows: {len(rows)}")

    bad = [r for r in rows if r.nifty_return is not None and abs(r.nifty_return) > 8.0]
    print(f"\nmacro_data.nifty_return rows with |value| > 8%: {len(bad)}")
    for r in bad[:25]:
        print(f"  {r.date}  nifty_return={r.nifty_return:+.4f}%  nifty_close={r.nifty_close}")

    # Also check for the classic causes: zero/duplicate closes that make a
    # pct_change() blow up, and outright NaN/inf that slipped past storage.
    import math
    weird_close = [r for r in rows if not r.nifty_close or r.nifty_close <= 0]
    print(f"\nmacro_data rows with nifty_close missing/zero/negative: {len(weird_close)}")
    for r in weird_close[:10]:
        print(f"  {r.date}  nifty_close={r.nifty_close}")

    nonfinite = [r for r in rows if r.nifty_return is not None and not math.isfinite(r.nifty_return)]
    print(f"\nmacro_data rows with non-finite nifty_return (NaN/inf): {len(nonfinite)}")
    for r in nonfinite[:10]:
        print(f"  {r.date}  nifty_return={r.nifty_return}")

    # Same check on daily_prices, in case it's a second, independent source.
    dp = session.query(DailyPrice).filter(DailyPrice.daily_return != None).all()
    bad_dp = [r for r in dp if abs(r.daily_return) > 0.35]
    print(f"\ndaily_prices rows with |daily_return| > 35% (should already be "
          f"filtered out by ml_forecast_engine's own 0.35 guard, but "
          f"checking the raw table): {len(bad_dp)}")
    for r in bad_dp[:15]:
        print(f"  {r.date}  {r.ticker}  daily_return={r.daily_return:+.4f}")

finally:
    session.close()
