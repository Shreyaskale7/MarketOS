# main.py
# MarketOS v2 — Master Pipeline
# FIXED: Auto-initialises DB, clean error handling, safe imports

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
# ─── CONFIG — Edit these ─────────────────────────────────────────

# ─── MANUAL MACRO CONFIG ─────────────────────────────────────────
# UPDATE THESE after each official data release.
# Last updated: 2026-05-08
# Sources: RBI (repo rate), MoSPI (GDP/CPI/IIP), GSTN (GST)

CURRENT_REPO_RATE   = 5.25   # RBI MPC — next review: Jun 2026
PREVIOUS_REPO_RATE  = 5.5  # Previous MPC decision

CURRENT_GDP         = 6.4    # Q3 FY26 advance estimate — MoSPI
CURRENT_CPI         = 4.8    # Apr 2026 — MoSPI (update monthly)
CURRENT_IIP         = 5.2    # Mar 2026 — MoSPI (update monthly)

CURRENT_GST         = 187000.0  # Apr 2026 collections (₹ Cr) — GSTN
PREVIOUS_GST        = 183000.0  # Mar 2026 collections (₹ Cr)

MACRO_CONFIG_DATE   = "2026-05-20"  # date these values were last verified
# ─────────────────────────────────────────────────────────────────


# ── ALWAYS ensure database + folders exist before anything else ───
from database import ensure_tables_exist, init_database
ensure_tables_exist()

from classification import get_sector_summary, MARKET_CLASSIFICATION


def patch_manual_macros():
    """Updates manual macro values across all modules."""
    from datetime import date
    days_old = (date.today() - date.fromisoformat(MACRO_CONFIG_DATE)).days
    if days_old > 45:
        print(f"  ⚠ MANUAL MACRO CONFIG IS {days_old} DAYS OLD — "
              f"consider updating CURRENT_CPI, CURRENT_IIP, CURRENT_GST in main.py")
    import macro_engine as me
    import data_loader as dl

    manual = {
        "repo_rate":       CURRENT_REPO_RATE,
        "gdp_growth":      CURRENT_GDP,
        "gst_collections": CURRENT_GST,
        "cpi_yoy":         CURRENT_CPI,
        "iip_growth":      CURRENT_IIP,
    }

    dl.MANUAL_MACRO = manual

    me.MANUAL_MACRO = manual
    me.MACRO_VARIABLES['repo_rate']['current_value']       = CURRENT_REPO_RATE
    me.MACRO_VARIABLES['repo_rate']['previous_value']      = PREVIOUS_REPO_RATE
    me.MACRO_VARIABLES['gst_collections']['current_value'] = CURRENT_GST
    me.MACRO_VARIABLES['gst_collections']['previous_value']= PREVIOUS_GST
    me.MACRO_VARIABLES['gdp_growth']['current_value']      = CURRENT_GDP


# ─────────────────────────────────────────────────────────────────
# AI INSIGHT CONFIG
# Choose ONE provider and add its key.
# All options are FREE — no credit card needed.
#
# Option A — Groq (RECOMMENDED — fastest, free forever)
#   Get key: console.groq.com → API Keys
#
# Option B — Google Gemini (free tier, some limits)
#   Get key: aistudio.google.com → Get API Key
#
# Option C — No key — system runs without AI narrative
# ─────────────────────────────────────────────────────────────────

GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def build_anti_hallucination_prefix(moderated_output):
    """
    Builds a strict fact-injection prefix to prevent LLM contradictions.
    Forces the LLM to use only these verified numbers.
    """
    macro = moderated_output.get('macro_data', {})
    regime = moderated_output.get('macro_regime', {})

    # BUG FIX: the NIFTY return itself — arguably the single most important
    # fact for a daily market insight — was never included in this prefix,
    # even though moderated_output carries it at the top level. That meant
    # the LLM path had no verified NIFTY figure to ground its narrative on,
    # and the no-API _structured_fallback()'s regex was searching prompt
    # text for a number that was never actually injected into the prompt,
    # producing "NIFTY 50 gained N/A% today" even when the real return was
    # sitting right there in moderated_output the whole time.
    nifty_ret_pct = moderated_output.get('nifty_actual_return_pct')
    nifty_ret_pct = 0.0 if nifty_ret_pct is None else nifty_ret_pct
    nifty_level   = moderated_output.get('nifty_level', 0) or 0
    nifty_dir     = "gained" if nifty_ret_pct >= 0 else "declined"

    crude_val    = macro.get('brent_crude', {}).get('current', 0)
    crude_chg    = macro.get('brent_crude', {}).get('change_pct', 0)
    usdinr_val   = macro.get('usdinr', {}).get('current', 0)
    usdinr_chg   = macro.get('usdinr', {}).get('change_pct', 0)
    vix_val      = macro.get('india_vix', {}).get('current', 0)
    repo_rate    = macro.get('repo_rate', {}).get('current', 6.5)
    rate_change  = macro.get('repo_rate', {}).get('change', 0)
    fii_signal   = macro.get('fii_flows', {}).get('signal', 'NEUTRAL')
    nasdaq_chg   = macro.get('nasdaq', {}).get('change_pct', 0)

    # Derive direction labels
    crude_dir    = "SPIKING" if crude_chg > 2 else ("FALLING" if crude_chg < -2 else "STABLE")
    rupee_dir    = "STRENGTHENING" if usdinr_chg < -0.3 else ("WEAKENING" if usdinr_chg > 0.3 else "STABLE")
    vix_label    = "ELEVATED FEAR" if vix_val > 20 else ("CALM" if vix_val < 13 else "MODERATE")
    rate_label   = "CUT" if rate_change < -0.01 else ("HIKED" if rate_change > 0.01 else "UNCHANGED")
    nasdaq_dir   = "RISING" if nasdaq_chg > 0.5 else ("FALLING" if nasdaq_chg < -0.5 else "FLAT")

    prefix = f"""
CRITICAL INSTRUCTION: You are generating financial analysis. 
Use ONLY the verified facts below. DO NOT contradict them. 
DO NOT invent data. DO NOT say crude is falling if it is spiking.

VERIFIED MACRO FACTS FOR TODAY:
- NIFTY 50: {nifty_level:,.2f} | Return: {nifty_ret_pct:+.4f}% (index {nifty_dir} today)
- Brent Crude: ${crude_val:.1f}/bbl | Direction: {crude_dir} ({crude_chg:+.1f}%)
- USD/INR: ₹{usdinr_val:.2f} | Rupee: {rupee_dir} ({usdinr_chg:+.2f}%)
- India VIX: {vix_val:.1f} | Volatility: {vix_label}
- Repo Rate: {repo_rate}% | Status: RATE {rate_label}
- FII Flows: {fii_signal}
- NASDAQ: {nasdaq_dir} ({nasdaq_chg:+.2f}%) — use this to explain IT sector movement
- Macro Regime: {regime.get('overall_regime', 'UNKNOWN')} (score: {regime.get('legacy_score', int(round(float(regime.get('regime_score',0))*10))):+d}/10)

RULES:
1. If crude is SPIKING, say it is hurting Energy/OMC sector. NEVER say "falling crude".
2. If rupee is STABLE, IT sector movement is driven by US tech sentiment (NASDAQ).
3. If VIX > 20, acknowledge elevated fear explicitly.
4. Explain MACRO_DIVERGENT sectors as "despite macro suggesting X, sector moved Y because of Z".
5. Keep all numbers consistent with the verified facts above.

"""
    return prefix


