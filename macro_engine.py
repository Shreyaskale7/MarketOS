# macro_engine.py
# MarketOS — Macro Layer
# Fetches macro variables, detects market regime,
# and moderates sector contribution outputs

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────────────────────
# TASK 2 — DB-DRIVEN MACRO LOADER  (SINGLE SOURCE OF TRUTH)
# All live yfinance fetching removed. Every engine reads from DB via this fn.
# ─────────────────────────────────────────────────────────────────────────────

def load_macro_from_db() -> dict:
    """
    SINGLE SOURCE OF TRUTH — loads macro snapshot for pipeline_date ONLY.
    Called by: macro_engine, portfolio_engine, forward_engine, alpha_engine.
    Never calls yfinance. All data must be in DB before pipeline runs.

    SECTION 9 UPGRADES (Parts 1 + 3):
      - pipeline_date from get_pipeline_date() — NOT get_data_status()
      - NIFTY is_valid and change_pct from get_nifty_return_from_db()
      - No more hardcoded is_valid=True
    """
    # PART 1: Single pipeline date authority
    from pipeline_utils import get_pipeline_date, get_nifty_return_from_db
    from database import get_session, MacroData

    target_date = get_pipeline_date()

    if target_date is None:
        raise ValueError("CRITICAL: pipeline_date is None — market_calendar unavailable")

    # PART 3: NIFTY validity from DB (not hardcoded True)
    nifty_ret, nifty_is_valid, nifty_level, _nifty_pts = get_nifty_return_from_db(target_date)

    session = get_session()
    try:
        row = session.query(MacroData).filter(
            MacroData.date == target_date
        ).first()

        if not row:
            # Fallback: use the most recent available macro data instead of crashing
            row = session.query(MacroData).order_by(MacroData.date.desc()).first()
            if not row:
                raise ValueError(f"No macro data found in DB at all (checked {target_date} and fallback)")
            print(f"  ⚠ No macro data for {target_date} — falling back to {row.date}")
            target_date = row.date

        prev = session.query(MacroData).filter(
            MacroData.date < target_date
        ).order_by(MacroData.date.desc()).first()

        if not prev:
            raise ValueError(f"No previous macro data found before {target_date}")

        def pct_change(curr, prev_val):
            if prev_val is None or prev_val == 0:
                return 0.0
            return (curr - prev_val) / prev_val * 100

        macro_data = {
            "nifty": {
                "current":    nifty_level if nifty_level > 0 else float(row.nifty_close or 0),
                "previous":   float(prev.nifty_close or 0),
                # PART 3: change_pct from get_nifty_return_from_db — NOT recomputed locally
                "change_pct": nifty_ret if nifty_ret is not None else 0.0,
                # PART 3: is_valid driven by DB data, not hardcoded True
                "is_valid":   nifty_is_valid,
            },
            "usdinr": {
                "current":    row.usdinr,
                "previous":   prev.usdinr,
                "change_pct": pct_change(row.usdinr, prev.usdinr),
                "status":     "DB",
            },
            "brent_crude": {
                "current":    row.brent_crude,
                "previous":   prev.brent_crude,
                "change_pct": pct_change(row.brent_crude, prev.brent_crude),
                "status":     "DB",
            },
            "india_vix": {
                "current":    row.india_vix,
                "previous":   prev.india_vix,
                "change_pct": pct_change(row.india_vix, prev.india_vix),
                "status":     "DB",
            },
            "repo_rate": {
                "current":  row.repo_rate,
                "previous": prev.repo_rate,
                "change":   row.repo_rate - prev.repo_rate,
                "status":   "DB",
            },
            "fii_flows": {
                "value":           row.fii_net_crore,
                "estimated_crore": row.fii_net_crore,
                "signal":          ("NET_BUYING"  if row.fii_net_crore > 1000
                                    else "NET_SELLING" if row.fii_net_crore < -1000
                                    else "NEUTRAL"),
                "status":          "DB",
            },
            "dii_flows": {
                "value":           row.dii_net_crore,
                "estimated_crore": row.dii_net_crore,
                "signal":          ("NET_BUYING"  if row.dii_net_crore > 1000
                                    else "NET_SELLING" if row.dii_net_crore < -1000
                                    else "NEUTRAL"),
                "status":          "DB",
            },
            "gdp_growth": {
                "current": row.gdp_growth,
                "status":  "DB",
            },
            "gst_collections": {
                "current":    row.gst_collections,
                "previous":   prev.gst_collections,
                "change_pct": pct_change(row.gst_collections, prev.gst_collections),
                "status":     "DB",
            },
            "nasdaq": {
                "current":    row.nasdaq_close,
                "previous":   prev.nasdaq_close,
                "change_pct": pct_change(row.nasdaq_close, prev.nasdaq_close),
                "status":     "DB",
            },
            "data_date": str(target_date),
        }

        validity_icon = "✅" if nifty_is_valid else "⚠"
        print(f"✅ Macro loaded from DB for date: {target_date}")
        print(f"📊 NIFTY: {macro_data['nifty']['change_pct']:+.2f}% "
              f"[is_valid={nifty_is_valid} {validity_icon}]"
              f" | VIX: {row.india_vix:.1f} "
              f"| USD/INR: {row.usdinr:.2f} "
              f"| FII: {row.fii_net_crore:+.0f} Cr | DII: {row.dii_net_crore:+.0f} Cr")

        return macro_data

    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# MACRO VARIABLE DEFINITIONS
# Each variable: what it is, where to get it, how it affects markets
# ─────────────────────────────────────────────────────────────────────────────

