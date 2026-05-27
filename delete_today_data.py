import sys, os
from datetime import datetime
sys.path.append(r'c:\MarketOS VIP')
from database import get_session, DailyPrice, SectorPerformance, MacroData

session = get_session()
today = datetime.today().date()
dp_del = session.query(DailyPrice).filter(DailyPrice.date == today).delete()
sp_del = session.query(SectorPerformance).filter(SectorPerformance.date == today).delete()
md_del = session.query(MacroData).filter(MacroData.date == today).delete()
session.commit()
session.close()

print(f"Deleted today's data ({today}): DailyPrice={dp_del}, SectorPerformance={sp_del}, MacroData={md_del}")
