import urllib.request
import json

endpoints = [
    "/api/status",
    "/api/macro",
    "/api/alpha",
    "/api/forecasts",
    "/api/performance",
    "/api/backtest",
    "/api/insights",
    "/api/sectors",
    "/api/sector-historical-returns",
    "/api/sector-performance?days=30",
    "/api/macro-history?days=30",
    "/api/sentiment"
]

for ep in endpoints:
    url = f"http://localhost:5001{ep}"
    try:
        req = urllib.request.urlopen(url, timeout=10)
        data = json.loads(req.read())
        status = data.get("status")
        print(f"ok {ep:40s} -> status={status}, keys={list(data.keys())}")
        if "alpha" in data:
            print(f"   Alpha count: {len(data['alpha'])}")
        if "sentiment" in data:
            print(f"   Sentiment count: {len(data['sentiment'])}")
        if "sectors" in data:
            print(f"   Sectors count: {len(data['sectors'])}")
        if "history" in data:
            print(f"   History count: {len(data['history'])}")
        if "forecasts" in data:
            print(f"   Forecasts count: {len(data['forecasts'])}")
        if "insights" in data:
            print(f"   Insights count: {len(data['insights']) if isinstance(data['insights'], list) else 'not a list'}")
        if "performance" in data:
            p_data = data["performance"]
            print(f"   Performance count: {len(p_data) if isinstance(p_data, list) else 'not a list'}")
        if "backtest" in data:
            bt_data = data["backtest"]
            print(f"   Backtest keys: {list(bt_data.keys()) if isinstance(bt_data, dict) else 'not dict'}")
    except Exception as e:
        print(f"fail {ep:40s} -> FAILED: {e}")