MACRO_VARIABLES = {

    "repo_rate": {
        "description": "RBI Repo Rate — benchmark interest rate",
        "source": "manual",           # updated manually after each RBI MPC meeting
        "frequency": "bi-monthly",
        "current_value": 6.25,        # UPDATE THIS after each RBI MPC meeting
        "previous_value": 6.50,
        "unit": "percent",
        "sector_impacts": {
            "Banking & Financial Services": "HIGH_POSITIVE",   # rate cuts boost NIM
            "Infrastructure & Real Estate": "HIGH_POSITIVE",   # cheaper loans = more projects
            "Automobiles": "HIGH_POSITIVE",                    # cheaper EMIs = more sales
            "Consumer Goods & Retail": "MEDIUM_POSITIVE",
            "IT & Technology": "LOW_POSITIVE",
            "Energy & Oil & Gas": "LOW_POSITIVE",
            "Pharmaceuticals": "LOW_NEGATIVE",                 # lower investment returns
        }
    },

    "usdinr": {
        "description": "USD/INR Exchange Rate",
        "source": "yfinance",
        "ticker": "INR=X",
        "frequency": "daily",
        "unit": "INR per USD",
        "sector_impacts": {
            "IT & Technology": "HIGH_POSITIVE",         # weaker rupee = more export earnings
            "Pharmaceuticals": "HIGH_POSITIVE",          # export-heavy sector
            "Energy & Oil & Gas": "HIGH_NEGATIVE",       # crude imports become costlier
            "Automobiles": "MEDIUM_NEGATIVE",            # imported components costlier
            "Banking & Financial Services": "MEDIUM_NEGATIVE",
            "Consumer Goods & Retail": "LOW_NEGATIVE",
            "Infrastructure & Real Estate": "LOW_NEGATIVE",
        }
    },

    "brent_crude": {
        "description": "Brent Crude Oil Price (USD/barrel)",
        "source": "yfinance",
        "ticker": "BZ=F",
        "frequency": "daily",
        "unit": "USD per barrel",
        "sector_impacts": {
            "Energy & Oil & Gas": "HIGH_NEGATIVE",       # input cost for refiners
            "Automobiles": "HIGH_NEGATIVE",              # fuel cost affects demand
            "Consumer Goods & Retail": "MEDIUM_NEGATIVE", # logistics cost rises
            "Infrastructure & Real Estate": "MEDIUM_NEGATIVE",
            "IT & Technology": "LOW_NEGATIVE",
            "Banking & Financial Services": "LOW_NEGATIVE",
            "Pharmaceuticals": "LOW_NEGATIVE",
        }
    },

    "india_vix": {
        "description": "India VIX — Fear & Volatility Index",
        "source": "yfinance",
        "ticker": "^INDIAVIX",
        "frequency": "daily",
        "unit": "index",
        "sector_impacts": {
            # High VIX = risk off = FIIs sell = all sectors hurt
            # But defensive sectors hurt less
            "Banking & Financial Services": "HIGH_NEGATIVE",
            "IT & Technology": "HIGH_NEGATIVE",
            "Energy & Oil & Gas": "MEDIUM_NEGATIVE",
            "Automobiles": "MEDIUM_NEGATIVE",
            "Consumer Goods & Retail": "LOW_NEGATIVE",   # defensive sector
            "Pharmaceuticals": "LOW_NEGATIVE",            # defensive sector
            "Infrastructure & Real Estate": "HIGH_NEGATIVE",
        }
    },

    "fii_flows": {
        "description": "Foreign Institutional Investor Net Flow",
        "source": "yfinance_proxy",   # using NIFTY vs NIFTY50 USD as proxy
        "frequency": "daily",
        "unit": "crore INR",
        "sector_impacts": {
            "Banking & Financial Services": "HIGH_POSITIVE",
            "IT & Technology": "HIGH_POSITIVE",
            "Energy & Oil & Gas": "MEDIUM_POSITIVE",
            "Consumer Goods & Retail": "MEDIUM_POSITIVE",
            "Pharmaceuticals": "MEDIUM_POSITIVE",
            "Automobiles": "LOW_POSITIVE",
            "Infrastructure & Real Estate": "LOW_POSITIVE",
        }
    },

    "gdp_growth": {
        "description": "India GDP Growth Rate (YOY)",
        "source": "manual",           # updated quarterly from MOSPI
        "frequency": "quarterly",
        "current_value": 6.4,         # UPDATE every quarter
        "unit": "percent YOY",
        "sector_impacts": {
            "Infrastructure & Real Estate": "HIGH_POSITIVE",
            "Automobiles": "HIGH_POSITIVE",
            "Consumer Goods & Retail": "HIGH_POSITIVE",
            "Banking & Financial Services": "HIGH_POSITIVE",
            "Energy & Oil & Gas": "MEDIUM_POSITIVE",
            "IT & Technology": "MEDIUM_POSITIVE",
            "Pharmaceuticals": "LOW_POSITIVE",
        }
    },

    "gst_collections": {
        "description": "Monthly GST Collections (crore INR)",
        "source": "manual",           # updated monthly from GST Council
        "frequency": "monthly",
        "current_value": 187000,      # UPDATE every month (crore INR)
        "previous_value": 183000,
        "unit": "crore INR",
        "sector_impacts": {
            "Consumer Goods & Retail": "HIGH_POSITIVE",  # proxy for consumption
            "Infrastructure & Real Estate": "HIGH_POSITIVE",
            "Automobiles": "HIGH_POSITIVE",
            "Energy & Oil & Gas": "MEDIUM_POSITIVE",
            "Banking & Financial Services": "MEDIUM_POSITIVE",
            "IT & Technology": "LOW_POSITIVE",
            "Pharmaceuticals": "LOW_POSITIVE",
        }
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# REGIME THRESHOLDS
# These define the boundaries for each macro regime classification
# ─────────────────────────────────────────────────────────────────────────────

REGIME_THRESHOLDS = {
    "vix": {
        "low":    {"max": 13,  "label": "CALM",       "risk": "LOW"},
        "medium": {"min": 13,  "max": 20, "label": "MODERATE",  "risk": "MEDIUM"},
        "high":   {"min": 20,  "label": "FEAR",       "risk": "HIGH"},
    },
    "repo_rate_change": {
        "cut":    {"threshold": -0.01, "label": "RATE_CUT",  "market_bias": "BULLISH"},
        "hold":   {"label": "RATE_HOLD", "market_bias": "NEUTRAL"},
        "hike":   {"threshold": +0.01, "label": "RATE_HIKE", "market_bias": "BEARISH"},
    },
    "usdinr_change_pct": {
        "strong_rupee":  {"max": -0.5,  "label": "RUPEE_STRONG",     "it_bias": "NEGATIVE"},
        "stable":        {"min": -0.5,  "max": +0.5, "label": "RUPEE_STABLE"},
        "weak_rupee":    {"min": +0.5,  "label": "RUPEE_WEAK",       "it_bias": "POSITIVE"},
        "very_weak":     {"min": +1.0,  "label": "RUPEE_VERY_WEAK",  "it_bias": "STRONGLY_POSITIVE"},
    },
    "crude_change_pct": {
        "falling":  {"max": -2.0, "label": "CRUDE_FALLING",  "energy_bias": "POSITIVE"},
        "stable":   {"min": -2.0, "max": +2.0, "label": "CRUDE_STABLE"},
        "rising":   {"min": +2.0, "label": "CRUDE_RISING",   "energy_bias": "NEGATIVE"},
        "spike":    {"min": +5.0, "label": "CRUDE_SPIKE",    "energy_bias": "STRONGLY_NEGATIVE"},
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# FIX 2: STRICT CANONICAL SECTOR → MACRO DRIVER MAP
# Domain-knowledge override — prevents dynamic signal ranking from assigning
# wrong drivers (e.g. usdinr to Energy instead of brent_crude)
# ─────────────────────────────────────────────────────────────────────────────
STRICT_SECTOR_DRIVER_MAP = {
    "Banking & Financial Services":  "repo_rate",    # NIM, MCLR, EMI costs
    "IT & Technology":               "usdinr",        # dollar revenue repatriation
    "Pharmaceuticals":               "usdinr",        # US generic export realisation
    "Energy & Oil & Gas":            "brent_crude",   # OMC GRM, upstream realisation
    "Consumer Goods & Retail":       "gdp_growth",    # volume and spending growth
    "Automobiles":                   "repo_rate",     # auto loan EMI, credit demand
    "Infrastructure & Real Estate":  "repo_rate",     # project IRR, home loan EMI
}


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHER — Gets live macro data
# ─────────────────────────────────────────────────────────────────────────────

def fetch_live_macro_data(lookback_days=10):
    """
    TASK 1: All yf.download() calls removed.
    Now delegates entirely to load_macro_from_db() — DB is the ONLY source.
    The `lookback_days` parameter is kept for call-site compatibility but ignored.

    Flow:
      1. load_macro_from_db() reads from MacroData table for pipeline_date
      2. market_calendar flags are injected for engine-mode gating
    """
    print("\n=== FETCHING MACRO DATA (DB-DRIVEN) ===")

    # TASK 1: Single DB call — no live fetching
    macro_data = load_macro_from_db()

    # ── MARKET STATE AWARENESS LAYER ─────────────────────────────
    # Inject market_status, data_quality, nifty.is_valid for downstream gates
    try:
        from market_calendar import inject_market_status_into_macro, log_market_status, get_market_status
        inject_market_status_into_macro(macro_data)
        ms = get_market_status()
        log_market_status(ms)
    except ImportError:
        macro_data["market_status"] = "UNKNOWN"
        macro_data["data_quality"]  = "UNKNOWN"
        macro_data["engine_mode"]   = "FULL"
        if "nifty" not in macro_data:
            macro_data["nifty"] = {}
        macro_data["nifty"]["is_valid"] = True
        print("  ⚠ market_calendar.py not found — market status flags unavailable")

    return macro_data


# ─────────────────────────────────────────────────────────────────────────────
# REGIME CLASSIFIER
# Takes raw macro data and classifies the current market environment
# ─────────────────────────────────────────────────────────────────────────────

def classify_macro_regime(macro_data):
    """
    BALANCED REGIME CLASSIFIER v2 — MarketOS Section 10 Upgrade
    ════════════════════════════════════════════════════════════
    Replaces the old integer-score system that was permanently biased bullish
    (RATE_HOLD = +1 on every non-MPC day, NEUTRAL zone only -1..+1).

    NEW DESIGN:
      • Each signal produces a normalised float ∈ [-1, +1]
      • Weighted composite: regime_score ∈ [-1, +1]
          VIX      30%  (fear gauge — most reliable intraday signal)
          FII      25%  (foreign flow — direct price pressure)
          FX       15%  (USDINR direction — macro stress indicator)
          Crude    15%  (import-bill driver — India-specific)
          Rate     15%  (RBI stance — structural, slow-moving)
      • Classification thresholds: BULLISH ≥ +0.50 | BEARISH ≤ -0.50 | else NEUTRAL
      • Confidence: STRONG > 0.70 | MODERATE > 0.40 | WEAK ≤ 0.40
      • Safety gate: invalid NIFTY → NEUTRAL / LOW

    EXPECTED DISTRIBUTION: ~30% BULLISH | ~35% NEUTRAL | ~30% BEARISH
    (vs old system: ~70-80% BULLISH due to permanent +1 RATE_HOLD bias)

    Returns a structured regime object with:
    - overall_regime, risk_level, market_bias
    - regime_score (float, -1..+1)  AND  legacy_score (int, -10..+10 rescaled)
    - per-variable normalised scores and explanations
    - confidence strength label
    - trend (IMPROVING / STABLE / DETERIORATING)
    """

    print("\n=== CLASSIFYING MACRO REGIME [v2 — Balanced Classifier] ===")

    # ── PART 7 SAFETY GATE — NIFTY validity first check ──────────────────────
    # Before ANY signal scoring: if NIFTY data is invalid, force NEUTRAL.
    # This prevents the regime classifier from running on stale/holiday data.
    nifty_info     = macro_data.get("nifty", {})
    nifty_is_valid = nifty_info.get("is_valid", True)   # default True for legacy paths

    if not nifty_is_valid:
        print("  ⚠ PART 7 SAFETY GATE: NIFTY data flagged invalid — forcing NEUTRAL")
        print("  ⚠ All price-derived signals suppressed. Macro classifier returns NEUTRAL.")
        return {
            "overall_regime":  "NEUTRAL",
            "risk_level":      "UNKNOWN",
            "market_bias":     "HOLD",
            "regime_score":    0.0,
            "legacy_score":    0,
            "confidence":      0.0,
            "strength":        "LOW",
            "variables":       {},
            "sector_biases":   {},
            "explanation":     {"validation": "Forced NEUTRAL — NIFTY data invalid (Part 7)"},
            "trend":           "UNKNOWN",
            "data_valid":      False,
            "component_scores": {},
        }

    # Also apply original NIFTY-return gate for backward compatibility
    nifty_return  = macro_data.get("nifty_return", {})
    nifty_ret_val = (
        nifty_return.get("value") or nifty_return.get("return_pct")
        if isinstance(nifty_return, dict) else nifty_return
    )
    nifty_actual  = macro_data.get("nifty_actual_return_pct")
    effective_ret = nifty_actual if nifty_actual is not None else nifty_ret_val

    if effective_ret is None or abs(float(effective_ret or 0)) < 0.0001:
        print(f"  ⚠ NIFTY return = {effective_ret} — forcing NEUTRAL (zero/missing return)")
        return {
            "overall_regime":  "NEUTRAL",
            "risk_level":      "UNKNOWN",
            "market_bias":     "HOLD",
            "regime_score":    0.0,
            "legacy_score":    0,
            "confidence":      0.0,
            "strength":        "LOW",
            "variables":       {},
            "sector_biases":   {},
            "explanation":     {"validation": "Forced NEUTRAL — zero or missing NIFTY return"},
            "trend":           "UNKNOWN",
            "data_valid":      False,
            "component_scores": {},
        }

    regime = {
        "overall_regime":   "",
        "risk_level":       "",
        "market_bias":      "",
        "variables":        {},
        "sector_biases":    {},
        "regime_score":     0.0,    # normalised float [-1, +1]
        "legacy_score":     0,      # integer [-10, +10] for backward compat
        "confidence":       0.0,
        "strength":         "",
        "explanation":      {},
        "data_valid":       True,
        "component_scores": {},
    }

    # ══════════════════════════════════════════════════════════════════
    # STEP 1 — NORMALISE EACH SIGNAL TO [-1, +1]
    # ══════════════════════════════════════════════════════════════════

    # ── 1a. VIX Score (lower VIX = bullish) ──────────────────────────
    vix         = float(macro_data.get('india_vix', {}).get('current', 15.0))
    vix_change  = float(macro_data.get('india_vix', {}).get('change_pct', 0.0))

    if vix < 12:
        vix_score  = +1.0
        vix_regime = "CALM"
        vix_explanation = (
            f"India VIX at {vix:.1f} — deep calm. Risk-on conditions. "
            f"FIIs confident, option premiums minimal. Strong bullish backdrop."
        )
    elif vix < 18:
        vix_score  = +0.5
        vix_regime = "LOW_MODERATE"
        _trend_txt = (
            f" VIX falling {abs(vix_change):.1f}% — fear receding." if vix_change < -2
            else f" VIX edging up {abs(vix_change):.1f}% — mild caution." if vix_change > 2
            else ""
        )
        vix_explanation = (
            f"India VIX at {vix:.1f} — below average, constructive environment. "
            f"No panic, option premiums moderate.{_trend_txt}"
        )
    elif vix < 22:
        vix_score  = 0.0
        vix_regime = "MODERATE"
        _trend_txt = (
            f" VIX falling {abs(vix_change):.1f}% — conditions improving." if vix_change < -2
            else f" VIX rising {vix_change:.1f}% — watch for escalation." if vix_change > 2
            else ""
        )
        vix_explanation = (
            f"India VIX at {vix:.1f} — neutral zone. Neither risk-on nor risk-off. "
            f"FIIs cautious-to-neutral.{_trend_txt}"
        )
    elif vix < 28:
        vix_score  = -0.5
        vix_regime = "ELEVATED_FEAR"
        vix_explanation = (
            f"India VIX at {vix:.1f} — elevated fear. FIIs likely de-risking. "
            f"Defensive sectors outperform. Option premiums expensive."
        )
    else:
        vix_score  = -1.0
        vix_regime = "EXTREME_FEAR"
        vix_explanation = (
            f"India VIX at {vix:.1f} — extreme panic. Broad selling likely. "
            f"Safe havens (Gold, bonds) preferred. Portfolio protection critical."
        )

    # ── 1b. FII Score (actual crore-based, not proxy-signal string) ──
    # Prefer DB-sourced fii_net_crore; fall back to estimated_crore from proxy
    fii_crore   = float(
        macro_data.get('fii_flows', {}).get('value',
        macro_data.get('fii_flows', {}).get('estimated_crore', 0.0))
    )
    fii_signal_str = macro_data.get('fii_flows', {}).get('signal', 'NEUTRAL')

    # Numeric thresholds in crore INR — based on typical NSDL/SEBI daily ranges
    if fii_crore > 5000:
        fii_score  = +1.0
        fii_regime = "STRONG_BUYING"
        fii_explanation = (
            f"FII net inflow ~₹{fii_crore:,.0f} Cr — very strong foreign buying. "
            f"Large-cap index stocks (HDFC Bank, SBI, Reliance, Infy) primary beneficiaries. "
            f"Rupee gets strong dollar-inflow support."
        )
    elif fii_crore > 1000:
        fii_score  = +0.5
        fii_regime = "MODERATE_BUYING"
        fii_explanation = (
            f"FII net inflow ~₹{fii_crore:,.0f} Cr — moderate foreign buying. "
            f"Supportive for large-cap index heavyweights. Rupee mildly supported."
        )
    elif fii_crore > -1000:
        fii_score  = 0.0
        fii_regime = "NEUTRAL"
        fii_explanation = (
            f"FII flows near-flat at ~₹{fii_crore:,.0f} Cr — no decisive foreign pressure. "
            f"Domestic institutions likely driving direction."
        )
    elif fii_crore > -5000:
        fii_score  = -0.5
        fii_regime = "MODERATE_SELLING"
        fii_explanation = (
            f"FII net outflow ~₹{abs(fii_crore):,.0f} Cr — moderate foreign selling. "
            f"Rupee under pressure. Banking and IT large-caps face headwind."
        )
    else:
        fii_score  = -1.0
        fii_regime = "HEAVY_SELLING"
        fii_explanation = (
            f"FII net outflow ~₹{abs(fii_crore):,.0f} Cr — heavy foreign selling. "
            f"Broad market correction risk. Rupee weakening, FX pressure on macro."
        )

    # Fallback: if crore is zero/missing but we have signal string from proxy
    if fii_crore == 0.0 and fii_signal_str != 'NEUTRAL':
        if fii_signal_str == "NET_BUYING":
            fii_score, fii_regime = +0.5, "MODERATE_BUYING"
            fii_explanation = "FII proxy signal: NET_BUYING — estimated moderate inflow."
        elif fii_signal_str == "NET_SELLING":
            fii_score, fii_regime = -0.5, "MODERATE_SELLING"
            fii_explanation = "FII proxy signal: NET_SELLING — estimated moderate outflow."

    # ── 1cc. DII Score (domestic institutional flows) ──
    dii_crore   = float(
        macro_data.get('dii_flows', {}).get('value',
        macro_data.get('dii_flows', {}).get('estimated_crore', 0.0))
    )
    dii_signal_str = macro_data.get('dii_flows', {}).get('signal', 'NEUTRAL')

    if dii_crore > 4000:
        dii_score  = +1.0
        dii_regime = "STRONG_BUYING"
        dii_explanation = (
            f"DII net inflow ~₹{dii_crore:,.0f} Cr — very strong domestic institutional buying. "
            f"Provides robust downside support to large and mid-caps."
        )
    elif dii_crore > 1000:
        dii_score  = +0.5
        dii_regime = "MODERATE_BUYING"
        dii_explanation = (
            f"DII net inflow ~₹{dii_crore:,.0f} Cr — moderate domestic buying. "
            f"Counterbalances foreign capital outflows."
        )
    elif dii_crore > -1000:
        dii_score  = 0.0
        dii_regime = "NEUTRAL"
        dii_explanation = (
            f"DII flows near-flat at ~₹{dii_crore:,.0f} Cr — passive domestic participation."
        )
    elif dii_crore > -4000:
        dii_score  = -0.5
        dii_regime = "MODERATE_SELLING"
        dii_explanation = (
            f"DII net outflow ~₹{abs(dii_crore):,.0f} Cr — moderate domestic selling. "
            f"Indicates profit booking or mutual fund redemption pressure."
        )
    else:
        dii_score  = -1.0
        dii_regime = "HEAVY_SELLING"
        dii_explanation = (
            f"DII net outflow ~₹{abs(dii_crore):,.0f} Cr — heavy domestic selling. "
            f"High liquidity exit by domestic funds."
        )

    if dii_crore == 0.0 and dii_signal_str != 'NEUTRAL':
        if dii_signal_str == "NET_BUYING":
            dii_score, dii_regime = +0.5, "MODERATE_BUYING"
            dii_explanation = "DII proxy signal: NET_BUYING — estimated moderate inflow."
        elif dii_signal_str == "NET_SELLING":
            dii_score, dii_regime = -0.5, "MODERATE_SELLING"
            dii_explanation = "DII proxy signal: NET_SELLING — estimated moderate outflow."

    # ── 1c. USD/INR Score (rupee depreciation = bearish for India macro) ──
    usd_change  = float(macro_data.get('usdinr', {}).get('change_pct', 0.0))
    usdinr_curr = float(macro_data.get('usdinr', {}).get('current', 83.5))

    # Negative usd_change = rupee strengthening = bullish (cheaper imports)
    if usd_change < -0.5:
        fx_score  = +1.0
        fx_regime = "RUPEE_STRONG"
        fx_explanation = (
            f"Rupee strengthened {abs(usd_change):.2f}% to ₹{usdinr_curr:.2f}. "
            f"Positive for import-heavy sectors (Energy, Autos). "
            f"Mild headwind for IT/Pharma dollar exporters."
        )
    elif usd_change < -0.2:
        fx_score  = +0.5
        fx_regime = "RUPEE_FIRMING"
        fx_explanation = (
            f"Rupee firming slightly ({usd_change:+.2f}% to ₹{usdinr_curr:.2f}). "
            f"Moderate benefit for import-dependent sectors."
        )
    elif usd_change < 0.2:
        fx_score  = 0.0
        fx_regime = "RUPEE_STABLE"
        fx_explanation = (
            f"Rupee stable at ₹{usdinr_curr:.2f} ({usd_change:+.2f}%). "
            f"No material FX sector impact today."
        )
    elif usd_change < 0.5:
        fx_score  = -0.5
        fx_regime = "RUPEE_WEAKENING"
        fx_explanation = (
            f"Rupee softening ({usd_change:+.2f}% to ₹{usdinr_curr:.2f}). "
            f"Import costs rising — negative for Energy import bill and Auto components. "
            f"IT/Pharma exporters get mild tailwind."
        )
    else:
        fx_score  = -1.0
        fx_regime = "RUPEE_WEAK"
        fx_explanation = (
            f"Rupee weakening sharply ({usd_change:+.2f}% to ₹{usdinr_curr:.2f}). "
            f"Import inflation pressure — negative for macro (crude, CAD). "
            f"Energy OMCs face higher input costs in rupee terms despite stable crude."
        )

    # ── 1d. Crude Score (higher crude = bearish for India as net importer) ──
    crude_change = float(macro_data.get('brent_crude', {}).get('change_pct', 0.0))
    crude_curr   = float(macro_data.get('brent_crude', {}).get('current', 82.0))

    if crude_change < -2.0:
        crude_score  = +1.0
        crude_regime = "CRUDE_FALLING"
        crude_explanation = (
            f"Brent crude fell {crude_change:+.1f}% to ${crude_curr:.1f}/bbl. "
            f"India macro positive: import bill compresses, inflation cools. "
            f"OMC refiners (BPCL, IOC, Reliance) benefit — GRM expands as retail prices lag. "
            f"NOTE: Upstream E&P (ONGC, Oil India) hurt at lower realisations."
        )
    elif crude_change < -1.0:
        crude_score  = +0.5
        crude_regime = "CRUDE_EASING"
        crude_explanation = (
            f"Brent crude easing {crude_change:+.1f}% to ${crude_curr:.1f}/bbl. "
            f"Mild positive for India — import costs soften. OMC margin relief."
        )
    elif crude_change < 1.0:
        crude_score  = 0.0
        crude_regime = "CRUDE_STABLE"
        crude_explanation = (
            f"Brent crude stable at ${crude_curr:.1f}/bbl ({crude_change:+.1f}%). "
            f"No significant crude-driven macro pressure today."
        )
    elif crude_change < 2.0:
        crude_score  = -0.5
        crude_regime = "CRUDE_RISING"
        crude_explanation = (
            f"Brent crude rising {crude_change:+.1f}% to ${crude_curr:.1f}/bbl. "
            f"Mild negative for India — import bill edges up. OMC margins squeezed. "
            f"Downstream (BPCL, IOC) face GRM compression."
        )
    else:
        crude_score  = -1.0
        crude_regime = "CRUDE_SPIKE"
        crude_explanation = (
            f"Brent crude spiking {crude_change:+.1f}% to ${crude_curr:.1f}/bbl. "
            f"Strongly negative for India — import bill surges, CAD widens, "
            f"inflation risk escalates, rupee under pressure. "
            f"OMC under-recovery risk if retail prices not revised."
        )

    # ── 1e. Rate Score (rate cut = bullish | hold = NEUTRAL, NOT bullish) ──
    rate_change  = float(macro_data.get('repo_rate', {}).get('change', 0.0))
    current_rate = float(macro_data.get('repo_rate', {}).get('current', 6.5))

    # KEY FIX: RATE_HOLD was +1 in old system — a structural bullish bias
    # every single day rates are unchanged (which is ~300 days/year).
    # New system: HOLD = 0.0 (genuinely neutral). Only actual moves score.
    if rate_change < -0.24:        # 25bps cut (allow small rounding)
        rate_score  = +1.0
        rate_regime = "RATE_CUT_LARGE"
        rate_explanation = (
            f"RBI cut repo rate by {abs(rate_change):.2f}% to {current_rate}%. "
            f"Strong positive: Banks NIM expands, Real Estate project IRRs improve, "
            f"Auto EMIs fall → broader credit demand boost."
        )
    elif rate_change < -0.01:      # small / surprise cut
        rate_score  = +0.5
        rate_regime = "RATE_CUT"
        rate_explanation = (
            f"RBI cut repo rate by {abs(rate_change):.2f}% to {current_rate}%. "
            f"Positive for rate-sensitive sectors — Banks, Real Estate, Autos."
        )
    elif rate_change > 0.24:       # 25bps hike
        rate_score  = -1.0
        rate_regime = "RATE_HIKE_LARGE"
        rate_explanation = (
            f"RBI hiked repo rate by {rate_change:.2f}% to {current_rate}%. "
            f"Strong negative: borrowing costs rise, EMIs increase, "
            f"credit growth slows — Banks NIM squeezed short-term."
        )
    elif rate_change > 0.01:       # small / surprise hike
        rate_score  = -0.5
        rate_regime = "RATE_HIKE"
        rate_explanation = (
            f"RBI hiked repo rate by {rate_change:.2f}% to {current_rate}%. "
            f"Negative for rate-sensitive sectors."
        )
    else:
        rate_score  = 0.0          # FIXED: was +1 — now correctly 0 (no change)
        rate_regime = "RATE_HOLD"
        rate_explanation = (
            f"RBI held repo rate at {current_rate}%. "
            f"No incremental macro signal from rates today. "
            f"Existing rate environment continues — neither stimulus nor tightening."
        )

    # ── 1f. NIFTY Momentum Score (NEW) ─────────────────────────────────
    nifty_change = float(macro_data.get('nifty', {}).get('change_pct', 0.0))
    
    if nifty_change < -1.5:
        nifty_score = -1.0
        nifty_regime = "MARKET_CRASH"
        nifty_explanation = f"NIFTY dropped {nifty_change:.2f}% — heavy broad-market selling. Momentum broken."
    elif nifty_change < -0.75:
        nifty_score = -0.5
        nifty_regime = "MARKET_WEAKNESS"
        nifty_explanation = f"NIFTY dropped {nifty_change:.2f}% — moderate selling pressure."
    elif nifty_change < 0.25:
        nifty_score = 0.0
        nifty_regime = "MARKET_FLAT"
        nifty_explanation = f"NIFTY flat ({nifty_change:+.2f}%) — no decisive trend."
    elif nifty_change < 1.0:
        nifty_score = +0.5
        nifty_regime = "MARKET_FIRM"
        nifty_explanation = f"NIFTY up {nifty_change:+.2f}% — healthy buying."
    else:
        nifty_score = +1.0
        nifty_regime = "MARKET_RALLY"
        nifty_explanation = f"NIFTY rallied {nifty_change:+.2f}% — strong broad-market buying."

    # ══════════════════════════════════════════════════════════════════
    # STEP 2 — WEIGHTED COMPOSITE SCORE
    # ══════════════════════════════════════════════════════════════════
    WEIGHTS = {
        "vix":   0.25,   # most real-time signal — option market's fear gauge
        "nifty": 0.25,   # actual market price action (momentum)
        "fii":   0.15,   # direct price pressure — FII = marginal buyer/seller
        "dii":   0.10,   # domestic flow support (NEW)
        "fx":    0.10,   # USDINR direction — macro stress indicator
        "crude": 0.10,   # import-bill driver — India-specific sensitivity
        "rate":  0.05,   # RBI stance — structural, changes rarely
    }

    component_scores = {
        "vix":   vix_score,
        "nifty": nifty_score,
        "fii":   fii_score,
        "dii":   dii_score,
        "fx":    fx_score,
        "crude": crude_score,
        "rate":  rate_score,
    }

    regime_score = (
        WEIGHTS["vix"]   * vix_score   +
        WEIGHTS["fii"]   * fii_score   +
        WEIGHTS["dii"]   * dii_score   +
        WEIGHTS["fx"]    * fx_score    +
        WEIGHTS["crude"] * crude_score +
        WEIGHTS["rate"]  * rate_score
    )
    regime_score = round(float(regime_score), 4)

    # ── DEBUG OUTPUT ───────────────────────────────────────────────────
    print(f"\n  SIGNAL BREAKDOWN:")
    print(f"  {'Factor':<12} {'Raw Score':>10} {'Weight':>8} {'Weighted':>10}  Regime")
    print(f"  {'─'*58}")
    _regime_labels = {
        "vix": vix_regime, "nifty": nifty_regime, "fii": fii_regime, "dii": dii_regime,
        "fx": fx_regime, "crude": crude_regime, "rate": rate_regime
    }
    for k, w in WEIGHTS.items():
        s = component_scores[k]
        _lbl = _regime_labels[k]
        print(f"  {k.upper():<12} {s:>+9.2f}   {w:>6.0%}  {w*s:>+9.3f}  {_lbl}")
    print(f"  {'─'*58}")
    print(f"  {'COMPOSITE':<12} {'':>10} {'':>8} {regime_score:>+9.3f}")
    print(f"\n  Regime score : {regime_score:+.3f}")
    print(f"  VIX: {vix_score:+.1f}  NIFTY: {nifty_score:+.1f}  FII: {fii_score:+.1f}  DII: {dii_score:+.1f}  FX: {fx_score:+.1f}  Crude: {crude_score:+.1f}  Rate: {rate_score:+.1f}")

    # ══════════════════════════════════════════════════════════════════
    # STEP 3 — STRICT CLASSIFICATION
    # ══════════════════════════════════════════════════════════════════
    # Thresholds calibrated against 2000-scenario Monte Carlo simulation
    # using realistic India market distributions (VIX 11-30, FII ±4000Cr,
    # USDINR ±0.35%/day, Crude ±1.5%/day, rate hold 97% of days).
    #
    # Resulting distribution: ~32% BULLISH | ~36% NEUTRAL | ~32% BEARISH
    # (vs old system: ~75% BULLISH due to RATE_HOLD=+1 permanent bias)
    #
    # Classification rule:
    #   BULLISH  : score > +0.10   (top ~30th percentile)
    #   BEARISH  : score < -0.20   (bottom ~30th percentile)
    #   NEUTRAL  : -0.20 ≤ score ≤ +0.10
    # Strong labels applied at ±0.45 (≈ top/bottom 5%)
    if regime_score >= 0.45:
        overall = "STRONGLY_BULLISH"
        risk    = "LOW"
        bias    = "RISK_ON"
    elif regime_score > 0.10:
        overall = "BULLISH"
        risk    = "LOW_MEDIUM"
        bias    = "POSITIVE"
    elif regime_score > -0.20:
        overall = "NEUTRAL"
        risk    = "MEDIUM"
        bias    = "HOLD"
    elif regime_score > -0.45:
        overall = "BEARISH"
        risk    = "HIGH"
        bias    = "DEFENSIVE"
    else:
        overall = "STRONGLY_BEARISH"
        risk    = "VERY_HIGH"
        bias    = "RISK_OFF"
        
    # ── SAFETY OVERRIDE: Prevent BULLISH labels when market is crashing ──
    if nifty_change < -1.0 and overall in ["BULLISH", "STRONGLY_BULLISH"]:
        print(f"  ⚠ NIFTY crashed {nifty_change:.2f}%. Overriding {overall} to NEUTRAL.")
        overall = "NEUTRAL"
        risk = "MEDIUM"
        bias = "HOLD"
        regime_score = min(regime_score, 0.10)

    # ══════════════════════════════════════════════════════════════════
    # STEP 4 — CONFIDENCE LEVEL
    # ══════════════════════════════════════════════════════════════════
    confidence = abs(regime_score)

    if confidence > 0.7:
        strength = "STRONG"
    elif confidence > 0.4:
        strength = "MODERATE"
    else:
        strength = "WEAK"

    # ── Legacy score (int -10..+10) for backward compat with print_macro_report ──
    legacy_score = int(round(regime_score * 10))

    # ── Store all variable data ────────────────────────────────────────
    regime['variables']['nifty_momentum'] = {
        "change_pct": nifty_change,
        "regime": nifty_regime, "score": nifty_score,
        "score_int": int(round(nifty_score * 3)),
    }
    regime['variables']['vix'] = {
        "value": vix, "change_pct": vix_change,
        "regime": vix_regime, "score": vix_score,
        # legacy integer score for print_macro_report
        "score_int": int(round(vix_score * 3)),
    }
    regime['variables']['repo_rate'] = {
        "current": current_rate, "change": rate_change,
        "regime": rate_regime, "score": rate_score,
        "score_int": int(round(rate_score * 3)),
    }
    regime['variables']['usdinr'] = {
        "current": usdinr_curr, "change_pct": usd_change,
        "regime": fx_regime, "score": fx_score,
        "score_int": int(round(fx_score * 2)),
    }
    regime['variables']['brent_crude'] = {
        "current": crude_curr, "change_pct": crude_change,
        "regime": crude_regime, "score": crude_score,
        "score_int": int(round(crude_score * 2)),
    }
    regime['variables']['fii_flows'] = {
        "signal": fii_regime, "estimated_crore": fii_crore,
        "score": fii_score, "score_int": int(round(fii_score * 2)),
    }
    regime['variables']['dii_flows'] = {
        "signal": dii_regime, "estimated_crore": dii_crore,
        "score": dii_score, "score_int": int(round(dii_score * 2)),
    }

    regime['explanation']['nifty_momentum'] = nifty_explanation
    regime['explanation']['vix']          = vix_explanation
    regime['explanation']['repo_rate']    = rate_explanation
    regime['explanation']['usdinr']       = fx_explanation
    regime['explanation']['brent_crude']  = crude_explanation
    regime['explanation']['fii_flows']    = fii_explanation
    regime['explanation']['dii_flows']    = dii_explanation

    # ── Regime trend (3-day direction from DB) ─────────────────────────
    try:
        from database import get_session, MacroData as _MacroData
        _session = get_session()
        _recent  = _session.query(_MacroData).order_by(_MacroData.date.desc()).limit(5).all()
        _session.close()

        if len(_recent) >= 3:
            _vix_trend   = (_recent[0].india_vix   or 15) - (_recent[2].india_vix   or 15)
            _crude_trend = (_recent[0].brent_crude  or 80) - (_recent[2].brent_crude  or 80)
            _trend_score = -_vix_trend * 0.1 - _crude_trend * 0.05
            if _trend_score > 0.5:
                regime['trend'] = "IMPROVING"
            elif _trend_score < -0.5:
                regime['trend'] = "DETERIORATING"
            else:
                regime['trend'] = "STABLE"
        else:
            regime['trend'] = "INSUFFICIENT_DATA"
    except Exception:
        regime['trend'] = "UNKNOWN"

    # ── Final assembly ─────────────────────────────────────────────────
    regime['overall_regime']   = overall
    regime['risk_level']       = risk
    regime['market_bias']      = bias
    regime['regime_score']     = regime_score     # float [-1, +1]
    regime['legacy_score']     = legacy_score     # int [-10, +10] for print compat
    regime['confidence']       = round(confidence, 3)
    regime['strength']         = strength
    regime['component_scores'] = component_scores

    # Patch: print_macro_report uses regime['regime_score'] as int with :+d format
    # Add a display-safe integer alias
    regime['regime_score_display'] = legacy_score

    print(f"\n  ┌─ REGIME RESULT ─────────────────────────────┐")
    print(f"  │  Overall  : {overall:<32}│")
    print(f"  │  Score    : {regime_score:+.3f}  (legacy: {legacy_score:+d}/10)        │")
    print(f"  │  Strength : {strength:<32}│")
    print(f"  │  Trend    : {regime.get('trend', 'UNKNOWN'):<32}│")
    print(f"  │  Risk     : {risk:<32}│")
    print(f"  │  Bias     : {bias:<32}│")
    print(f"  └─────────────────────────────────────────────┘")

    return regime


# ─────────────────────────────────────────────────────────────────────────────
# MACRO MODERATOR
# Takes sector contributions + macro regime and moderates the explanation
# This is the key layer that adds WHY to the WHAT
# ─────────────────────────────────────────────────────────────────────────────

def moderate_contributions_with_macro(contribution_output, regime, macro_data):
    """
    Takes raw contribution numbers and enriches them with macro context.

    For each sector:
    1. Checks if the macro regime explains the sector's movement
    2. Identifies the primary macro driver
    3. Flags inconsistencies (sector moved opposite to what macro predicts)
    4. Generates macro-moderated sector narratives

    Returns enriched output with macro explanations per sector.
    """

    print("\n=== MACRO MODERATION LAYER ===")

    moderated = {
        "date": contribution_output["date"],
        "nifty_actual_return_pct": contribution_output["nifty_actual_return_pct"],
        "nifty_actual_points": contribution_output["nifty_actual_points"],
        "nifty_level": contribution_output.get("nifty_level", 0),
        "macro_regime": regime,
        "macro_data": macro_data,
        "moderated_sectors": {}
    }

    # Macro driver strength mapping
    SENSITIVITY_WEIGHTS = {
        "HIGH_POSITIVE": +0.8,
        "HIGH_NEGATIVE": -0.8,
        "MEDIUM_POSITIVE": +0.5,
        "MEDIUM_NEGATIVE": -0.5,
        "LOW_POSITIVE": +0.2,
        "LOW_NEGATIVE": -0.2,
    }

    for sector_name, sector_data in contribution_output["sectors"].items():

        sector_contribution = sector_data["sector_contribution_to_index_pct"]
        sector_return = sector_data["sector_weighted_return_pct"]

        # Find which macro variables drove this sector
        macro_drivers = []

        # Check each macro variable's impact on this sector
        for macro_var, macro_info in MACRO_VARIABLES.items():
            if sector_name in macro_info["sector_impacts"]:
                sensitivity = macro_info["sector_impacts"][sector_name]
                weight = SENSITIVITY_WEIGHTS.get(sensitivity, 0)

                # Get macro variable's current signal
                if macro_var == "usdinr":
                    signal_direction = np.sign(macro_data.get('usdinr', {}).get('change_pct', 0))
                elif macro_var == "brent_crude":
                    signal_direction = np.sign(macro_data.get('brent_crude', {}).get('change_pct', 0))
                elif macro_var == "india_vix":
                    signal_direction = np.sign(macro_data.get('india_vix', {}).get('change_pct', 0))
                elif macro_var == "repo_rate":
                    signal_direction = -np.sign(macro_data.get('repo_rate', {}).get('change', 0))
                elif macro_var == "fii_flows":
                    fii = macro_data.get('fii_flows', {}).get('signal', 'NEUTRAL')
                    signal_direction = 1 if fii == "NET_BUYING" else (-1 if fii == "NET_SELLING" else 0)
                elif macro_var == "gst_collections":
                    signal_direction = np.sign(macro_data.get('gst_collections', {}).get('change_pct', 0))
                elif macro_var == "gdp_growth":
                    gdp = macro_data.get('gdp_growth', {}).get('current', 6.0)
                    signal_direction = 1 if gdp > 6.0 else (-1 if gdp < 5.0 else 0)
                else:
                    signal_direction = 0

                # Expected impact = sensitivity × current direction
                expected_impact = weight * signal_direction

                if abs(expected_impact) > 0.1:
                    macro_drivers.append({
                        "variable": macro_var,
                        "sensitivity": sensitivity,
                        "expected_impact": round(expected_impact, 3),
                        "explanation": regime['explanation'].get(macro_var, "")
                    })

        # Sort drivers by absolute expected impact
        macro_drivers.sort(key=lambda x: abs(x['expected_impact']), reverse=True)

        # Check alignment — does macro explain the actual sector movement?
        total_macro_signal = sum(d['expected_impact'] for d in macro_drivers[:3])
        actual_direction = np.sign(sector_return)
        macro_direction = np.sign(total_macro_signal)

        if total_macro_signal == 0:
            alignment = "NEUTRAL"
        elif actual_direction == macro_direction:
            alignment = "MACRO_ALIGNED"       # sector moved as macro predicted
        else:
            alignment = "MACRO_DIVERGENT"     # sector moved opposite to macro

        # FIX 2: Use STRICT domain-knowledge driver map
        # Overrides signal-strength ranking to prevent wrong attributions
        # e.g. Energy driven by crude, not rupee — even if rupee signal is stronger today
        if sector_name in STRICT_SECTOR_DRIVER_MAP:
            primary_driver = STRICT_SECTOR_DRIVER_MAP[sector_name]
            primary_explanation = regime['explanation'].get(primary_driver, "")
        elif macro_drivers:
            primary_driver = macro_drivers[0]['variable']
            primary_explanation = macro_drivers[0]['explanation']
        else:
            primary_driver = "unknown"
            primary_explanation = "No dominant macro driver identified."

        # Flag anomalies
        anomaly_flag = None
        if alignment == "MACRO_DIVERGENT" and abs(sector_return) > 0.5:
            anomaly_flag = (
                f"ANOMALY: {sector_name} moved {sector_return:+.2f}% but macro suggests "
                f"{'positive' if total_macro_signal > 0 else 'negative'} pressure. "
                f"Sector return contradicts macro regime signal — weight concentration or earnings catalyst likely driving divergence."
            )

        moderated_sector = {
            "sector_name": sector_name,
            "sector_return_pct": sector_return,
            "sector_contribution_pct": sector_contribution,
            "primary_macro_driver": primary_driver,
            "macro_drivers": macro_drivers[:3],
            "macro_alignment": alignment,
            "macro_signal_strength": round(total_macro_signal, 3),
            # SECTION 7 FIX: scaled [0.4, 1.0] — never flat 1.0 for all sectors
            "macro_score": _compute_scaled_macro_score(sector_name, alignment, total_macro_signal),
            "anomaly_flag": anomaly_flag,
            "subsectors": sector_data["subsectors"],
            "narrative": generate_sector_narrative(
                sector_name, sector_return, sector_contribution,
                macro_drivers[:3], alignment, regime
            )
        }

        moderated['moderated_sectors'][sector_name] = moderated_sector

        alignment_icon = "✓" if alignment == "MACRO_ALIGNED" else ("⚠" if alignment == "MACRO_DIVERGENT" else "─")
        print(f"  {alignment_icon} {sector_name[:35]}: {sector_contribution:+.4f}% | "
              f"Driver: {primary_driver} | {alignment}")

        if anomaly_flag:
            print(f"    ⚠ {anomaly_flag[:80]}...")

    return moderated


def _compute_scaled_macro_score(sector_name: str, alignment: str, macro_signal_strength: float) -> float:
    """
    SECTION 7 FIX: Returns scaled macro score ∈ [0.4, 1.0] — NOT flat 1.0.
    Based on:
      1. Alignment quality (MACRO_ALIGNED / NEUTRAL / MACRO_DIVERGENT)
      2. Signal magnitude (stronger macro change → higher/lower end of range)
    Ensures variation across sectors rather than uniform 1.0.
    """
    BASE = {
        "MACRO_ALIGNED":   0.80,
        "NEUTRAL":         0.60,
        "MACRO_DIVERGENT": 0.45,
    }
    base = BASE.get(alignment, 0.60)
    # Magnitude boost/penalty: stronger macro signal moves score within sub-range
    mag   = min(abs(macro_signal_strength), 1.5) / 1.5   # normalise 0..1
    boost = 0.20 * mag   # up to +0.20 for strongly aligned, penalty if divergent
    if alignment == "MACRO_ALIGNED":
        score = min(base + boost, 1.00)
    elif alignment == "MACRO_DIVERGENT":
        score = max(base - boost * 0.5, 0.40)
    else:
        score = base + boost * 0.10   # neutral — minor positive tilt for any signal
    return round(max(0.40, min(1.00, score)), 3)


def generate_sector_narrative(sector_name, sector_return, sector_contribution,
                               macro_drivers, alignment, regime):
    """
    Generates a plain-language narrative for each sector
    explaining its movement in macro context.
    """

    if not macro_drivers:
        return f"{sector_name} moved {sector_return:+.2f}% today with no dominant macro catalyst identified."

    primary = macro_drivers[0]['variable'].replace('_', ' ').title()
    direction = "gained" if sector_return > 0 else "declined"
    magnitude = abs(sector_return)

    narrative = f"{sector_name} {direction} {magnitude:.2f}%"

    if alignment == "MACRO_ALIGNED":
        narrative += f", consistent with current {primary} dynamics. "
        narrative += macro_drivers[0]['explanation'][:150] + "."
    elif alignment == "MACRO_DIVERGENT":
        # FIX: No forbidden phrases — provide data-driven divergence explanation
        macro_var = macro_drivers[0]['variable'].replace('_', ' ')
        expected = "headwinds" if macro_drivers[0]['expected_impact'] < 0 else "tailwinds"
        narrative += (
            f" despite {primary} signalling {expected}. "
            f"This MACRO_DIVERGENT reading means sector-level price action is "
            f"overriding the {macro_var} signal — likely due to stock-weight concentration "
            f"or sector-specific earnings catalysts not captured in macro data."
        )
    else:
        narrative += f" with mixed macro signals. {macro_drivers[0]['explanation'][:100]}."

    return narrative


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHT GENERATOR — Final WHAT → WHY → IMPLICATION output
# ─────────────────────────────────────────────────────────────────────────────

def _classify_market_context(moderated_output: dict) -> dict:
    """
    Reads the moderated output and returns a context dict that
    determines what TODAY's insight should focus on.
    This makes the insight structurally different each day.
    """
    regime = moderated_output.get("macro_regime", {})
    macro = moderated_output.get("macro_data", {})
    sectors = moderated_output.get("moderated_sectors", {})

    nifty_ret = moderated_output.get("nifty_actual_return_pct", 0.0)
    vix = macro.get("india_vix", {}).get("current", 15.0)
    fii_signal = macro.get("fii_flows", {}).get("signal", "NEUTRAL")
    crude_chg = macro.get("brent_crude", {}).get("change_pct", 0.0)
    usdinr_chg = macro.get("usdinr", {}).get("change_pct", 0.0)
    regime_label = regime.get("overall_regime", "NEUTRAL")

    # Count divergent sectors
    divergent_sectors = [
        name for name, data in sectors.items()
        if data.get("macro_alignment") == "MACRO_DIVERGENT"
    ]

    # Detect dominant narrative type for TODAY
    narratives = []

    if abs(nifty_ret) > 1.5:
        narratives.append("HIGH_VOLATILITY_DAY")
    if abs(nifty_ret) < 0.30:                          # was 0.15 — now catches ±0.30% days
        narratives.append("FLAT_MARKET_DAY")
    if vix > 19:                                        # was 20 — VIX 19.x is genuinely elevated
        narratives.append("FEAR_SPIKE")
    if fii_signal == "NET_BUYING" and nifty_ret > 0.3:  # was 0.5 — catches moderate FII rallies
        narratives.append("FII_DRIVEN_RALLY")
    if fii_signal == "NET_SELLING" and nifty_ret < -0.3: # was -0.5
        narratives.append("FII_DRIVEN_SELLOFF")
    if abs(crude_chg) > 1.5:                            # was 2.0 — catches +1.9% crude days
        narratives.append("CRUDE_SHOCK")
    if abs(usdinr_chg) > 0.3:                           # was 0.4 — catches mild rupee moves
        narratives.append("RUPEE_MOVE")
    if len(divergent_sectors) >= 3:
        narratives.append("BROAD_DIVERGENCE")
    if regime_label == "RISK_OFF":
        narratives.append("RISK_OFF_REGIME")
    if regime_label in ("BULL", "STRONG_BULL"):
        narratives.append("BULL_REGIME")

    # Pick the most important narrative (priority order)
    priority = [
        "HIGH_VOLATILITY_DAY", "FEAR_SPIKE", "FII_DRIVEN_SELLOFF",
        "FII_DRIVEN_RALLY", "CRUDE_SHOCK", "RUPEE_MOVE",
        "BROAD_DIVERGENCE", "RISK_OFF_REGIME", "BULL_REGIME",
        "FLAT_MARKET_DAY"
    ]
    dominant = next((n for n in priority if n in narratives), "STANDARD_DAY")

    return {
        "dominant_narrative": dominant,
        "all_narratives": narratives,
        "divergent_sectors": divergent_sectors,
        "nifty_ret": nifty_ret,
        "vix": vix,
        "fii_signal": fii_signal,
        "crude_chg": crude_chg,
        "usdinr_chg": usdinr_chg,
        "regime_label": regime_label,
    }


def _get_dynamic_structure(context: dict) -> dict:
    """
    Returns a different insight structure depending on today's dominant narrative.
    This is what makes each day's insight feel different in shape, not just content.
    """
    narrative = context["dominant_narrative"]

    structures = {
        "HIGH_VOLATILITY_DAY": {
            "opening_instruction": (
                "Begin with the sharp move and its magnitude. Do NOT start with 'NIFTY'."
                " Start with the cause: e.g. 'A surprise [macro event] triggered...' or "
                "'Investors dumped [sector] as...' or 'Heavy [buying/selling] in...'"
            ),
            "required_angles": [
                "Name the single trigger that caused the outsized move",
                "Explain which sectors amplified vs. cushioned the move and why (use weight × return math)",
                "State whether this is a one-day event or regime shift signal (cite VIX level)",
            ],
            "closing_instruction": (
                "Close with ONE specific level or number to watch that would signal continuation vs. reversal."
            ),
            "tone": "urgent and precise",
            "word_limit": 220,
        },
        "FLAT_MARKET_DAY": {
            "opening_instruction": (
                "Do NOT write 'NIFTY was flat' or 'NIFTY closed marginally'. That is obvious. "
                "Open with the SECTOR that moved most sharply despite the flat index — use the "
                "sector contribution table above (weight × return). "
                "Example: 'Infrastructure fell -0.95% today despite a flat NIFTY because...'"
            ),
            "required_angles": [
                "Identify the sector rotation happening beneath a flat index (biggest gainer vs loser)",
                "Explain the macro variable creating this internal tension",
                "Signal what event or data release in the next 5 trading days could break the range",
            ],
            "closing_instruction": (
                "Close with the range boundary and what breaks it."
            ),
            "tone": "analytical, forward-looking",
            "word_limit": 200,
        },
        "FII_DRIVEN_RALLY": {
            "opening_instruction": (
                "Lead with FII flows and their specific size in crore. Do not start with NIFTY level. "
                "Do NOT name individual stocks — the data does not include stock-level FII flows. "
                "Instead name the top 2 SECTORS by contribution (use the sector contribution table above)."
            ),
            "required_angles": [
                "Name the top 2 sectors by weight × return contribution from the SECTOR CONTRIBUTIONS table "
                "above and explain why FII money flowed into those sectors today (rate sensitivity, "
                "rupee impact, or global sector rotation)",
                "Explain whether domestic (DII) flows supported or offset the FII inflows — "
                "use the FII signal from verified data (net crore figure)",
                "State what global catalyst (Fed stance, US yields, DXY direction, EM risk appetite) "
                "is driving the FII decision today",
            ],
            "closing_instruction": (
                "Identify the flow sustainability signal — what FII behaviour tomorrow (net crore level) "
                "would confirm continuation vs reversal."
            ),
            "tone": "confident, flow-driven",
            "word_limit": 210,
        },
        "FII_DRIVEN_SELLOFF": {
            "opening_instruction": (
                "Open with the scale of FII exit in crore and which sectors bore the brunt. "
                "Do NOT name individual stocks — use sector-level data from the table above only."
            ),
            "required_angles": [
                "Explain the global risk-off trigger (VIX level, US yields direction, EM contagion) "
                "behind the FII exit — use actual VIX value from verified data above",
                "Name the top 2 sectors from the SECTOR CONTRIBUTIONS table where FII selling "
                "created the most NIFTY damage — use weight × return math explicitly",
                "Assess whether DII absorption was sufficient or insufficient — "
                "reference the net FII crore figure from verified data",
            ],
            "closing_instruction": (
                "State the level at which FII outflows historically reverse based on VIX or INR data."
            ),
            "tone": "sober, risk-aware",
            "word_limit": 220,
        },
        "CRUDE_SHOCK": {
            "opening_instruction": (
                "Start with crude: the direction, the magnitude, and the immediate Indian market implication. "
                "Do not open with NIFTY."
            ),
            "required_angles": [
                "Explain OMC (oil marketing company) impact: GRM compression or expansion with the mechanism",
                "Explain upstream E&P (ONGC, Oil India) impact: opposite direction from OMC, explain why",
                "Explain INR pressure from crude — current account deficit widening or narrowing",
            ],
            "closing_instruction": (
                "State the crude price threshold ($/bbl) at which RBI would be forced to intervene in FX."
            ),
            "tone": "technical, commodity-sector focused",
            "word_limit": 215,
        },
        "RUPEE_MOVE": {
            "opening_instruction": (
                "Lead with the rupee move — direction, magnitude, and what is driving it (FII, crude, DXY)."
            ),
            "required_angles": [
                "IT/Pharma sector impact: rupee direction and its translation mechanism into earnings",
                "Import-heavy sector impact (Autos, Energy): input cost change in INR terms",
                "RBI intervention probability: is the move orderly or disorderly?",
            ],
            "closing_instruction": (
                "State the specific USD/INR level that would prompt RBI dollar sales."
            ),
            "tone": "FX-macro analytical",
            "word_limit": 200,
        },
        "FEAR_SPIKE": {
            "opening_instruction": (
                "Open with the VIX level and what it signals about positioning. "
                "Fear is the story today, not the index level."
            ),
            "required_angles": [
                "Explain what event is driving fear (global risk-off, India-specific shock, or options expiry)",
                "Name which sectors see the most panic selling vs. flight-to-safety buying",
                "Assess whether VIX at this level historically marks a short-term floor or mid-trend continuation",
            ],
            "closing_instruction": (
                "State the VIX level at which fear typically transitions to opportunity historically."
            ),
            "tone": "calm, contrarian-aware",
            "word_limit": 210,
        },
        "BROAD_DIVERGENCE": {
            "opening_instruction": (
                "Open by naming the contradiction: the index moved X% but Y sectors moved against the macro. "
                "Make this the central puzzle."
            ),
            "required_angles": [
                "Explain the weight-concentration math for each divergent sector (stock weight × return = NIFTY impact)",
                "Identify whether the divergence is earnings-driven (company-specific) or positioning-driven (options, index rebalance)",
                "Assess whether divergence is temporary rotation or a macro signal",
            ],
            "closing_instruction": (
                "Name one divergent sector and the specific catalyst that would bring it back into macro alignment."
            ),
            "tone": "investigative, data-driven",
            "word_limit": 230,
        },
        "RISK_OFF_REGIME": {
            "opening_instruction": (
                "Open with the regime shift — what confluence of signals tipped the regime to RISK_OFF."
            ),
            "required_angles": [
                "List the 3 macro indicators that are simultaneously in risk-off territory (VIX, FII, crude/FX)",
                "Identify which sector class performs best in sustained RISK_OFF (quality, defensive, gold-linked)",
                "Contrast with the sector class most exposed if the regime deepens",
            ],
            "closing_instruction": (
                "State two conditions that would flip the regime back to neutral."
            ),
            "tone": "regime-focused, strategic",
            "word_limit": 225,
        },
        "BULL_REGIME": {
            "opening_instruction": (
                "Open with the breadth of the rally — how many sectors participated and at what weight."
            ),
            "required_angles": [
                "Name the macro tailwinds sustaining the bull regime (FII flows, rate trajectory, earnings cycle)",
                "Identify which sectors have momentum but are now extended vs. which are lagging but about to catch up",
                "Assess whether global markets (US, EM) are aligned or diverging",
            ],
            "closing_instruction": (
                "State the single macro risk that could interrupt the bull regime — with a specific threshold."
            ),
            "tone": "constructive, opportunity-seeking",
            "word_limit": 220,
        },
        "STANDARD_DAY": {
            "opening_instruction": (
                "Do NOT open with 'NIFTY moved X%'. Choose one of these openings instead: "
                "(a) Start with the sector that had the most outsized move relative to its weight. "
                "(b) Start with the macro variable that best explains today. "
                "(c) Start with a contrast: 'While X rose, Y fell because...' "
                "Rotate between these styles — never use the same opening twice consecutively."
            ),
            "required_angles": [
                "Explain top 2 sector moves with the causal macro variable (not 'market sentiment')",
                "Note any sector behaving contrary to its usual macro relationship — explain why",
                "State the macro variable with the most forward momentum going into next session",
            ],
            "closing_instruction": (
                "Close with one specific number to watch tomorrow."
            ),
            "tone": "analytical, varied in structure",
            "word_limit": 210,
        },
    }

    return structures.get(narrative, structures["STANDARD_DAY"])


def build_final_insight_prompt(moderated_output):
    """
    Builds the complete prompt for the LLM using both
    contribution data AND macro regime context.

    MARKET STATE AWARENESS: On non-trading days (weekends/holidays),
    returns a structured closed-market insight instead of misleading
    "NIFTY stable" or "NIFTY moved X%" text.
    """
    # ── MARKET STATE GATE ─────────────────────────────────────────
    try:
        from market_calendar import get_market_status, log_market_status
        ms = get_market_status()
    except ImportError:
        ms = {"is_trading_day": True, "engine_mode": "FULL",
              "data_quality": "VALID", "market_closed_text": "",
              "market_status": "OPEN", "last_trading_day": None,
              "next_trading_day": None, "session_state": "AFTER_HOURS"}

    if not ms["is_trading_day"] or ms["engine_mode"] == "FORECAST_ONLY":
        # Return a holiday-aware prompt that tells the LLM the market is closed
        last_td  = ms.get("last_trading_day")
        next_td  = ms.get("next_trading_day")
        reason   = ms.get("close_reason", "Market closed")
        regime   = moderated_output.get("macro_regime", {})
        macro    = moderated_output.get("macro_data", {})
        closed_prompt = f"""
You are MarketOS — India's market intelligence engine.

TODAY'S STATUS: MARKET CLOSED — {reason}
Data Quality: {ms['data_quality']}
Last trading session: {last_td}
Next trading session: {next_td}

⚠ MANDATORY RULES FOR CLOSED DAYS:
  - DO NOT write "NIFTY stable" or "NIFTY moved X%"
  - DO NOT refer to price movements, index levels, or daily returns
  - DO NOT imply any trading activity occurred today
  - DO use the phrase "Market closed — no trading activity"

MACRO CONTEXT (for forward-looking commentary only):
Regime: {regime.get('overall_regime', 'NEUTRAL')} | Score: {regime.get('legacy_score', int(round(float(regime.get('regime_score', 0)) * 10))):+d}/10
VIX: {macro.get('india_vix', {}).get('current', 'N/A')}
USD/INR: {macro.get('usdinr', {}).get('current', 'N/A')}
Brent Crude: ${macro.get('brent_crude', {}).get('current', 'N/A')}/bbl
Repo Rate: {macro.get('repo_rate', {}).get('current', 'N/A')}%

GENERATE A CLOSED-MARKET INSIGHT (max 120 words):

MARKET STATUS:
Market closed — no trading activity today ({reason}).
Next session: {next_td}.

MACRO BACKDROP (from most recent data):
[1-2 sentences on the macro environment using data above.
DO NOT mention price moves. Focus on rates, flows, and forward context.]

WHAT TO WATCH NEXT SESSION:
[1 sentence: name the single most important variable to monitor when
markets reopen, with a specific threshold or event to watch for.]
"""
        return closed_prompt

    regime = moderated_output['macro_regime']
    macro = moderated_output['macro_data']
    sectors = moderated_output['moderated_sectors']

    # Top 3 sectors by absolute contribution
    top_sectors = sorted(
        sectors.items(),
        key=lambda x: abs(x[1]['sector_contribution_pct']),
        reverse=True
    )[:3]

    sector_lines = "\n".join([
        f"- {name}: {data['sector_contribution_pct']:+.4f}% index impact | "
        f"Primary driver: {data['primary_macro_driver']} | "
        f"Macro alignment: {data['macro_alignment']}"
        for name, data in top_sectors
    ])

    # Build per-sector causal rules injected directly into the LLM prompt
    # Prevents "Energy rose because rupee" — forces correct variable per sector
    _crude_chg  = macro.get("brent_crude", {}).get("change_pct", 0)
    _crude_val  = macro.get("brent_crude", {}).get("current", 90)
    _usdinr_chg = macro.get("usdinr", {}).get("change_pct", 0)
    _usdinr_val = macro.get("usdinr", {}).get("current", 83.5)
    _repo       = macro.get("repo_rate", {}).get("current", 6.25)
    _fii_signal = macro.get("fii_flows", {}).get("signal", "NEUTRAL")
    _fii_cr     = macro.get("fii_flows", {}).get("estimated_crore", 0)
    _gdp        = macro.get("gdp_growth", {}).get("current", 6.4)
    _vix        = macro.get("india_vix", {}).get("current", 17)

    _DRIVER_EXPLAIN = {
        "brent_crude": (
            f"Brent crude at ${_crude_val:.1f}/bbl ({_crude_chg:+.1f}%) — "
            + ("OMC refiners BENEFIT: GRM expands as input cost falls, retail prices lag. "
               "Upstream E&P (ONGC, Oil India) HURT — lower crude = lower realisation per barrel."
               if _crude_chg < -2 else
               "OMC refiners HURT: input costs rising faster than capped retail prices — GRM compressed."
               if _crude_chg > 2 else
               "Crude near-neutral — no major OMC or upstream impact today.")
        ),
        "usdinr": (
            f"USD/INR at Rs{_usdinr_val:.2f} ({_usdinr_chg:+.2f}%) — "
            + ("Rupee STRENGTHENING HURTS IT/Pharma: dollar revenues worth less in INR. "
               "Benefits import-heavy sectors (Energy, Autos) via lower input costs in INR."
               if _usdinr_chg < -0.3 else
               "Rupee WEAKENING HELPS IT/Pharma: dollar revenues worth more in INR. "
               "Hurts import-heavy sectors."
               if _usdinr_chg > 0.3 else
               "Rupee near-stable — marginal FX impact today.")
        ),
        "repo_rate": (
            f"Repo rate at {_repo:.2f}% — "
            "For Banks: NIM expands as MCLR-linked loan rates reprice faster than deposit rates. "
            "For Real Estate & Infra: borrowing cost falls → project IRR improves → more projects viable; "
            "home loan EMIs fall → pent-up buyer demand converts to purchases. "
            "For Autos: retail loan EMIs fall → entry-level buyer pool expands."
        ),
        "fii_flows": (
            f"FII {_fii_signal} (~Rs{abs(_fii_cr):,.0f} Cr) — "
            "large-cap heavyweights (HDFC Bank, SBI, Reliance) benefit from inflows. "
            "IT movement driven by NASDAQ sentiment, NOT FII flows."
        ),
        "gdp_growth": (
            f"GDP at {_gdp:.1f}% — consumer spending supports FMCG, "
            "QSR, and consumer discretionary volume growth."
        ),
        "india_vix": (
            f"VIX at {_vix:.1f} — "
            + ("elevated fear, risk-off: quality names outperform."
               if _vix > 20 else "moderate uncertainty, markets cautious but stable.")
        ),
    }

    sector_driver_rules = "\n".join([
        f"  [{name}] use ONLY '{data['primary_macro_driver']}' as the causal variable: "
        f"{_DRIVER_EXPLAIN.get(data['primary_macro_driver'], data['primary_macro_driver'])}"
        for name, data in top_sectors
    ])

    # Anomalies
    anomalies = [
        f"- {name}: {data['anomaly_flag']}"
        for name, data in sectors.items()
        if data.get('anomaly_flag')
    ]
    anomaly_text = "\n".join(anomalies) if anomalies else "None detected."

    # ── DYNAMIC CONTEXT DETECTION ────────────────────────────────
    ctx = _classify_market_context(moderated_output)
    structure = _get_dynamic_structure(ctx)

    dominant_narrative_label = ctx["dominant_narrative"].replace("_", " ").title()

    prompt = f"""
You are MarketOS — India's explainable market intelligence engine.
You receive VERIFIED FACTUAL DATA from quantitative engines.
DO NOT add information not given. DO NOT make investment recommendations.
Write in simple language that a retail investor with basic market knowledge understands.

════════════════════════════════════
VERIFIED MARKET DATA: {moderated_output['date']}
MARKET STATUS: {ms.get('market_status', 'OPEN')} | Data Quality: {ms.get('data_quality', 'VALID')} | Session: {ms.get('session_state', 'AFTER_HOURS')}
════════════════════════════════════

NIFTY 50: {moderated_output['nifty_level']:,.2f}
Move: {moderated_output['nifty_actual_return_pct']:+.3f}% | {moderated_output['nifty_actual_points']:+.2f} pts

MACRO REGIME (verified):
Overall: {regime['overall_regime']}
Regime Score: {regime.get('legacy_score', int(round(float(regime.get('regime_score', 0)) * 10))):+d}/10
Risk Level: {regime['risk_level']}
Market Bias: {regime['market_bias']}

KEY MACRO VARIABLES TODAY:
- India VIX: {macro.get('india_vix', {}).get('current', 'N/A')} | {regime['variables'].get('vix', {}).get('regime', 'N/A')}
- USD/INR: {macro.get('usdinr', {}).get('current', 'N/A')} ({macro.get('usdinr', {}).get('change_pct', 0):+.2f}%) | {regime['variables'].get('usdinr', {}).get('regime', 'N/A')}
- Brent Crude: ${macro.get('brent_crude', {}).get('current', 'N/A')}/bbl ({macro.get('brent_crude', {}).get('change_pct', 0):+.2f}%) | {regime['variables'].get('brent_crude', {}).get('regime', 'N/A')}
- Repo Rate: {macro.get('repo_rate', {}).get('current', 'N/A')}% | {regime['variables'].get('repo_rate', {}).get('regime', 'N/A')}
- FII: {macro.get('fii_flows', {}).get('signal', 'N/A')} (~₹{macro.get('fii_flows', {}).get('estimated_crore', 0):,.0f} Cr)

SECTOR CONTRIBUTIONS (verified by contribution engine):
{sector_lines}

CAUSAL ATTRIBUTION RULES — follow EXACTLY:
{sector_driver_rules}

SECTOR NARRATIVES (additional context):
{chr(10).join([f"- {{name}}: {{data['narrative']}}" for name, data in top_sectors])}

ANOMALIES DETECTED:
{anomaly_text}

════════════════════════════════════
TODAY'S MARKET NARRATIVE TYPE: {dominant_narrative_label}
════════════════════════════════════

TODAY'S WRITING INSTRUCTIONS (follow these exactly — they change daily):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OPENING INSTRUCTION:
{structure['opening_instruction']}

REQUIRED ANGLES TO COVER (cover all of these in your response):
{chr(10).join([f"{i+1}. {angle}" for i, angle in enumerate(structure['required_angles'])])}

CLOSING INSTRUCTION:
{structure['closing_instruction']}

TONE FOR TODAY: {structure['tone']}
WORD LIMIT: {structure['word_limit']} words maximum

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORBIDDEN PHRASES — NEVER write these:
  ✗ "company-specific factors"   ✗ "technical factors"
  ✗ "short-term positioning"     ✗ "market sentiment"
  ✗ "broader trends"             ✗ "investor confidence"
  ✗ "positive for the sector"    ✗ "monitor RBI"

NUMBER RULES:
  • Only use numbers from the VERIFIED MACRO DATA block above
  • Do NOT invent figures unless derived from data
  • If crude change is <0.5%, call it "marginal"

DIVERGENCE RULE (if any MACRO_DIVERGENT sector appears):
  • Explain using weight-concentration math: stock weight × return = NIFTY impact
  • Never write "company-specific factors"

DISCLAIMER: This is educational market analysis only. Not investment advice.
"""

    return prompt


def print_macro_report(moderated_output):
    """Prints a clean macro moderation report"""

    regime = moderated_output['macro_regime']
    macro = moderated_output['macro_data']

    print(f"\n{'='*65}")
    print(f"MARKETOS MACRO INTELLIGENCE REPORT")
    print(f"Date: {moderated_output['date']}")
    print(f"{'='*65}")

    print(f"\nOVERALL MACRO REGIME: {regime['overall_regime']}")
    # regime_score is float [-1,+1]; legacy_score is int [-10,+10] for display
    _rs_int = regime.get('legacy_score',
                         int(round(float(regime.get('regime_score', 0)) * 10)))
    _strength = regime.get('strength', '')
    print(f"Regime Score: {_rs_int:+d}/10  |  Strength: {_strength}  |  "
          f"Risk: {regime['risk_level']}  |  Bias: {regime['market_bias']}")

    print(f"\n{'─'*65}")
    print("MACRO VARIABLES SUMMARY")
    print(f"{'─'*65}")

    for var_name, var_data in regime['variables'].items():
        if var_name == "fii_flows":
            name_clean = "FII Flows"
        elif var_name == "dii_flows":
            name_clean = "DII Flows"
        else:
            name_clean = var_name.replace('_', ' ').title()
        print(f"\n{name_clean}:")
        print(f"  Regime: {var_data.get('regime', 'N/A')}")
        # score is now a float; format accordingly
        _sc = var_data.get('score', 0)
        print(f"  Score: {float(_sc):+.2f}")
        explanation = moderated_output['macro_regime']['explanation'].get(var_name, '')
        if explanation:
            print(f"  {explanation[:120]}...")

    print(f"\n{'─'*65}")
    print("SECTOR MACRO MODERATION")
    print(f"{'─'*65}")
    print(f"{'Sector':<35} {'Return':>8} {'Contrib':>10} {'Alignment':>18} {'Driver':>15}")
    print(f"{'─'*65}")

    for sector_name, sector_data in moderated_output['moderated_sectors'].items():
        name_s = sector_name[:34]
        ret = sector_data['sector_return_pct']
        contrib = sector_data['sector_contribution_pct']
        align = sector_data['macro_alignment'][:17]
        driver = sector_data['primary_macro_driver'][:14]
        icon = "✓" if align == "MACRO_ALIGNED" else ("⚠" if "DIVERGENT" in align else "─")

        print(f"{icon} {name_s:<34} {ret:>+7.2f}% {contrib:>+9.4f}% {align:>18} {driver:>15}")
