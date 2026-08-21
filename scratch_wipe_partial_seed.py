# scratch_wipe_partial_seed.py
# One-off: clears the partially-seeded price/macro tables left behind by the
# crashed Render free-instance bootstrap attempt, so `python main.py --setup`
# starts from a genuinely empty DB instead of being fooled by
# check_data_freshness() into skipping the fetch (it only checks the most
# recent date, not per-sector coverage — see chat for the full diagnosis).
#
# Safe to delete after use. Run with DATABASE_URL already set in the shell:
#   python scratch_wipe_partial_seed.py

from database import get_session, DailyPrice, MacroData, SectorPerformance, ForwardForecast

session = get_session()
try:
    counts_before = {
        "daily_prices":      session.query(DailyPrice).count(),
        "macro_data":        session.query(MacroData).count(),
        "sector_performance": session.query(SectorPerformance).count(),
        "forward_forecasts": session.query(ForwardForecast).count(),
    }
    print("Before:", counts_before)

    if sum(counts_before.values()) == 0:
        print("Already empty — nothing to wipe.")
    else:
        confirm = input(
            "This will DELETE the rows above from the connected database "
            "(the one in $env:DATABASE_URL). Type 'wipe' to confirm: "
        )
        if confirm.strip().lower() != "wipe":
            print("Cancelled — nothing deleted.")
        else:
            session.query(DailyPrice).delete()
            session.query(MacroData).delete()
            session.query(SectorPerformance).delete()
            session.query(ForwardForecast).delete()
            session.commit()
            print("Wiped. Now run: python main.py --setup")
finally:
    session.close()
