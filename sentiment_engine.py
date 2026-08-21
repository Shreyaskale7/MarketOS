# sentiment_engine.py
# MarketOS — LLM News Sentiment Layer

import os
import json
import time
import requests
import urllib.parse
import xml.etree.ElementTree as ET
import yfinance as yf
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Groq model, overridable by env so a provider deprecation is a config
# change, not a code change + redeploy.
#
# HISTORY: this was hardcoded to "llama-3.1-8b-instant", which Groq has
# since retired -- every request returned HTTP 404 model_not_found, which
# surfaced to users only as the generic "Error analyzing sentiment." Groq
# rotates its catalogue regularly; verify with
#   curl -H "Authorization: Bearer $GROQ_API_KEY" \
#        https://api.groq.com/openai/v1/models
# and set GROQ_MODEL in the environment rather than editing this default.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

# We map each sector to heavyweight proxies for news fetching
SECTOR_PROXIES = {
    "Banking & Financial Services": ["HDFCBANK.NS", "SBIN.NS"],
    "IT & Technology": ["INFY.NS", "TCS.NS"],
    "Energy & Oil & Gas": ["RELIANCE.NS", "ONGC.NS"],
    "Consumer Goods & Retail": ["ITC.NS", "HINDUNILVR.NS"], # Hindustan Unilever
    "Automobiles": ["MARUTI.NS", "TATAMOTORS.NS"],
    "Pharmaceuticals": ["SUNPHARMA.NS", "CIPLA.NS"],
    "Infrastructure & Real Estate": ["LT.NS", "DLF.NS"]
}

def fetch_headlines(sector):
    tickers = SECTOR_PROXIES.get(sector, [])
    headlines = []
    for t in tickers:
        try:
            clean_name = t.split('.')[0] + " stock market news"
            query = urllib.parse.quote(clean_name)
            url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
            
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            
            for item in root.findall(".//item")[:5]:  # get top 5 recent news per ticker
                title = item.find("title").text
                if title:
                    title = title.rsplit(' - ', 1)[0] # Remove source suffix
                    headlines.append(title)
        except Exception as e:
            print(f"Error fetching RSS for {t}: {e}")
            pass
    return headlines

def analyze_sentiment_groq(sector, headlines):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"score": 0.0, "narrative": "No Groq API key found. Sentiment disabled."}
        
    if not headlines:
        return {"score": 0.0, "narrative": "No recent news found."}

    news_text = "\n".join(f"- {h}" for h in headlines)
    
    prompt = f"""
    You are an expert institutional quantitative analyst. 
    Analyze the following recent news headlines for the Indian '{sector}' sector.
    Provide a sentiment score between -1.0 (extremely bearish/panic) to +1.0 (extremely bullish/euphoria).
    Also provide a comprehensive 2-3 sentence narrative explaining the score, mentioning specific themes or stocks.
    
    Headlines:
    {news_text}
    
    Respond EXACTLY in this JSON format and nothing else:
    {{
        "sentiment_score": 0.0,
        "bullish_bearish_label": "BULLISH",
        "rationale": "Brief explanation."
    }}
    """
    
    max_retries = 2
    base_delay = 2.0
    for attempt in range(max_retries):
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"}
            }

            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 429:
                print(f"Rate limited on attempt {attempt+1}. Retrying...")
                time.sleep(base_delay * (2 ** attempt))
                continue

            # FAIL FAST on permanent errors. Retrying a 404 (model retired)
            # or 401 (bad key) can never succeed, and the old code retried
            # both with a 2s backoff -- across 7 sectors that turned one
            # config mistake into a ~32s hang that blocked /api/alpha and
            # /api/portfolio, which is what made the whole dashboard look
            # broken rather than just the sentiment panel.
            if response.status_code in (400, 401, 403, 404):
                print(f"  [Sentiment] PERMANENT ERROR {response.status_code} for model "
                      f"'{GROQ_MODEL}': {response.text[:200]}")
                print(f"  [Sentiment] Not retrying. Set GROQ_MODEL to a currently-available "
                      f"model (list them: GET https://api.groq.com/openai/v1/models).")
                return {"sentiment_score": 0.0, "bullish_bearish_label": "NEUTRAL",
                        "rationale": f"Sentiment unavailable (model error {response.status_code})."}

            response.raise_for_status()

            content = response.json()["choices"][0]["message"]["content"]
            result = json.loads(content)
            
            score = float(result.get("sentiment_score", result.get("score", 0.0)))
            score = max(-1.0, min(1.0, score))
            
            if score >= 0.2:
                label = "BULLISH"
            elif score <= -0.2:
                label = "BEARISH"
            else:
                label = "NEUTRAL"
                
            label = result.get("bullish_bearish_label", label)
            rationale = result.get("rationale", result.get("narrative", "Neutral."))
            
            return {"sentiment_score": score, "bullish_bearish_label": label, "rationale": rationale}
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Error fetching sentiment for {sector}: {e}")
                return {"sentiment_score": 0.0, "bullish_bearish_label": "NEUTRAL", "rationale": "Error analyzing sentiment."}
            else:
                print(f"Exception on attempt {attempt+1}: {e}. Retrying...")
                time.sleep(base_delay * (2 ** attempt))
                
    print(f"Failed to fetch sentiment for {sector} after {max_retries} retries.")
    return {"sentiment_score": 0.0, "bullish_bearish_label": "NEUTRAL", "rationale": "API Rate Limit exceeded."}