# ─────────────────────────────────────────────────────────────────
# MODULE 7 — INSIGHT REALISM FILTER
# Removes fake precision; enforces qualitative language consistency
# ─────────────────────────────────────────────────────────────────

def _apply_insight_realism(text: str) -> str:
    """
    MODULE 7 UPGRADE — Post-processes LLM insight text:

    1. Replaces fabricated specific figures with qualitative language
         e.g. "EBITDA +10%" → "EBITDA may improve"
              "GRM falls $2–3" → "refining margins may decline"
    2. Ensures bullish sector descriptions are positive in tone
    3. Flags conflicting sentiment with "despite headwinds" language
    4. Removes patterns like "X% revenue boost" unless from verified data
    """
    import re

    # ── Replace fake EBITDA / GRM precise figures ─────────────────
    # Pattern: "EBITDA [+-]X%" → qualitative
    text = re.sub(
        r"EBITDA\s*[+-]?\d+[\–\-]?\d*\s*%",
        "EBITDA may improve",
        text, flags=re.IGNORECASE
    )
    # Pattern: "GRM [falls/rises/narrows] $X-Y/bbl"
    text = re.sub(
        r"GRM\s+(falls?|rises?|narrows?|expands?)\s+(?:by\s+)?\~?\$[\d\.]+[\–\-]?[\d\.]*\s*(?:/bbl)?",
        r"refining margins may \1",
        text, flags=re.IGNORECASE
    )
    # Pattern: "$X-Y/bbl" standalone
    text = re.sub(
        r"\~?\$[\d\.]+[\–\-][\d\.]+\s*/bbl",
        "per-barrel margin impact",
        text, flags=re.IGNORECASE
    )
    # Pattern: "X-Y% EBITDA" or "X-12% EBITDA"
    text = re.sub(
        r"\d+[\–\-]\d+\s*%\s*EBITDA",
        "potential EBITDA pressure",
        text, flags=re.IGNORECASE
    )
    # Pattern: "X-Y% revenue boost/impact"
    text = re.sub(
        r"\d+[\–\-]\d+\s*%\s*(revenue\s+boost|revenue\s+impact|margin\s+improvement|margin\s+compression)",
        r"potential \1",
        text, flags=re.IGNORECASE
    )
    # Pattern: "EMI savings of ₹X" — remove fabricated rupee savings
    text = re.sub(
        r"EMI\s+savings?\s+of\s+₹[\d,]+",
        "lower EMI costs",
        text, flags=re.IGNORECASE
    )
    # ── "cutting X's EBITDA by ~Y%" patterns ─────────────────────
    text = re.sub(
        r"cutting\s+\w+[''\s]*s?\s+(?:refining\s+)?EBITDA\s+by\s+[~\d\-–%]+",
        "potentially pressuring profitability",
        text, flags=re.IGNORECASE
    )

    # ── SECTION 11: Replace fake precision phrases entirely ────────
    text = text.replace("EBITDA +10%", "EBITDA likely to improve")
    text = text.replace("GRM +$3", "refining margins may improve")
    text = text.replace("GRM -$3", "refining margins may decline")

    # ── Remove forbidden phrases (Section 11 cleanup) ─────────────
    FORBIDDEN = [
        ("company-specific factors",   "sector-level dynamics"),
        ("technical factors",           "price-level dynamics"),
        ("short-term positioning",      "near-term flows"),
        ("market sentiment",            "macro backdrop"),
        ("broader trends",              "macro environment"),
        ("investor confidence",         "risk appetite"),
        ("positive for the sector",     "a tailwind for the sector"),
        ("stock price boost",           "positive price impact"),
        ("technical reasons",           "price-level factors"),
        ("positioning effects",         "flow dynamics"),
    ]
    for bad, good in FORBIDDEN:
        text = re.sub(re.escape(bad), good, text, flags=re.IGNORECASE)

    return text


def generate_ai_insight(prompt, language="english", moderated_output=None):
    """
    Generates AI market insight.
    Tries Groq first, falls back to Gemini, then returns structured fallback.
    Injects anti-hallucination prefix with verified macro facts.
    """
    import requests

    # Inject verified macro facts to prevent hallucination
    if moderated_output:
        anti_hallucination = build_anti_hallucination_prefix(moderated_output)
        prompt = anti_hallucination + prompt

    # Add language instruction
    if language == "hindi":
        lang_prefix = "Respond in simple Hindi. Keep NIFTY, FII, VIX, SEBI in English.\n\n"
        prompt = lang_prefix + prompt

    # ── Try Groq first (fastest, most reliable free tier) ─────────
    if GROQ_API_KEY:
        result = _call_groq(prompt)
        if result and not result.startswith("ERROR"):
            return _apply_insight_realism(result)   # MODULE 7: realism filter
        print(f"  Groq failed: {result}. Trying Gemini...")

    # ── Try Gemini as fallback ────────────────────────────────────
    if GEMINI_API_KEY:
        result = _call_gemini(prompt)
        if result and not result.startswith("ERROR"):
            return _apply_insight_realism(result)   # MODULE 7: realism filter
        print(f"  Gemini failed: {result}")

    # ── Structured fallback — no API needed ───────────────────────
    return _structured_fallback(prompt)


