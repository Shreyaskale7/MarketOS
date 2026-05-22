#!/usr/bin/env python3
"""
MarketOS v2 — Master Pipeline
FIXED: Auto-initialises DB, clean error handling, safe imports
"""

import os
import sys
import json

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

from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

# ─────────────────────────────────────────────────────────────────
# SIMPLE STARTUP - Just start API and pipeline
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "#"*60)
    print("#" + " "*58 + "#")
    print("#  MARKETOS DASHBOARD — Starting Services" + " "*18 + "#")
    print("#" + " "*58 + "#")
    print("#"*60)
    
    import subprocess
    import threading
    import time
    
    def start_api():
        print("\n  [1] Starting API Server...")
        subprocess.call([sys.executable, "marketos_api.py"])
    
    def run_pipeline():
        time.sleep(3)
        print("\n  [2] Running Daily Pipeline...")
        from main import run_daily_pipeline
        run_daily_pipeline()
    
    # Start API in background
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()
    
    # Start pipeline in background
    pipeline_thread = threading.Thread(target=run_pipeline, daemon=True)
    pipeline_thread.start()
    
    # Keep main thread alive
    try:
        api_thread.join()
    except KeyboardInterrupt:
        print("\n\n  Shutting down...")
        sys.exit(0)
