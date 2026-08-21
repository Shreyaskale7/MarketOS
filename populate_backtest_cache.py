"""
Pre-computes the walk-forward backtest for every window the dashboard
offers and writes the results into whatever database DATABASE_URL points
at.

WHY THIS EXISTS
---------------
/api/backtest computes the simulation on a cache miss. That is fine on a
laptop and fatal on Render's 512MB free instance: a 5yr or 10yr run loads
years of price history and simulates 15-35 rebalances, which exceeds the
memory/time budget, so the worker dies and the endpoint returns an empty
response with no error. Measured against the deployed service:

    years=3   -> 200, but served a STALE cache row (n=21, monthly
                 rebalancing, i.e. from before the quarterly switch)
    years=5   -> empty response (worker died)
    years=10  -> empty response (worker died)

Populating the cache from a machine that actually has the RAM turns every
one of those into an instant cache hit.

USAGE (point it at the deployed DB, not the local SQLite file):
    # PowerShell
    $env:DATABASE_URL = "<External Database URL from Render marketos-db>"
    python populate_backtest_cache.py

force_recompute=True is deliberate: the existing 3yr row was computed with
the old monthly/126d settings and must be overwritten, not reused.
"""

import os
import sys

# 3Y intentionally excluded: n=7 periods with a negative Sharpe is too
# small a sample to support a conclusion, so it is not shown on the
# dashboard and there is no reason to spend compute caching it.
WINDOWS = [5, 10]


def main():
    url = os.getenv("DATABASE_URL")
    print(f"DATABASE_URL set : {bool(url)}")
    if url:
        # Never print credentials.
        tail = url.rsplit("@", 1)[-1]
        print(f"target           : ...@{tail}")
    else:
        print("target           : local sqlite (data/marketos.db)")
        print("\nWARNING: DATABASE_URL is not set, so this will populate the LOCAL")
        print("cache only and the deployed dashboard will be unchanged.")
        if input("Continue anyway? [y/N] ").strip().lower() != "y":
            sys.exit(1)

    from backtest_engine import (
        run_backtest, REBALANCE_FREQ_DAYS, TRAIN_WINDOW_DAYS,
    )
    print(f"settings         : rebalance={REBALANCE_FREQ_DAYS}d "
          f"train={TRAIN_WINDOW_DAYS}d\n")

    rows = []
    for yrs in WINDOWS:
        print(f"--- {yrs}yr ---", flush=True)
        try:
            r = run_backtest(lookback_years=yrs, force_recompute=True)
            m = r.get("metrics", {})
            rows.append((
                yrs,
                m.get("total_periods"),
                m.get("portfolio_annualised_return_pct"),
                m.get("nifty_annualised_return_pct"),
                m.get("net_alpha_pct"),
                m.get("sharpe_ratio"),
                m.get("information_ratio"),
                m.get("cost_drag_annual_pct"),
                len(r.get("equity_curve", [])),
            ))
        except Exception as exc:
            print(f"  FAILED: {exc}")
            rows.append((yrs, "ERR", str(exc)[:40], None, None, None, None, None, 0))

    print("\n\n================ CACHED RESULTS ================")
    hdr = (f"{'yrs':>4} {'n':>4} {'port%':>8} {'nifty%':>8} {'alpha%':>8} "
           f"{'sharpe':>7} {'IR':>7} {'cost%':>6} {'curve':>6}")
    print(hdr)
    print("-" * len(hdr))
    for x in rows:
        if x[1] == "ERR":
            print(f"{x[0]:>4}  ERROR {x[2]}")
            continue
        print(f"{x[0]:>4} {x[1]:>4} {x[2]:>8.2f} {x[3]:>8.2f} {x[4]:>8.2f} "
              f"{x[5]:>7.3f} {x[6]:>7.3f} {x[7]:>6.2f} {x[8]:>6}")

    print("\nDone. The dashboard's 3Y / 5Y / 10Y buttons should now all be")
    print("instant cache hits. Reminder when quoting these: the largest")
    print("sample (10yr, n=35) is the defensible one, the result is not")
    print("stable across windows, and this exercises the trailing-Sharpe")
    print("selection heuristic, not the ML forecast engine.")


if __name__ == "__main__":
    main()