def _call_groq(prompt):
    """Calls Groq API — free, 14,400 requests/day."""
    import requests

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        # See sentiment_engine.GROQ_MODEL for the full note: the previous
        # hardcoded "llama-3.1-8b-instant" was retired by Groq and returned
        # 404 on every call, silently forcing every daily insight down the
        # no-API _structured_fallback() path. Overridable via GROQ_MODEL.
        "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are MarketOS, India\'s explainable market intelligence engine. "
                    "You explain verified financial data in clear, simple language. "
                    "Never make investment recommendations. Always include a disclaimer."
                )
            },
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 800,
        "temperature": 0.3,
    }

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code == 429:
            return "ERROR: Groq rate limit hit. Retrying in 60 seconds."

        if response.status_code != 200:
            return f"ERROR: Groq HTTP {response.status_code}: {response.text[:200]}"

        data = response.json()
        text = data["choices"][0]["message"]["content"].strip()
        return text

    except requests.exceptions.Timeout:
        return "ERROR: Groq timed out."
    except Exception as e:
        return f"ERROR: {e}"


def _call_gemini(prompt):
    """Calls Gemini API — free tier with daily limits."""
    import requests

    # Try models in order of availability
    models = ["gemini-1.5-flash-8b", "gemini-1.0-pro", "gemini-2.0-flash-lite"]

    for model in models:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={GEMINI_API_KEY}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 800, "temperature": 0.3}
        }

        try:
            response = requests.post(url, json=payload, timeout=30)

            if response.status_code == 429:
                continue  # quota exceeded, try next model

            if response.status_code != 200:
                continue

            data = response.json()
            if "error" in data:
                continue

            candidates = data.get("candidates", [])
            if not candidates:
                continue

            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if text:
                return text.strip()

        except Exception:
            continue

    return "ERROR: All Gemini models exhausted or unavailable."


def _structured_fallback(prompt):
    """
    Generates a structured insight WITHOUT any API.
    Extracts key facts from the prompt and formats them cleanly.
    Used when no API key is set or all APIs fail.
    """
    import re

    # Extract key numbers from the prompt.
    # Matches the "NIFTY 50: 24,395.85 | Return: -0.1641% (index declined
    # today)" line injected by build_anti_hallucination_prefix() — the
    # previous pattern searched for text that was never actually in the
    # prompt (NIFTY was missing from the prefix entirely), which is why
    # this always fell through to "N/A".
    nifty_match  = re.search(r"NIFTY 50:.*?Return:\s*([+-]?\d+\.\d+)%", prompt)
    # FIX: this was searching for "Overall: X" / "Regime Score: N", which
    # never appears anywhere in build_anti_hallucination_prefix()'s actual
    # text ("Macro Regime: NEUTRAL (score: +0/10)") — always fell through
    # to "Unknown" / "0", same class of bug as the NIFTY one above.
    regime_match = re.search(r"Macro Regime:\s*(\w+)", prompt)
    score_match  = re.search(r"\(score:\s*([+-]?\d+)/10\)", prompt)
    vix_match    = re.search(r"India VIX.*?(\d+\.\d+)", prompt)
    crude_match  = re.search(r"Brent Crude.*?\$(\d+\.?\d*)", prompt)

    nifty_ret = nifty_match.group(1) if nifty_match else "N/A"
    regime    = regime_match.group(1).replace("_", " ") if regime_match else "Unknown"
    score     = score_match.group(1) if score_match else "0"
    vix       = vix_match.group(1) if vix_match else "N/A"
    crude     = crude_match.group(1) if crude_match else "N/A"

    direction = "gained" if nifty_ret and not str(nifty_ret).startswith("-") else "declined"

    return f"""WHAT HAPPENED:
NIFTY 50 {direction} {nifty_ret}% today, with mixed sectoral performance across the market.

WHY IT HAPPENED:
Current macro regime is {regime} with a score of {score}/10. India VIX at {vix} indicates {'elevated market fear and risk-off sentiment' if vix != 'N/A' and float(vix) > 20 else 'moderate market conditions'}. Brent crude at ${crude}/barrel is {'adding pressure to import-heavy sectors' if crude != 'N/A' and float(crude) > 90 else 'providing relief to the import bill'}.

IMPLICATION FOR INVESTORS:
Monitor macro variables closely, particularly VIX levels and FII flows, before making portfolio decisions. Sectors aligned with the current macro regime are more likely to sustain their current direction.

REGIME CONTEXT:
Overall macro environment is {regime}. Maintain awareness of crude oil prices and rupee movement as primary near-term market drivers.

DISCLAIMER: This is educational market analysis only. Not investment advice.
Add GROQ_API_KEY (free at console.groq.com) for AI-generated insights."""


def save_output(output, date_str, label="daily"):
    """Saves pipeline output to JSON."""
    os.makedirs("outputs", exist_ok=True)
    fname = f"outputs/marketos_{label}_{date_str}.json"

    def clean(obj):
        if isinstance(obj, float):
            if obj != obj or abs(obj) == float('inf'):
                return None
            return round(obj, 6)
        if isinstance(obj, (datetime,)):
            return str(obj)
        return obj

    with open(fname, 'w') as f:
        json.dump(output, f, indent=2, default=clean)

    print(f"\nOutput saved → {fname}")
    return fname


# ─────────────────────────────────────────────────────────────────
# FIRST TIME SETUP
# ─────────────────────────────────────────────────────────────────

def first_time_setup():
    """
    Run ONCE when you first set up the project.
    Downloads 10 years of data and trains all models.
    Takes 30-90 minutes depending on internet speed.
    """

    patch_manual_macros()

    print("\n" + "█"*60)
    print("  MARKETOS — FIRST TIME SETUP")
    print("  Estimated time: 30-90 minutes")
    print("  Please keep this window open.")
    print("█"*60)

    # Step 1: Database
    print("\n[1/4] Creating database tables...")
    init_database()
    print("  ✓ Database ready")

    # Step 2: Historical data
    print("\n[2/4] Downloading 10 years of market data...")
    print("  (This is the slowest step — ~20-40 mins)")
    from data_loader import run_data_loader
    run_data_loader()
    print("  ✓ Historical data loaded")

    # Step 3a: Train legacy sector models
    print("\n[3/4] Training sector models...")
    print("  (Takes ~5-15 minutes)")
    from model_trainer import train_all_models
    train_all_models(lookback_years=10, model_type='auto')
    print("  ✓ Legacy models trained")

    # Step 3b: Train ML horizon models (new data-driven engine)
    print("\n[3b/4] Training ML horizon models (1M/3M/6M) from 10yr data...")
    print("  (Takes ~10-20 minutes — trains per-horizon RF models for every sector)")
    try:
        from ml_forecast_engine import train_all_horizon_models
        ml_results = train_all_horizon_models(lookback_years=10)
        ok = sum(1 for v in ml_results.values() if v is not None)
        print(f"  ✓ ML horizon models trained: {ok}/{len(ml_results)} sectors")
    except Exception as e:
        print(f"  ML training skipped (non-critical): {e}")

    # Step 4: Analytics
    print("\n[4/4] Computing sector growth analytics...")
    try:
        from forward_engine import compute_sector_growth_analytics
        compute_sector_growth_analytics()
        print("  ✓ Analytics computed")
    except Exception as e:
        print(f"  Analytics skipped (non-critical): {e}")

    print("\n" + "█"*60)
    print("  SETUP COMPLETE")
    print("  Now run:  python main.py --daily")
    print("█"*60)


