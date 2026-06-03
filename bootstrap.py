import threading
import time
import os
import sys

BOOTSTRAP_STATE = {
    "is_running": False,
    "status": "ready",
    "message": "System operational",
    "progress": "complete",
    "database_connected": False,
    "tables_created": False,
    "macro_data_loaded": False,
    "prices_loaded": False,
    "sector_data_loaded": False,
    "forecasts_generated": False,
    "daily_insights_generated": False,
    "pipeline_ready": False
}

def _run_bootstrap():
    global BOOTSTRAP_STATE
    try:
        from database import get_session, MacroData, DailyPrice, SectorPerformance, ForwardForecast, DailyInsight
        session = get_session()
        
        BOOTSTRAP_STATE["database_connected"] = True
        BOOTSTRAP_STATE["tables_created"] = True
        
        macro_count = session.query(MacroData).count()
        price_count = session.query(DailyPrice).count()
        sector_count = session.query(SectorPerformance).count()
        forecast_count = session.query(ForwardForecast).count()
        insight_count = session.query(DailyInsight).count()
        
        session.close()

        if macro_count > 0 and price_count > 0 and forecast_count > 0:
            BOOTSTRAP_STATE["macro_data_loaded"] = True
            BOOTSTRAP_STATE["prices_loaded"] = True
            BOOTSTRAP_STATE["sector_data_loaded"] = sector_count > 0
            BOOTSTRAP_STATE["forecasts_generated"] = True
            BOOTSTRAP_STATE["daily_insights_generated"] = insight_count > 0
            BOOTSTRAP_STATE["pipeline_ready"] = True
            BOOTSTRAP_STATE["is_running"] = False
            BOOTSTRAP_STATE["status"] = "ready"
            print("  [Bootstrap] Database is fully seeded. Ready for traffic.")
            return

        print("  [Bootstrap] Database is empty. Commencing background initialisation...")
        BOOTSTRAP_STATE["status"] = "bootstrapping"
        BOOTSTRAP_STATE["message"] = "Initial market data is loading"
        
        if price_count == 0 or macro_count == 0:
            BOOTSTRAP_STATE["progress"] = "fetching_raw_data"
            print("  [Bootstrap] Step 1: Running Data Loader...")
            import data_loader
            data_loader.run_data_loader()
            BOOTSTRAP_STATE["macro_data_loaded"] = True
            BOOTSTRAP_STATE["prices_loaded"] = True

        BOOTSTRAP_STATE["progress"] = "running_ml_pipeline"
        print("  [Bootstrap] Step 2: Running Daily Pipeline (ML Forecasts & Alpha)...")
        import main
        main.run_daily_pipeline()
        
        BOOTSTRAP_STATE["sector_data_loaded"] = True
        BOOTSTRAP_STATE["forecasts_generated"] = True
        BOOTSTRAP_STATE["daily_insights_generated"] = True
        BOOTSTRAP_STATE["pipeline_ready"] = True
        BOOTSTRAP_STATE["progress"] = "complete"
        BOOTSTRAP_STATE["status"] = "ready"
        BOOTSTRAP_STATE["message"] = "System operational"
        BOOTSTRAP_STATE["is_running"] = False
        print("  [Bootstrap] System initialisation complete! All endpoints online.")

    except Exception as e:
        import traceback
        traceback.print_exc()
        BOOTSTRAP_STATE["status"] = "error"
        BOOTSTRAP_STATE["message"] = f"Bootstrap failed: {str(e)}"
        BOOTSTRAP_STATE["is_running"] = False

def start_bootstrap():
    if os.environ.get("AUTO_BOOTSTRAP", "true").lower() != "true":
        return
    
    global BOOTSTRAP_STATE
    if BOOTSTRAP_STATE["is_running"]:
        return
        
    BOOTSTRAP_STATE["is_running"] = True
    BOOTSTRAP_STATE["status"] = "bootstrapping"
    
    t = threading.Thread(target=_run_bootstrap, daemon=True)
    t.start()
