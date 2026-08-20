import sentiment_engine, requests, json, os

def test():
    sector = 'Banking & Financial Services'
    headlines = sentiment_engine.fetch_headlines(sector)[:15]
    prompt = f"""
    You are an expert institutional quantitative analyst. 
    Analyze the following recent news headlines for the Indian '{sector}' sector.
    Provide a sentiment score between -1.0 (extremely bearish/panic) to +1.0 (extremely bullish/euphoria).
    Also provide a comprehensive 2-3 sentence narrative explaining the score, mentioning specific themes or stocks.
    
    Headlines:
    {chr(10).join(['- ' + h for h in headlines])}
    
    Respond EXACTLY in this JSON format and nothing else:
    {{
        "sentiment_score": 0.0,
        "bullish_bearish_label": "BULLISH",
        "rationale": "Brief explanation."
    }}
    """
    
    url = 'https://api.groq.com/openai/v1/chat/completions'
    headers = {
        'Authorization': f'Bearer {os.getenv("GROQ_API_KEY")}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': 'llama-3.3-70b-versatile',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'response_format': {'type': 'json_object'}
    }
    r = requests.post(url, headers=headers, json=data)
    print('Status:', r.status_code)
    print('Headers:', r.headers)
    print('Response:', r.text)

if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    test()