# ─────────────────────────────────────────────────────────────────
# DAILY PIPELINE
# ─────────────────────────────────────────────────────────────────

def run_daily_pipeline(date=None, print_report=True):
    """
    Runs the full daily intelligence pipeline.

    Flow:
    1.  Ensure DB tables exist
    2.  Fetch today's new price + macro data
    3.  Run contribution engine (company→subsector→sector→NIFTY)
    4.  Fetch live macro snapshot
    5.  Classify macro regime
    6.  Moderate contributions with macro context
    7.  Generate daily AI insight (WHAT→WHY→IMPLICATION)
    8.  Generate forward forecasts (1M/3M/6M/12M)
    9.  Identify top opportunities per horizon
    10. Generate forward AI insight
    11. Save full JSON output
    """

    patch_manual_macros()
    ensure_tables_exist()  # safety net — always ensure tables first

    start_time = datetime.now()
    run_date   = date or datetime.today().strftime('%Y-%m-%d')

    # ── MARKET STATE AWARENESS — determine engine mode at pipeline start ──
    try:
        from market_calendar import get_market_status, log_market_status
        _market_status = get_market_status()
        log_market_status(_market_status)
        _engine_mode  = _market_status["engine_mode"]
        _data_quality = _market_status["data_quality"]
        _trading_day  = _market_status["is_trading_day"]
    except ImportError:
        print("  ⚠ market_calendar.py not found — assuming FULL mode")
        _market_status = {"engine_mode": "FULL", "data_quality": "VALID",
                          "is_trading_day": True, "should_rebalance": True}
        _engine_mode   = "FULL"
        _data_quality  = "VALID"
        _trading_day   = True

    # Determine data source for transparency
    from data_loader import get_last_stored_date, _last_nse_trading_day
    _last_db_date    = get_last_stored_date()
    _last_trade_day  = _last_nse_trading_day()
    _is_fallback     = (_last_db_date is not None and _last_db_date < _last_trade_day)
    _data_source_str = (f"FALLBACK — DB data from {_last_db_date} (last trading day: {_last_trade_day})"
                        if _is_fallback else f"LIVE — current data as of {_last_db_date or run_date}")

    print(f"\n{'='*65}")
    print(f"  MARKETOS DAILY PIPELINE  —  {run_date}")
    print(f"  Engine Mode   : {_engine_mode}  |  Data Quality: {_data_quality}")
    print(f"{'='*65}")
    if _is_fallback:
        print(f"  ⚠ DATA SOURCE: {_data_source_str}")
    if not _trading_day:
        print(f"  ℹ NON-TRADING DAY: {_market_status.get('close_reason', 'Market closed')}")
        print(f"  ℹ Price-driven engines (portfolio, risk, alpha) will be SKIPPED.")
        print(f"  ℹ ML forecasts and macro analysis will still run.")

    # ── Step 1: Fetch new data ─────────────────────────────────────
    print("\n[1/9] Fetching new market data...")
    from data_loader import run_data_loader, get_data_status
    run_data_loader()

    # TASK 6: Global debug log — single pipeline_date reference
    _status = get_data_status()
    print("\n=== DATA PIPELINE STATUS ===")
    print(f"Pipeline date : {_status['pipeline_date']}")
    print(f"Last DB date  : {_status['last_db_date']}")
    print(f"Data source   : {_status['data_source']}")
    print("===========================\n")

    # TASK 7: Hard block on stale data — but ONLY when market was open.
    # On weekends / holidays, data_source = "market_closed:DATE" which is
    # expected and valid — the pipeline correctly runs on last trading day's data.
    # We must NOT raise here in those cases, or the pipeline breaks every weekend.
    _data_src = _status.get("data_source", "")
    _is_market_closed_source = (
        _data_src.startswith("market_closed:") or
        _data_src.startswith("fallback:") or
        _trading_day is False  # already detected non-trading day above
    )
    if _status.get("is_stale") and not _is_market_closed_source:
        raise ValueError(
            f"CRITICAL: Stale DB data (last={_status['last_db_date']}) — "
            f"run data_loader first: python main.py --setup or check data feed"
        )
    elif _status.get("is_stale") and _is_market_closed_source:
        print(f"  ℹ Stale flag set but data_source='{_data_src}' — "
              f"market closed, running on last trading day ({_status['last_db_date']}) ✓")

    # ── Step 2: Macro data ─────────────────────────────────────────
    print("\n[2/9] Fetching live macro snapshot...")
    from macro_engine import (
        fetch_live_macro_data,
        classify_macro_regime,
        moderate_contributions_with_macro,
        build_final_insight_prompt,
        print_macro_report
    )
    macro_data = fetch_live_macro_data()

    # ── Step 3: Contribution engine ────────────────────────────────
    print("\n[3/9] Running contribution engine...")
    from contribution_engine import (
        run_full_contribution_engine,
        print_contribution_report,
        get_top_movers
    )
    contrib = run_full_contribution_engine(target_date=date)

    if contrib is None:
        print("\n  Contribution engine returned no data.")
        print("  Market may be closed today, or data not yet available.")
        print("  Try again after 4:30 PM IST on a trading day.")
        return None

    print(f"  NIFTY: {contrib['nifty_actual_return_pct']:+.3f}% "
          f"| Attribution: {contrib.get('total_contribution_explained_pct', 0):+.3f}%")

    # ── SECTION 10: Output consistency validation ──────────────────
    nifty_ret_check  = contrib.get('nifty_actual_return_pct', None)
    contrib_sum_check = contrib.get('normalized_contribution_pct', None)
    if nifty_ret_check is not None and contrib_sum_check is not None:
        mismatch = abs(nifty_ret_check - contrib_sum_check)
        if mismatch > 0.05:
            print(f"  ⚠ SECTION 10 WARNING: Contribution sum mismatch — "
                  f"NIFTY={nifty_ret_check:+.4f}% vs contrib_sum={contrib_sum_check:+.4f}% "
                  f"(diff={mismatch:.4f}%)")
        else:
            print(f"  ✓ SECTION 10: Contribution sum consistent with NIFTY return")
    if nifty_ret_check == 0.0:
        print(f"  ⚠ SECTION 10 WARNING: NIFTY return = 0.000% — verify data freshness")

    # ── Attribution reliability flag (uses correct key from contribution engine) ──
    raw_attr  = contrib.get('raw_contribution_pct', 0)   # correct key name
    actual    = contrib.get('nifty_actual_return_pct', 0)
    scale_err = abs(raw_attr - actual) if raw_attr != 0 else 0
    if scale_err < 0.05:
        attr_quality = "HIGH"
    elif scale_err < 0.20:
        attr_quality = "MEDIUM"
    else:
        attr_quality = "LOW"
    print(f"    Attribution confidence: {attr_quality}"
          f" (raw={raw_attr:+.3f}% → normalized={actual:+.3f}%)")

    # ── Step 4: Regime classification ─────────────────────────────
    print("\n[4/9] Classifying macro regime...")

    # FILE 5: Pipeline consistency — pass NIFTY return from contribution engine
    # to regime classifier so it uses the SAME data source (not a separate fetch)
    nifty_ret_for_regime = contrib.get("nifty_actual_return_pct", None)
    if nifty_ret_for_regime is not None:
        macro_data["nifty_actual_return_pct"] = nifty_ret_for_regime
        print(f"  [FILE 5] Injecting NIFTY return into macro_data: {nifty_ret_for_regime:+.4f}%")

    # FILE 4 FIX 1: validation gate inside classify_macro_regime will
    # force NEUTRAL if nifty_actual_return_pct is None or ~0
    regime = classify_macro_regime(macro_data)
    _rs_disp = regime.get('legacy_score', int(round(float(regime.get('regime_score',0))*10)))
    print(f"  Regime: {regime['overall_regime']} | Score: {_rs_disp:+d} | "
          f"Data valid: {regime.get('data_valid', True)}")

    # ── Step 5: Macro moderation ───────────────────────────────────
    print("\n[5/9] Macro moderation...")
    moderated = moderate_contributions_with_macro(contrib, regime, macro_data)

    # ── Step 6: Daily AI insight ───────────────────────────────────
    print("\n[6/9] Generating daily insight...")

    # FIX 3: Ensure NIFTY data is valid before insight generation.
    # A missing or None change_pct would cause the prompt builder to
    # embed None/NaN literals → LLM hallucination or format errors.
    _nifty_check = macro_data.get("nifty", {})
    if not _nifty_check or _nifty_check.get("change_pct") is None:
        print("  ⚠ Fixing missing NIFTY return before insight — defaulting change_pct to 0.0")
        macro_data["nifty"] = {
            "current":    _nifty_check.get("current", 0) if _nifty_check else 0,
            "change_pct": 0.0,
            "is_valid":   True,
        }

    daily_prompt  = build_final_insight_prompt(moderated)
    daily_insight = generate_ai_insight(daily_prompt, moderated_output=moderated)

    # ── Step 7: Forward forecasts — ML engine (falls back to rule-based) ─
    print("\n[7/9] Generating forward forecasts (ML engine)...")
    try:
        # Try ML engine first — data-driven from 10yr historical patterns
        from ml_forecast_engine import (
            generate_ml_forecasts,
            validate_forecast_sanity,
        )
        from forward_engine import (
            get_top_opportunities,
            build_opportunity_prompt,
            print_forward_intelligence_report,
            get_sector_comparison_report,
        )

        import os as _os
        _ml_models_exist = _os.path.isdir("data/models/ml_horizon") and             any(f.endswith(".pkl") for f in _os.listdir("data/models/ml_horizon"))

        if _ml_models_exist:
            print("  Using ML horizon models (data-driven)")
            all_forecasts = generate_ml_forecasts(macro_data, regime)
        else:
            print("  ML models not found — using rule-based engine")
            print("  To train ML models: python main.py --train-ml")
            from forward_engine import generate_forward_forecasts
            all_forecasts = generate_forward_forecasts(macro_data, regime)

        # ── Step 8: Top opportunities ──────────────────────────────
        print("\n[8/9] Identifying opportunities...")
        opportunities = {
            h: get_top_opportunities(horizon=h, top_n=10)
            for h in ["1M", "3M", "6M", "12M"]
        }

        # ── Step 9: Forward AI insight ─────────────────────────────
        print("\n[9/9] Generating forward intelligence...")
        comparison     = get_sector_comparison_report()
        fwd_prompt     = build_opportunity_prompt(
            opportunities, comparison, regime, macro_data
        )
        forward_insight = generate_ai_insight(fwd_prompt)

    except Exception as e:
        print(f"  Forward engine skipped: {e}")
        all_forecasts   = {}
        opportunities   = {}
        forward_insight = "Forward intelligence unavailable — run --setup first to train models."

    # ── NEW: Portfolio, Risk, Alpha, Performance, Backtest ────────
    portfolio_output  = {}
    risk_output       = {}
    alpha_scores      = {}
    performance_output = {}
    backtest_output   = {}

    if all_forecasts:
        # ── Alpha signals FIRST — needed to filter portfolio ───────
        try:
            # Warm sentiment SYNCHRONOUSLY here. The engine now defaults to
            # non-blocking so the web API never hangs ~37s on a cold cache
            # (see sentiment_engine.get_live_sentiment_all_sectors), but the
            # daily pipeline is exactly the place that SHOULD wait: whatever
            # it computes gets persisted, so it must be real sentiment, not
            # a neutral placeholder.
            try:
                from sentiment_engine import get_live_sentiment_all_sectors
                get_live_sentiment_all_sectors(force_refresh=True, blocking=True)
            except Exception as _e:
                print(f"  Sentiment warm-up skipped: {_e}")

            print("\n[+] Computing alpha signals...")
            from alpha_engine import compute_alpha_scores
            alpha_scores = compute_alpha_scores(moderated, macro_data, regime)
        except Exception as e:
            print(f"  Alpha engine skipped: {e}")

        # ── Portfolio construction (with alpha scores injected) ────
        try:
            print("\n[+] Running portfolio construction engine...")
            from portfolio_engine import build_portfolio
            # MODULE 2+3: alpha_scores passed in — excluded subsectors dropped,
            # score formula uses alpha_score × confidence × return / vol
            portfolio_output = {}
            for h in ["1M", "3M", "6M", "12M"]:
                portfolio_output[h] = build_portfolio(
                    all_forecasts, macro_data, regime,
                    horizon=h, alpha_scores=alpha_scores
                )
        except Exception as e:
            print(f"  Portfolio engine skipped: {e}")

        # ── Risk management ────────────────────────────────────────
        try:
            print("\n[+] Applying risk management rules...")
            from risk_engine import apply_risk_rules
            risk_output = {}
            if isinstance(portfolio_output, dict):
                for h in ["1M", "3M", "6M", "12M"]:
                    if h in portfolio_output:
                        risk_output[h] = apply_risk_rules(portfolio_output[h], macro_data, regime)
        except Exception as e:
            print(f"  Risk engine skipped: {e}")

        # ── Paper Trading Ledger ──────────────────────────────────
        try:
            print("\n[+] Recording paper trades...")
            from portfolio_engine import record_paper_trade
            nifty_ret = contrib.get("nifty_actual_return_pct", 0.0)
            if isinstance(portfolio_output, dict) and "3M" in portfolio_output:
                p_3m = portfolio_output["3M"]
                allocs = {sub: w_data.get("adjusted_weight", 0.0) for sub, w_data in p_3m.get("weights", {}).items()}
                record_paper_trade(run_date, allocs, all_forecasts, benchmark_return=nifty_ret)
        except Exception as e:
            print(f"  Paper trade recording skipped: {e}")

    # ── Performance analytics (always runs if DB has data) ────────
    try:
        print("\n[+] Computing performance analytics...")
        from performance_engine import compute_performance_summary
        performance_output = compute_performance_summary()
    except Exception as e:
        print(f"  Performance engine skipped: {e}")

    # ── Print reports ──────────────────────────────────────────────
    if print_report:
        print_contribution_report(contrib)
        get_top_movers(contrib, n=5)
        print_macro_report(moderated)

        if all_forecasts:
            try:
                print_forward_intelligence_report(
                    all_forecasts, macro_data, regime
                )
            except Exception as e:
                print(f"  Forward report skipped: {e}")

        print(f"\n{'='*65}")
        print("MARKETOS DAILY INSIGHT")
        print(f"{'='*65}")
        print(daily_insight)

        print(f"\n{'='*65}")
        print("MARKETOS FORWARD INTELLIGENCE")
        print(f"{'='*65}")
        print(forward_insight)

    # ── Build final output ─────────────────────────────────────────
    final_output = {
        "date":         run_date,
        "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "market_status":  _market_status.get("market_status", "OPEN"),
        "engine_mode":    _engine_mode,
        "data_quality":   _data_quality,
        "nifty": {
            "level":      contrib.get('nifty_level', 0),
            "return_pct": contrib['nifty_actual_return_pct'],
            "points":     contrib['nifty_actual_points'],
            "is_valid":   contrib.get('nifty_data_valid', True),
        },
        "macro_regime": {
            "label":  regime['overall_regime'],
            "score":  regime['regime_score'],
            "risk":   regime['risk_level'],
            "bias":   regime['market_bias'],
        },
        "macro_snapshot": {
            k: (v.get('current') if isinstance(v, dict) else
                v.get('signal')  if isinstance(v, dict) else v)
            for k, v in macro_data.items()
        },
        "sector_summary": {
            name: {
                "contribution_pct": d.get('sector_contribution_pct', 0),
                "return_pct":       d.get('sector_return_pct', 0),
                "macro_driver":     d.get('primary_macro_driver', ''),
                "alignment":        d.get('macro_alignment', ''),
            }
            for name, d in moderated.get('moderated_sectors', {}).items()
        },
        "top_opportunities": {
            h: [
                {
                    "subsector":    o['subsector'],
                    "score":        o['opportunity_score'],
                    "base_return":  o['base_case_return_pct'],
                    "bull_return":  o.get('bull_case_return_pct', 0),
                    "bear_return":  o.get('bear_case_return_pct', 0),
                    "confidence":   o.get('confidence_score', 0),
                    "catalyst":     o['primary_catalyst'],
                    "stance":       o.get('portfolio_stance', 'NEUTRAL'),
                }
                for o in opps[:5]
            ]
            for h, opps in opportunities.items()
        },
        "daily_insight":   daily_insight,
        "forward_insight": forward_insight,
        # ── New modules ───────────────────────────────────────────
        "portfolio": {
            "construction": portfolio_output,
            "risk_adjusted": risk_output,
        },
        "alpha_scores":  alpha_scores,
        "performance":   performance_output,
    }

    save_output(final_output, run_date, "daily")

    # ── Store DailyInsight to DB (with data_quality + market_status) ──
    try:
        from database import get_session, DailyInsight
        import json as _json
        from datetime import date as _date_type

        _top_sector = ""
        _top_contrib = 0.0
        for _sname, _sdata in moderated.get("moderated_sectors", {}).items():
            _c = abs(_sdata.get("sector_contribution_pct", 0))
            if _c > _top_contrib:
                _top_contrib = _c
                _top_sector  = _sname

        _insight_session = get_session()
        try:
            _run_date_obj = (
                datetime.strptime(run_date, "%Y-%m-%d").date()
                if isinstance(run_date, str) else run_date
            )
            # Upsert: delete today's record if present, then insert fresh
            _insight_session.query(DailyInsight).filter(
                DailyInsight.date == _run_date_obj
            ).delete(synchronize_session=False)

            _insight_rec = DailyInsight(
                date           = _run_date_obj,
                what_text      = daily_insight[:500] if daily_insight else "",
                why_text       = "",
                implication    = "",
                regime_context = regime.get("overall_regime", ""),
                full_insight   = daily_insight or "",
                forward_insight = forward_insight or "",
                regime_label   = regime.get("overall_regime", ""),
                regime_score   = int(regime.get('legacy_score', int(round(float(regime.get('regime_score', 0)) * 10)))),
                nifty_return   = float(contrib.get("nifty_actual_return_pct", 0.0)),
                top_sector     = _top_sector,
                model_version  = f"data_quality={_data_quality}|market={_market_status.get('market_status','OPEN')}",
                generated_at   = datetime.utcnow(),
            )
            _insight_session.add(_insight_rec)
            _insight_session.commit()
            print(f"  ✓ DailyInsight stored — data_quality={_data_quality} "
                  f"| market_status={_market_status.get('market_status','OPEN')}")
        except Exception as _ie:
            _insight_session.rollback()
            print(f"  ⚠ DailyInsight store failed: {_ie}")
        finally:
            _insight_session.close()
    except Exception as _outer_ie:
        print(f"  ⚠ DailyInsight import/store skipped: {_outer_ie}")

    # ── Store SectorPerformance to DB ──────────────────────────────
    try:
        from database import get_session, SectorPerformance as _SectorPerf
        _sp_session = get_session()
        try:
            _sp_run_date_obj = (
                datetime.strptime(run_date, "%Y-%m-%d").date()
                if isinstance(run_date, str) else run_date
            )
            # Upsert: delete today's records first to prevent duplicates
            _sp_session.query(_SectorPerf).filter(
                _SectorPerf.date == _sp_run_date_obj
            ).delete(synchronize_session=False)

            _sp_records = []
            _regime_label = regime.get("overall_regime", "UNKNOWN")

            for _sec_name, _sec_data in moderated.get("moderated_sectors", {}).items():
                _sector_ret   = float(_sec_data.get("sector_return_pct", 0) or 0)
                _sector_contr = float(_sec_data.get("sector_contribution_pct", 0) or 0)
                _primary_drv  = str(_sec_data.get("primary_macro_driver", "") or "")
                _alignment    = str(_sec_data.get("macro_alignment", "") or "")

                _subsectors = _sec_data.get("subsectors", {})
                if _subsectors:
                    for _sub_name, _sub_data in _subsectors.items():
                        _sp_records.append(_SectorPerf(
                            date                       = _sp_run_date_obj,
                            sector                     = _sec_name,
                            subsector                  = _sub_name,
                            sector_return_pct          = _sector_ret,
                            sector_contribution_pct    = _sector_contr,
                            subsector_return_pct       = float(_sub_data.get("subsector_weighted_return_pct", 0) or 0),
                            subsector_contribution_pct = float(_sub_data.get("subsector_contribution_to_index_pct", 0) or 0),
                            top_company                = str(_sub_data.get("top_contributor", "") or ""),
                            primary_macro_driver       = _primary_drv,
                            macro_alignment            = _alignment,
                            regime_label               = _regime_label,
                        ))
                else:
                    # No subsectors — store a sector-level row
                    _sp_records.append(_SectorPerf(
                        date                       = _sp_run_date_obj,
                        sector                     = _sec_name,
                        subsector                  = "",
                        sector_return_pct          = _sector_ret,
                        sector_contribution_pct    = _sector_contr,
                        subsector_return_pct       = _sector_ret,
                        subsector_contribution_pct = _sector_contr,
                        top_company                = "",
                        primary_macro_driver       = _primary_drv,
                        macro_alignment            = _alignment,
                        regime_label               = _regime_label,
                    ))

            _sp_session.add_all(_sp_records)
            _sp_session.commit()
            print(f"  ✓ SectorPerformance stored — {len(_sp_records)} records for {run_date}")
        except Exception as _spe:
            _sp_session.rollback()
            print(f"  ⚠ SectorPerformance store failed: {_spe}")
        finally:
            _sp_session.close()
    except Exception as _outer_spe:
        print(f"  ⚠ SectorPerformance import/store skipped: {_outer_spe}")

    elapsed = (datetime.now() - start_time).seconds
    print(f"\n✓ Pipeline complete in {elapsed}s  |  "
          f"NIFTY: {contrib['nifty_actual_return_pct']:+.3f}%  |  "
          f"Regime: {regime['overall_regime']}  |  "
          f"DataQuality: {_data_quality}")

    return final_output


