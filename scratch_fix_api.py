import os

def fix():
    with open("c:/MarketOS VIP/marketos_api.py", "r", encoding="utf-8") as f:
        content = f.read()

    new_route = """# ─────────────────────────────────────────────────────────────────
# ROUTE 2B — SENTIMENT DATA
# ─────────────────────────────────────────────────────────────────

@app.route("/api/sentiment")
def sentiment_data():
    try:
        from sentiment_engine import get_live_sentiment_all_sectors
        sentiment = get_live_sentiment_all_sectors(force_refresh=False)
        return success({"sentiment": sentiment})
    except Exception as exc:
        return error(f"Sentiment engine error: {str(exc)}")

# ─────────────────────────────────────────────────────────────────
# ROUTE 3 — MACRO DATA"""

    target = """# ─────────────────────────────────────────────────────────────────
# ROUTE 3 — MACRO DATA"""
    
    content = content.replace(target, new_route)

    with open("c:/MarketOS VIP/marketos_api.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    fix()
