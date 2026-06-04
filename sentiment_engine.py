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
    
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        
        content = response.json()["choices"][0]["message"]["content"]
        result = json.loads(content)
        
        score = float(result.get("sentiment_score", result.get("score", 0.0)))
        score = max(-1.0, min(1.0, score))
        
        # Originality/fairness improvement: robust mapping of labels
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
        print(f"Error fetching sentiment for {sector}: {e}")
        return {"sentiment_score": 0.0, "bullish_bearish_label": "NEUTRAL", "rationale": "Error analyzing sentiment."}

_SENTIMENT_CACHE = None
_CACHE_TIMESTAMP = 0

def get_live_sentiment_all_sectors(force_refresh=False):
    global _SENTIMENT_CACHE, _CACHE_TIMESTAMP
    
    # Cache for 1 hour
    if not force_refresh and _SENTIMENT_CACHE and (time.time() - _CACHE_TIMESTAMP < 3600):
        return _SENTIMENT_CACHE
        
    print("\n=== LLM SENTIMENT ENGINE ===")
    results = {}
    for sector in SECTOR_PROXIES.keys():
        print(f"  Fetching news for {sector}...")
        headlines = fetch_headlines(sector)
        if headlines:
            sentiment = analyze_sentiment_groq(sector, headlines)
            results[sector] = sentiment
            print(f"  -> Score: {sentiment['sentiment_score']:+.2f} | {sentiment['rationale']}")
        else:
            print("  -> No news found.")
            results[sector] = {"sentiment_score": 0.0, "bullish_bearish_label": "NEUTRAL", "rationale": "No news data available."}
        time.sleep(0.5)
        
    _SENTIMENT_CACHE = results
    _CACHE_TIMESTAMP = time.time()
    return results

if __name__ == "__main__":
    print(get_live_sentiment_all_sectors(force_refresh=True))