# ─────────────────────────────────────────────────────────────────
# MONTHLY RETRAINING
# ─────────────────────────────────────────────────────────────────

def run_monthly_retraining():
    """Retrains all models (legacy + ML) on latest 3 years of data."""

    ensure_tables_exist()
    print("\n" + "="*60)
    print("MONTHLY RETRAINING")
    print("="*60)

    from model_trainer import train_all_models
    train_all_models(lookback_years=3, model_type='auto')

    # Also retrain ML horizon models on rolling 3yr window
    try:
        from ml_forecast_engine import retrain_rolling_ml
        retrain_rolling_ml(lookback_years=3)
        print("  ✓ ML horizon models retrained (3yr window)")
    except Exception as e:
        print(f"  ML retrain skipped: {e}")

    try:
        from forward_engine import compute_sector_growth_analytics
        compute_sector_growth_analytics()
    except Exception as e:
        print(f"Analytics refresh skipped: {e}")

    print("\nMonthly retraining complete.")


def run_ml_training(lookback_years=10):
    """Trains ML horizon models from scratch using full historical data."""

    ensure_tables_exist()
    print("\n" + "="*60)
    print(f"ML HORIZON MODEL TRAINING — {lookback_years}yr")
    print("="*60)
    print("This trains separate RandomForest models for 1M, 3M, 6M")
    print("horizons using actual historical price + macro data.")
    print("Run this once after --setup, or after major DB updates.")
    print()

    from ml_forecast_engine import train_all_horizon_models, diagnose_database
    diagnose_database()
    results = train_all_horizon_models(lookback_years=lookback_years)

    ok = sum(1 for v in results.values() if v is not None)
    print(f"\n✓ ML training complete: {ok}/{len(results)} models")
    print("Daily pipeline will now use ML forecasts automatically.")


