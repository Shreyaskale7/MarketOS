import os
import re

def fix():
    with open("c:/MarketOS VIP/macro_engine.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Step 1: Add Nifty momentum score calculation right before WEIGHTS
    nifty_momentum_code = """    # ── 1f. NIFTY Momentum Score (NEW) ─────────────────────────────────
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
    }"""
    
    target_weights = """    # ══════════════════════════════════════════════════════════════════
    # STEP 2 — WEIGHTED COMPOSITE SCORE
    # ══════════════════════════════════════════════════════════════════
    WEIGHTS = {
        "vix":   0.30,   # most real-time signal — option market's fear gauge
        "fii":   0.15,   # direct price pressure — FII = marginal buyer/seller
        "dii":   0.10,   # domestic flow support (NEW)
        "fx":    0.15,   # USDINR direction — macro stress indicator
        "crude": 0.15,   # import-bill driver — India-specific sensitivity
        "rate":  0.15,   # RBI stance — structural, changes rarely
    }

    component_scores = {
        "vix":   vix_score,
        "fii":   fii_score,
        "dii":   dii_score,
        "fx":    fx_score,
        "crude": crude_score,
        "rate":  rate_score,
    }"""
    
    content = content.replace(target_weights, nifty_momentum_code)

    # Step 2: Fix debug print labels
    target_labels = """    _regime_labels = {
        "vix": vix_regime, "fii": fii_regime, "dii": dii_regime,
        "fx": fx_regime, "crude": crude_regime, "rate": rate_regime
    }"""
    new_labels = """    _regime_labels = {
        "vix": vix_regime, "nifty": nifty_regime, "fii": fii_regime, "dii": dii_regime,
        "fx": fx_regime, "crude": crude_regime, "rate": rate_regime
    }"""
    content = content.replace(target_labels, new_labels)
    
    target_print = """    print(f"  VIX: {vix_score:+.1f}  FII: {fii_score:+.1f}  DII: {dii_score:+.1f}  FX: {fx_score:+.1f}  Crude: {crude_score:+.1f}  Rate: {rate_score:+.1f}")"""
    new_print = """    print(f"  VIX: {vix_score:+.1f}  NIFTY: {nifty_score:+.1f}  FII: {fii_score:+.1f}  DII: {dii_score:+.1f}  FX: {fx_score:+.1f}  Crude: {crude_score:+.1f}  Rate: {rate_score:+.1f}")"""
    content = content.replace(target_print, new_print)

    # Step 3: Add safety override
    target_safety = """    else:
        overall = "STRONGLY_BEARISH"
        risk    = "VERY_HIGH"
        bias    = "RISK_OFF"

    # ══════════════════════════════════════════════════════════════════
    # STEP 4 — CONFIDENCE LEVEL"""
    
    new_safety = """    else:
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
    # STEP 4 — CONFIDENCE LEVEL"""
    content = content.replace(target_safety, new_safety)

    # Step 4: Save nifty data in regime output
    target_vars = """    # ── Store all variable data ────────────────────────────────────────
    regime['variables']['vix'] = {"""
    
    new_vars = """    # ── Store all variable data ────────────────────────────────────────
    regime['variables']['nifty_momentum'] = {
        "change_pct": nifty_change,
        "regime": nifty_regime, "score": nifty_score,
        "score_int": int(round(nifty_score * 3)),
    }
    regime['variables']['vix'] = {"""
    content = content.replace(target_vars, new_vars)
    
    target_expl = """    regime['explanation']['vix']          = vix_explanation"""
    new_expl = """    regime['explanation']['nifty_momentum'] = nifty_explanation
    regime['explanation']['vix']          = vix_explanation"""
    content = content.replace(target_expl, new_expl)

    with open("c:/MarketOS VIP/macro_engine.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    fix()