_SENTIMENT_CACHE = None
_CACHE_TIMESTAMP = 0

def get_live_sentiment_all_sectors(force_refresh=False):
    global _SENTIMENT_CACHE, _CACHE_TIMESTAMP
    
    cache_file = "data/sentiment_cache.json"
    
    # Try to load from file on very first call if memory cache is empty
    if _SENTIMENT_CACHE is None:
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                _SENTIMENT_CACHE = cached_data.get("results", {})
                _CACHE_TIMESTAMP = cached_data.get("timestamp", 0)
                print(f"  [Sentiment] Loaded persistent cache from {cache_file} (age: {round(time.time() - _CACHE_TIMESTAMP)}s)")
            except Exception as e:
                print(f"  [Sentiment] Warning: Failed to load persistent cache: {e}")
                
    # If not forced, use memory/file cache if it is under 12 hours old
    if not force_refresh and _SENTIMENT_CACHE and (time.time() - _CACHE_TIMESTAMP < 43200):
        return _SENTIMENT_CACHE
        
    print("\n=== LLM SENTIMENT ENGINE ===")
    results = {}
    try:
        for sector in SECTOR_PROXIES.keys():
            print(f"  Fetching news for {sector}...")
            headlines = fetch_headlines(sector)
            if headlines:
                headlines = headlines[:15]
                sentiment = analyze_sentiment_groq(sector, headlines)
                results[sector] = sentiment
                time.sleep(1.0)
                print(f"  -> Score: {sentiment['sentiment_score']:+.2f} | {sentiment['rationale']}")
            else:
                print("  -> No news found.")
                results[sector] = {"sentiment_score": 0.0, "bullish_bearish_label": "NEUTRAL", "rationale": "No news data available."}
        
        # Save to memory and disk cache
        _SENTIMENT_CACHE = results
        _CACHE_TIMESTAMP = time.time()
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"results": results, "timestamp": _CACHE_TIMESTAMP}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"  [Sentiment] Warning: Failed to save persistent cache: {e}")
            
    except Exception as e:
        print(f"  [Sentiment] Error during live fetch: {e}")
        if _SENTIMENT_CACHE:
            print("  [Sentiment] Falling back to existing cache after fetch failure.")
            return _SENTIMENT_CACHE
        raise e
        
    return results

if __name__ == "__main__":
    print(get_live_sentiment_all_sectors(force_refresh=True))