# ─────────────────────────────────────────────────────────────────
# AUTOMATED SCHEDULER
# ─────────────────────────────────────────────────────────────────

def start_scheduler():
    """Starts the automated daily scheduler (runs indefinitely)."""

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("Install APScheduler:  pip install apscheduler")
        return

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    @scheduler.scheduled_job(CronTrigger(day_of_week='mon-fri', hour=16, minute=30))
    def job_fetch():
        from data_loader import run_data_loader
        patch_manual_macros()
        run_data_loader()

    @scheduler.scheduled_job(CronTrigger(day_of_week='mon-fri', hour=19, minute=0))
    def job_daily():
        run_daily_pipeline()

    @scheduler.scheduled_job(CronTrigger(day=1, hour=21, minute=0))
    def job_retrain():
        run_monthly_retraining()   # includes ML rolling retrain

    @scheduler.scheduled_job(CronTrigger(day_of_week='sat', hour=8, minute=0))
    def job_ml_validate():
        # Weekly sanity check on ML forecasts
        try:
            from ml_forecast_engine import validate_forecast_sanity, generate_ml_forecasts
            from macro_engine import fetch_live_macro_data, classify_macro_regime
            macro = fetch_live_macro_data()
            reg   = classify_macro_regime(macro)
            fcs   = generate_ml_forecasts(macro, reg)
            validate_forecast_sanity(fcs)
        except Exception as e:
            print(f"ML validate error: {e}")

    @scheduler.scheduled_job(CronTrigger(day_of_week='sun', hour=10, minute=0))
    def job_analytics():
        try:
            from forward_engine import compute_sector_growth_analytics
            compute_sector_growth_analytics()
        except Exception as e:
            print(f"Analytics error: {e}")

    print("\nMarketOS Scheduler Started (IST)")
    print("  4:30 PM  Mon-Fri  →  Fetch market data")
    print("  7:00 PM  Mon-Fri  →  Full daily pipeline")
    print("  1st of month      →  Model retraining")
    print("  Sunday 10:00 AM   →  Analytics refresh")
    print("\nPress Ctrl+C to stop.\n")

    scheduler.start()


