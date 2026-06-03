import os
import re

def fix():
    with open("c:/MarketOS VIP/alpha_engine.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Step 1: Update weights
    target_weights = """WEIGHTS = {
    "momentum":       0.40,
    "mean_reversion": 0.20,
    "vol_breakout":   0.20,
    "macro_align":    0.20,
}"""
    new_weights = """WEIGHTS = {
    "momentum":       0.30,
    "mean_reversion": 0.15,
    "vol_breakout":   0.15,
    "macro_align":    0.20,
    "sentiment":      0.20,
}"""
    content = content.replace(target_weights, new_weights)

    # Step 2: Add sentiment signal function
    target_macro_align = """def _signal_macro_alignment(moderated_output: dict) -> pd.Series:"""
    new_sentiment_signal = """def _signal_sentiment(moderated_output: dict) -> pd.Series:
    \"\"\"Fetches live LLM sentiment per sector and maps to subsectors.\"\"\"
    try:
        from sentiment_engine import get_live_sentiment_all_sectors
        sentiment_data = get_live_sentiment_all_sectors(force_refresh=False)
    except Exception:
        sentiment_data = {}

    sub_scores = {}
    for sector_name, sec_data in MARKET_CLASSIFICATION.items():
        # Score is -1.0 to 1.0, scale it to 0.0 to 100.0 (where 0.0 is neutral 50)
        raw_score = sentiment_data.get(sector_name, {}).get("score", 0.0)
        scaled_score = (raw_score + 1.0) / 2.0 * 100.0
        
        for sub_name in sec_data["subsectors"]:
            sub_scores[sub_name] = scaled_score
    return pd.Series(sub_scores)

def _signal_macro_alignment(moderated_output: dict) -> pd.Series:"""
    content = content.replace(target_macro_align, new_sentiment_signal)

    # Step 3: Compute raw sentiment inside compute_alpha_scores
    target_raw = """    mom_raw = _signal_momentum(price_df)
    rev_raw = _signal_mean_reversion(price_df)
    vol_raw = _signal_volatility_breakout(price_df)
    mac_raw = _signal_macro_alignment(moderated_output)"""
    new_raw = """    mom_raw = _signal_momentum(price_df)
    rev_raw = _signal_mean_reversion(price_df)
    vol_raw = _signal_volatility_breakout(price_df)
    mac_raw = _signal_macro_alignment(moderated_output)
    sen_raw = _signal_sentiment(moderated_output)"""
    content = content.replace(target_raw, new_raw)

    # Step 4: Reindex sen_raw
    target_reindex = """    all_subs = set(mom_raw.index) | set(rev_raw.index) | set(vol_raw.index) | set(mac_raw.index)
    mom_raw  = mom_raw.reindex(all_subs).fillna(0.0)
    rev_raw  = rev_raw.reindex(all_subs).fillna(0.0)
    vol_raw  = vol_raw.reindex(all_subs).fillna(0.0)
    mac_raw  = mac_raw.reindex(all_subs).fillna(65.0)"""
    
    new_reindex = """    all_subs = set(mom_raw.index) | set(rev_raw.index) | set(vol_raw.index) | set(mac_raw.index) | set(sen_raw.index)
    mom_raw  = mom_raw.reindex(all_subs).fillna(0.0)
    rev_raw  = rev_raw.reindex(all_subs).fillna(0.0)
    vol_raw  = vol_raw.reindex(all_subs).fillna(0.0)
    mac_raw  = mac_raw.reindex(all_subs).fillna(65.0)
    sen_raw  = sen_raw.reindex(all_subs).fillna(50.0)"""
    content = content.replace(target_reindex, new_reindex)

    # Step 5: Normalize and compute composite
    target_composite = """    mom_norm = _normalise(mom_raw)
    rev_norm = _normalise(rev_raw)
    vol_norm = _normalise(vol_raw)
    mac_norm = _normalise(mac_raw)

    alpha_df = pd.DataFrame({
        "momentum":       mom_norm,
        "mean_reversion": rev_norm,
        "vol_breakout":   vol_norm,
        "macro_align":    mac_norm,
    }).fillna(0.0)

    alpha_df["alpha_score"] = (
        alpha_df["momentum"]       * WEIGHTS["momentum"] +
        alpha_df["mean_reversion"] * WEIGHTS["mean_reversion"] +
        alpha_df["vol_breakout"]   * WEIGHTS["vol_breakout"] +
        alpha_df["macro_align"]    * WEIGHTS["macro_align"]
    )"""

    new_composite = """    mom_norm = _normalise(mom_raw)
    rev_norm = _normalise(rev_raw)
    vol_norm = _normalise(vol_raw)
    mac_norm = _normalise(mac_raw)
    sen_norm = _normalise(sen_raw)

    alpha_df = pd.DataFrame({
        "momentum":       mom_norm,
        "mean_reversion": rev_norm,
        "vol_breakout":   vol_norm,
        "macro_align":    mac_norm,
        "sentiment":      sen_norm,
    }).fillna(0.0)

    alpha_df["alpha_score"] = (
        alpha_df["momentum"]       * WEIGHTS["momentum"] +
        alpha_df["mean_reversion"] * WEIGHTS["mean_reversion"] +
        alpha_df["vol_breakout"]   * WEIGHTS["vol_breakout"] +
        alpha_df["macro_align"]    * WEIGHTS["macro_align"] +
        alpha_df["sentiment"]      * WEIGHTS["sentiment"]
    )"""
    content = content.replace(target_composite, new_composite)
    
    target_print = """    print("  Rank  Subsector                             Alpha    Mom   MRev    Vol    Mac Status")
    print("  ────────────────────────────────────────────────────────────────────────────────")"""
    new_print = """    print("  Rank  Subsector                             Alpha    Mom   MRev    Vol    Mac    Sen Status")
    print("  ───────────────────────────────────────────────────────────────────────────────────────")"""
    content = content.replace(target_print, new_print)
    
    target_loop = """        print(f"  {r:<4}  {s:<37} {a:.3f} {mo:.3f} {mr:.3f} {vo:.3f} {ma:.3f}  {st}")"""
    new_loop = """        sn = float(row.get('sentiment', 0.0))
        print(f"  {r:<4}  {s:<37} {a:.3f} {mo:.3f} {mr:.3f} {vo:.3f} {ma:.3f} {sn:.3f} {st}")"""
    content = content.replace(target_loop, new_loop)

    with open("c:/MarketOS VIP/alpha_engine.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    fix()