# ─────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    get_sector_summary()

    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python main.py --setup               # Run ONCE on first use")
        print("  python main.py --daily               # Run every trading day")
        print("  python main.py --retrain             # Retrain all models (3yr window)")
        print("  python main.py --train-ml [years]    # Train ML horizon models (default: 10yr)")
        print("  python main.py --retrain-ml          # Rolling ML retrain (3yr window)")
        print("  python main.py --diagnose            # Show DB data summary")
        print("  python main.py --validate-ml         # Validate current ML forecasts")
        print("  python main.py --schedule            # Start auto-scheduler")
        print("  python main.py --date 2024-10-15     # Specific date")
        print("  python main.py --backtest [years]    # Walk-forward backtest (default: 3yr)")
        print("  python main.py --performance         # Show forecast accuracy & analytics")
        print("  python main.py --portfolio           # Build today's portfolio allocation")
        print("\nFirst time? Run:")
        print("  1. python main.py --setup        (downloads data, trains legacy models)")
        print("  2. python main.py --train-ml     (trains ML horizon models from 10yr data)")
        print("  3. python main.py --daily        (runs daily pipeline with ML forecasts)")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "--setup":
        first_time_setup()

    elif cmd == "--daily":
        run_daily_pipeline()

    elif cmd == "--retrain":
        run_monthly_retraining()

    elif cmd == "--train-ml":
        # Train ML horizon models from full historical data
        yrs = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        run_ml_training(lookback_years=yrs)

    elif cmd == "--retrain-ml":
        # Retrain ML models on rolling 3yr window
        from ml_forecast_engine import retrain_rolling_ml
        retrain_rolling_ml(lookback_years=3)

    elif cmd == "--diagnose":
        # Show what data is in the DB — useful for debugging
        from ml_forecast_engine import diagnose_database
        diagnose_database()

    elif cmd == "--validate-ml":
        # Validate current ML forecasts for sanity
        from ml_forecast_engine import validate_forecast_sanity, generate_ml_forecasts
        from macro_engine import fetch_live_macro_data, classify_macro_regime
        macro_data = fetch_live_macro_data()
        regime     = classify_macro_regime(macro_data)
        forecasts  = generate_ml_forecasts(macro_data, regime)
        validate_forecast_sanity(forecasts)

    elif cmd == "--schedule":
        start_scheduler()

    elif cmd == "--date" and len(sys.argv) > 2:
        run_daily_pipeline(date=sys.argv[2])

    elif cmd == "--backtest":
        # Run walk-forward backtest
        # Usage: python main.py --backtest [years] [--force]
        # --force bypasses cache and recomputes from scratch (needed after data updates)
        _args     = sys.argv[2:]
        _force    = "--force" in _args
        # Sanitize: strip non-numeric characters so '3M', '5Y', '3yr' all work
        _yrs_args = []
        for a in _args:
            if a.startswith("--"):
                continue
            cleaned = ''.join(c for c in a if c.isdigit())
            if cleaned:
                _yrs_args.append(cleaned)
        yrs = int(_yrs_args[0]) if _yrs_args else 3
        # Clamp to valid range: 1-10 years
        yrs = max(1, min(10, yrs))

        if _force:
            print(f"\nRunning {yrs}-year walk-forward backtest (FORCE RECOMPUTE)...")
        else:
            print(f"\nRunning {yrs}-year walk-forward backtest (cache-first)...")
            print("  Tip: use --force to bypass cache after data updates.")

        from backtest_engine import run_backtest
        results = run_backtest(lookback_years=yrs, force_recompute=_force)
        if results.get("status") == "ok":
            m = results["metrics"]
            print(f"\n{'='*60}")
            print("BACKTEST SUMMARY" + (" [FROM CACHE]" if results.get("_from_cache") else " [FRESHLY COMPUTED]"))
            print(f"{'='*60}")
            print(f"  Portfolio annualised return : {m['portfolio_annualised_return_pct']:+.2f}%")
            print(f"  NIFTY annualised return     : {m['nifty_annualised_return_pct']:+.2f}%")
            print(f"  Average alpha               : {m['average_alpha_pct']:+.2f}%")
            print(f"  Sharpe ratio                : {m['sharpe_ratio']:.3f}")
            print(f"  Max drawdown                : {m['max_drawdown_pct']:.2f}%")
            print(f"  Win rate                    : {m['win_rate_pct']:.1f}%")
            print(f"  Information ratio           : {m['information_ratio']:.3f}")

    elif cmd == "--performance":
        # Show performance analytics
        from performance_engine import compute_performance_summary
        compute_performance_summary()

    elif cmd == "--portfolio":
        # Run portfolio construction on today's forecasts
        print("\nBuilding today's portfolio allocation...")
        from macro_engine import fetch_live_macro_data, classify_macro_regime
        from ml_forecast_engine import generate_ml_forecasts
        from portfolio_engine import build_portfolio
        from risk_engine import apply_risk_rules
        macro  = fetch_live_macro_data()
        reg    = classify_macro_regime(macro)
        fc     = generate_ml_forecasts(macro, reg)
        port   = build_portfolio(fc, macro, reg, horizon="3M")
        risk_p = apply_risk_rules(port, macro, reg)
        print("\nDone. See output above for allocation details.")

    else:
        print(f"Unknown command: {cmd}")
        print("Run without arguments to see usage.")
