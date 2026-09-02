# bible_content_d.py
# MarketOS Build Bible v2 — Parts 9, 10, 11, 12.
# Every number in Part 9 was read out of data/marketos.db or produced by backtest_engine.py.

BLOCKS = [

# ═══════════════════════════════════════════════════════════════════
("part", (9, "The measured results & the honest negatives",
          "Every figure here was read out of the shipped database or produced by the backtest engine. "
          "The failures sit next to the wins, because that is what makes the wins believable.")),

("h2", "9.1 What the system is built on"),
("table", ([0.42, 0.20, 0.38], [
    ["Quantity", "Measured", "Source"],
    ["Daily price rows", "306,746", "<font face='Courier'>daily_prices</font>"],
    ["Macro rows", "3,781", "<font face='Courier'>macro_data</font>"],
    ["Date coverage", "2016-04-06 → 2026-08-13", "min/max of <font face='Courier'>daily_prices.date</font>"],
    ["Sectors / subsectors / entries", "7 / 28 / 130 (128 unique tickers)",
     "<font face='Courier'>classification.py</font>"],
    ["Trained model versions", "~140 active (grows daily — GitHub Actions retrains and re-tournaments "
     "every weekday after close)", "<font face='Courier'>model_versions</font>, verified live on the "
     "deployed Postgres"],
    ["Training rows per model (mean)", "2,462 / 2,422 / 2,361 at 1M/3M/6M",
     "<font face='Courier'>model_versions.n_samples</font>"],
    ["Forecast evaluations recorded", "94,500", "<font face='Courier'>prediction_accuracy</font>"],
])),

("h2", "9.2 Walk-forward backtest"),
("p", "Quarterly rebalance (63 trading days, 252-day training window — changed from an earlier monthly "
      "default; see the box below), full Indian cost stack deducted, NIFTY close-to-close benchmark, "
      "weights built only from data strictly before each rebalance date. These are live, freshly-queried "
      "numbers from the deployed cache, not a point-in-time snapshot."),
("table", ([0.20, 0.11, 0.15, 0.15, 0.13, 0.10, 0.10, 0.10], [
    ["Window", "Periods", "Port. p.a.", "NIFTY p.a.", "Net alpha", "Sharpe", "IR", "MaxDD"],
    ["5yr", "15", "+19.11%", "+13.58%", "<b>+5.53%</b>", "0.864", "0.601", "−5.83%"],
    ["10yr", "35", "+11.89%", "+11.87%", "<b>+0.02%</b>", "0.375", "0.021", "−21.61%"],
])),
("p", "Win rate 80% at 5yr, 63% at 10yr. Cost drag ~1.6–1.8%/yr at both windows — quarterly rebalancing "
      "roughly halves the friction of the monthly default it replaced (measured at 3.95%/yr, see below)."),
("box", ("Why quarterly, not monthly — a parameter sweep, not a preference",
         "The system originally rebalanced monthly (30 trading days, 126-day training window). A full "
         "sweep across {30, 63, 126}-day rebalancing × {126, 252}-day training windows showed monthly was "
         "the <i>worst</i> of six configurations measured: it traded 20 of 20 rebalances (the turnover "
         "filter never once skipped one), costing 3.95%/yr in friction for a −9.07% 3-year alpha. "
         "Quarterly/252d cut friction to ~1.7%/yr. Momentum is also documented in the literature to "
         "operate on 3–12 month horizons, and a 252-day Sharpe estimate is materially less noisy than a "
         "126-day one — the sweep result and the prior agree.")),
("warn", ("Read the two windows honestly — the edge is real but unstable, and the 10-year number is the "
          "one to lead with",
          "Two identical reruns of the 10-year window measured <b>+3.00%</b> and <b>+4.59%</b> "
          "respectively for net alpha — a ~1.5-point swing on an identical configuration, purely from "
          "which rebalance dates a data refresh happened to land on. And an 8-year window measured "
          "<b>−2.33%</b> — negative. A result that changes sign with the start date, on the same strategy, "
          "is the signature of a weak or unstable edge, not a robust one. The 3-year window (n=7) was "
          "removed from the public dashboard entirely for exactly this reason — seven observations cannot "
          "support a conclusion either way. <b>The honest headline is the 10-year figure</b> — largest "
          "sample, essentially flat (+0.02%, IR 0.021) — not the flattering 5-year one. Standard error on "
          "a Sharpe of 0.864 at n=15 is ≈1/√15 ≈ 0.26; say “about 0.9, ±0.25”, not “0.864”.")),
("warn", ("The most important caveat in this document",
          "<b>The backtest does not test the ML or alpha engines.</b> "
          "<font face='Courier'>_backtest_weights()</font> selects by trailing Sharpe and inverse-vol "
          "sizing — it never calls <font face='Courier'>ml_forecast_engine</font> or "
          "<font face='Courier'>alpha_engine</font>. The alpha above is evidence for the <b>portfolio "
          "construction methodology</b>, not for the ML forecasts. The ML evidence is entirely separate "
          "— see the important caveat at the top of §9.3 before quoting it. Conflating the two would be "
          "the single most misleading claim available here. Closing this gap is still roadmap item one.")),

("h2", "9.3 Model quality — the pre-fix figures, and why they're retired"),
("warn", ("Read this before quoting any number in §9.3 or §9.4",
          "The tables below were measured on training targets that were later found to be corrupted by a "
          "unit-mismatch bug: NIFTY's daily return was stored as a percent (e.g. −8.30) while subsector "
          "returns were stored as a fraction (e.g. 0.012), and the compounding formula assumed both were "
          "fractions. Any training window touching a large single-day NIFTY move compounded a negative "
          "base across the window, producing target values in the tens of millions of percent in the "
          "worst case. The bug is fixed (both sides now compound in the same units) and every model has "
          "been retrained against the corrected targets — but the IC and optimism-bias figures below "
          "predate that fix and no longer describe the live models. They are kept here, clearly labelled, "
          "because they are still the right shape of evidence to know how to produce and how to read — "
          "just not the right numbers. Fresh figures require forecasts to mature (30+ days per horizon) "
          "before <font face='Courier'>feedback_evaluator.evaluate_forecast_accuracy()</font> can score "
          "them; as of this writing, no post-fix forecast has yet reached that age.")),
("table", ([0.13, 0.15, 0.15, 0.22, 0.35], [
    ["Horizon", "Mean IC", "Median IC", "Share IC&gt;0", "Range"],
    ["1M", "+0.089", "+0.101", "83% (29/35)", "−0.178 → +0.244"],
    ["3M", "+0.136", "+0.146", "86% (30/35)", "−0.383 → +0.427"],
    ["6M", "+0.170", "+0.214", "83% (29/35)", "−0.305 → +0.441"],
])),
("box", ("What an IC of 0.14 would mean, if reproduced post-fix",
         "Published equity factor research reports single-stock ICs of 0.02–0.06; sector aggregation "
         "should score higher because idiosyncratic noise is averaged out. IC <b>rising monotonically</b> "
         "with horizon (0.089→0.170) was the informative pattern in the pre-fix run — consistent with a "
         "genuinely macro-driven signal, since macro effects accumulate over quarters, not days. Whether "
         "this pattern survives the retrain on corrected targets is precisely the open question — it is "
         "the first re-measurement to run once enough post-fix forecasts have matured.")),
("p", "Pre-fix, Ridge won <b>41 of 175</b> model slots outright — positive evidence against overfitting at "
      "the time; the model tournament's mechanism (walk-forward CV, IC-scored) is unchanged by the fix, so "
      "there is no reason to expect this general shape to disappear, only for the specific counts to move."),

("h2", "9.4 The forecast optimism bias — also pre-fix, also pending re-measurement"),
("table", ([0.13, 0.19, 0.19, 0.15, 0.19, 0.15], [
    ["Horizon", "Mean predicted", "Mean realised", "Ratio", "Direction ✓", "MAE"],
    ["1M", "+8.49%", "+3.24%", "2.6×", "62.0%", "5.25pt"],
    ["3M", "+16.18%", "+6.37%", "2.5×", "65.4%", "9.81pt"],
    ["6M", "+24.06%", "+9.84%", "2.4×", "70.1%", "14.21pt"],
])),
("p", "A stable ~2.5× overprediction across three independent horizons was a calibration problem with an "
      "identifiable cause (the train/serve feature skew, §3.2) — plausible independent of the unit-"
      "mismatch bug, since the skew and the mismatch are different code paths (inference-time feature "
      "approximation vs. training-time target computation). The skew has not been fixed; whether the "
      "2.5× ratio survives the target fix at all, changes magnitude, or is joined by a second effect from "
      "the fix itself, is unknown until the same measurement is rerun on matured post-fix forecasts. "
      "Directional accuracy in the table above is inflated by the base rate (both mean prediction and "
      "mean outcome were positive); all 94,500 rows were evaluated on one date — a bulk backfill, not a "
      "rolling out-of-sample test."),

("h2", "9.5 Defects in the shipped code"),
("p", "Six of the eleven originally-documented defects are still open, unchanged. Two are now fixed "
      "(marked below). Two more, more severe than anything in the original list, were found during "
      "deployment and are fixed too — full write-ups in the change log's §2.1 and §2.4."),
("table", ([0.28, 0.44, 0.28], [
    ["Defect", "What it does", "Severity"],
    ["<b>NIFTY %/fraction unit mismatch in ML targets</b> — found post-deployment",
     "daily_prices.daily_return is a fraction, macro_data.nifty_return is a percent; compounding assumed "
     "both were fractions. A training window touching a large NIFTY move produced targets in the tens of "
     "millions of percent.", "<b>Fixed</b> — was Critical, corrupted every model's training targets"],
    ["<b>Backtest regime snapshot missing the nifty key</b> — found post-deployment",
     "classify_macro_regime() defaulted to NEUTRAL on every historical rebalance for the snapshot's "
     "entire history, making the STRONGLY_BEARISH hedge rule unreachable dead code in every backtest ever "
     "run.", "<b>Fixed</b> — was High, silently disabled a documented risk-management rule"],
    ["NIFTY term omitted from regime composite", "Declared at weight 0.25, computed, never summed. "
     "Effective weights total 0.75.", "<b>High</b> — every regime label — still open"],
    ["Docstring/code disagreement in classifier", "Documented weights and thresholds differ from the "
     "implemented ones.", "Medium — misleads readers — still open"],
    ["<font face='Courier'>directional_accuracy</font> hardcoded to 0.5", "Every forecast reports a "
     "literal, not the measured value one variable away.", "Medium — display bug — still open"],
    ["<font face='Courier'>r_squared</font> column holds a rank IC", "Nothing computes an R² anywhere.",
     "Low in substance, high risk of misquoting — still open"],
    ["In-sample metrics stored as if evaluated", "Chosen model refit and scored on all data; drives "
     "user-facing confidence.", "Medium — inflates confidence — still open"],
    ["Train/serve feature skew", "Rolling/lagged features approximated as x×0.85/0.9/0.6 at inference.",
     "<b>High</b> — prime suspect for the 2.5× bias in §9.4 — still open"],
    ["Wrong ticker for Tata Motors", "M&amp;M.NS double-listed; Passenger Vehicles' history was wrong.",
     "<b>Fixed</b> — was High, corrupted a whole subsector"],
    ["ETF map mismatched to taxonomy", "4/7 sectors silently fell back to NIFTYBEES.NS.",
     "<b>Fixed</b> — was Medium, paper-trading layer only"],
    ["MILD_BEARISH stricter than BEARISH", "0.48 vs 0.45 — non-monotonic in severity.",
     "Low — likely a transposition — still open"],
    ["Diversification floor not reached", "MIN_SECTORS=5, shipped portfolio holds 5 subsectors / 2 "
     "sectors.", "Medium — tuning gap — still open"],
    ["Risk-free rate inconsistent", "0.065 in two places, 0.07 in the MVO objective.", "Low — 50bp, "
     "barely moves the optimiser — still open"],
])),
("box", ("The pattern across every real bug found this deployment",
         "Not one of the four fixed defects above raised an exception. Each produced a plausible-looking, "
         "wrong number: a subsector's return history built from the wrong company, a backtest hedge rule "
         "that silently never fired, a training target with the wrong units. The only tool that ever "
         "caught any of them was measuring an output and asking whether the number made sense — never a "
         "stack trace. This is the strongest argument in the whole document for the missing test suite "
         "(§9.5's structural limitations, and Tier-1 of the roadmap): every one of these bugs is exactly "
         "the shape an assertion catches and a human staring at logs does not.")),
("h3", "Structural and methodological limitations"),
("bul", [
    "The backtest does not exercise the ML or alpha engines (§9.2).",
    "FII/DII are synthetic and derived from the NIFTY return — a quarter of the regime composite is a "
    "re-labelled index return.",
    "Repo, GDP, GST, CPI, IIP are constants; <font face='Courier'>rate_momentum</font> is identically "
    "zero on every row.",
    "No purge/embargo in cross-validation — reported ICs are mildly optimistic.",
    "Sector weights sum to 0.95, not 1.00.",
    "Window-unstable — the 10-year backtest is essentially flat (+0.02% alpha) while the 5-year window "
    "shows +5.53%, an 8-year window shows −2.33%, and two identical reruns of the 10-year window differ "
    "by ~1.5 points. The edge does not survive being measured a second way.",
    "The ML forecast metrics in §9.3–9.4 are pre-fix and formally invalid post-retrain; no post-fix "
    "figures exist yet because forecasts need 30+ days to mature before they can be scored.",
    "Sentiment has never been ablated despite carrying 20% of the alpha weight.",
    "No test suite — at least four defects above would each have been caught by one assertion.",
]),
("h3", "Security posture"),
("p", "Fixed during deployment: password hashing is now bcrypt (cost 12, random salt) with a transparent "
      "one-time migration for existing SHA-256 hashes, and <font face='Courier'>JWT_SECRET</font> now "
      "refuses to boot in production if unset rather than falling back to a hardcoded default. Still "
      "open: wildcard CORS on every route. Detailed with the fixes made in the change log's §5.2."),
("h3", "The regime distribution"),
("table", ([0.28, 0.18, 0.20, 0.34], [
    ["Label", "Count", "Share", "Target"],
    ["BULLISH", "27", "50.0%", "~32%"],
    ["MILDLY_BULLISH", "3", "5.6%", "—"],
    ["NEUTRAL", "19", "35.2%", "~36%"],
    ["BEARISH", "5", "9.3%", "~32%"],
])),
("p", "The RATE_HOLD fix worked partially — NEUTRAL landed exactly on target — but bullish still runs at "
      "56% combined against a 32% target. Two identifiable causes: the missing NIFTY term compresses "
      "scores upward against asymmetric thresholds (+0.10 vs −0.20), and the sample period happened to be "
      "mostly not a bear market. Disentangling them is a one-afternoon job (Tier-1 roadmap)."),

("h2", "9.6 What actually holds up"),
("bul", [
    "Alpha that survives a fully itemised, size-dependent Indian cost stack — not an invented flat rate — "
    "on the largest available sample (10 years, 35 independent rebalances), even though that sample's "
    "headline number is a humbling +0.02%, not a flattering one.",
    "The portfolio-construction methodology, hedging rules, and cost model are now demonstrably wired "
    "correctly end-to-end — the regime-hedge dead-code bug (§9.5) meant this was not true before.",
    "Four real, silent correctness bugs found this deployment were all found the same principled way — "
    "measuring an output and noticing it didn't make sense — never by a crash. That is a repeatable "
    "method, not luck.",
    "Attribution is exact and hand-verifiable — the one layer proved rather than measured.",
    "One pipeline clock, one NIFTY definition, a data-integrity circuit breaker, anchor-keyed caching, "
    "per-stage failure isolation, a market-state machine that degrades rather than fabricates.",
    "The failure modes are known and written down — the difference between a project and a demo is "
    "whether the author can tell you where it breaks. That list grew this deployment, and every new entry "
    "is disclosed here rather than quietly fixed and forgotten.",
]),
("warn", ("What does NOT yet hold up",
          "The ML forecast layer's quality claims (§9.3–9.4) are unverified post-fix — the honest current "
          "position is “the mechanism is sound, the pre-fix numbers looked good, and the numbers that "
          "would prove it post-fix don't exist yet.” Overstating this in an interview is the single "
          "easiest way to lose credibility on this project; the correct answer is the one written down "
          "here.")),

# ═══════════════════════════════════════════════════════════════════
("part", (10, "Extending it: the roadmap",
          "Ordered by measured leverage. Every item names the number it is trying to move.")),

("h2", "10.1 Tier 1 — before anything else"),
("num", [
    "<b>Backtest the actual system.</b> Route the walk-forward loop through ML forecast → alpha score → "
    "<font face='Courier'>build_portfolio()</font> → <font face='Courier'>apply_risk_rules()</font>, "
    "retraining at each rebalance on data available at that date. <i>Target: an alpha number "
    "attributable to the ML engine, comparable against the 7.35% heuristic baseline.</i>",
    "<b>Fix the NIFTY term</b>, one line, and re-derive every regime label across all 3,781 macro rows. "
    "<i>Target: bullish share from 56% toward 32%.</i>",
    "<b>Fix the train/serve skew</b> — compute inference features from <font face='Courier'>MacroData</font> "
    "the way training does. <i>Target: the 2.5× optimism ratio toward 1.0.</i>",
    "<b>Re-measure §9.3–9.4 post-fix.</b> The NIFTY unit-mismatch fix invalidated every IC and "
    "optimism-bias figure in this document; none have been replaced yet because forecasts need 30+ days "
    "to mature. <i>Target: a defensible, current answer to “what does the ML actually contribute.”</i>",
    "<b>De-duplicate the remaining two tickers</b> (MPHASIS.NS, EICHERMOT.NS) — the Tata Motors instance "
    "of this exact bug class is already fixed; these two are next.",
    "<b>Write the test suite</b>, starting with the assertions that would have caught the four fixed "
    "defects in §9.5 — every one of them was a plausible-looking wrong number, not a crash, which is "
    "exactly what a unit test on a known-good fixture catches and eyeballing output does not.",
]),
("h2", "10.2 Tier 2 — measurable improvements"),
("bul", [
    "Real FII/DII data from NSDL/SEBI — removes the regime-score circularity.",
    "Real macro time series (RBI, MOSPI, GST Council) — five columns stop being constants.",
    "Purge and embargo in cross-validation.",
    "Calibrated shrinkage — derive the factor from <font face='Courier'>prediction_accuracy</font> "
    "instead of a flat 0.65.",
    "Ablate every alpha component — right now five weights are asserted, none justified by a measurement.",
    "Rolling forward evaluation, replacing the single-date bulk backfill.",
]),
("h2", "10.3 Tier 3 — capability"),
("bul", [
    "Black-Litterman in place of raw MVO.",
    "Ledoit-Wolf shrinkage on the covariance matrix.",
    "Regime-conditional models rather than regime-as-a-feature.",
    "Bootstrap confidence intervals on the alpha, and a multiple-testing correction for strategy variants "
    "tried.",
    "Explicit CORS origins (currently wildcard) and cron/systemd-grade scheduling beyond the current "
    "GitHub Actions cron.",
]),
("p", "Three Tier-3 items from the original roadmap are already done: bcrypt password hashing, a "
      "mandatory JWT secret in production, and PostgreSQL — all shipped during deployment, detailed in "
      "the change log's §5.2. A fourth, consolidating the dashboard and the React app, resolved itself: "
      "the React app was never wired to anything and was deleted rather than consolidated."),

# ═══════════════════════════════════════════════════════════════════
("part", (11, "Defending the project",
          "Questions a sharp interviewer will ask, answerable from a number in Part 9.")),

("h2", "“Does it actually make money?”"),
("p", "Depends which honest window you quote, and I'll give you both before you have to ask. Over the "
      "largest sample I have — 10 years, 35 quarterly rebalances — it's essentially flat: +0.02% net "
      "alpha, IR 0.021, after a fully itemised Indian cost stack. Over 5 years it looks much better: "
      "+5.53% alpha, Sharpe 0.86, IR 0.60. I lead with the 10-year number, not the 5-year one, because a "
      "result that flips from strong to flat depending on the window — and that shifts ~1.5 points between "
      "two identical reruns of the same 10-year window — is the signature of a weak or unstable edge, and "
      "I'd rather you hear that from me than discover it yourself. What I can say with more confidence: "
      "the portfolio-construction methodology, the hedging rule, and the cost model are now wired "
      "correctly end-to-end, which was not true until I found and fixed a bug where the historical regime "
      "classifier defaulted to NEUTRAL for every rebalance ever backtested — meaning the bear-market hedge "
      "had never once actually fired in any backtest before this fix."),

("h2", "“What does the ML actually contribute?”"),
("p", "Honestly — I can't give you a current number, and I want to explain why rather than dodge it. The "
      "figures I had (mean IC +0.089/+0.136/+0.170 across 1M/3M/6M, 83–86% of models positive) were "
      "measured before I found that NIFTY's return was stored in the wrong units relative to every "
      "subsector's return in the same compounding formula — a bug that corrupted every model's training "
      "target, in the worst cases into targets in the tens of millions of percent. I fixed the unit "
      "mismatch and retrained every model, but a forecast has to mature 30+ days before it can be scored "
      "against reality, so I don't have post-fix numbers yet — only the mechanism, which is unchanged and "
      "sound. The honest answer is “the ML layer produces a positive, monotonically-increasing "
      "cross-validated signal pre-fix; whether that holds post-fix is the first thing I'll measure once "
      "enough time has passed,” not a number I don't actually have."),

("h2", "“An IC of 0.14 is basically nothing.”"),
("p", "In this domain it isn't. Published single-stock factor ICs run 0.02–0.06; sector aggregation "
      "should and does score higher. The number to be suspicious of is 0.6, which here would mean a leak. "
      "This is a weak signal, correctly measured, that needs disciplined position sizing — which is what "
      "most real quantitative alpha looks like."),

("h2", "“Why relative return, not absolute?”"),
("p", "An absolute prediction is dominated by market direction, which any index fund delivers for five "
      "basis points. Training on sector-return-minus-NIFTY over the identical window cancels the market's "
      "move exactly and forces the model to learn relative behaviour. Side effect: the target is roughly "
      "zero-mean, so directional accuracy sits near 50% and rank IC is the headline — and that's the "
      "honest description of what I built."),

("h2", "“Where is the look-ahead bias?”"),
("p", "I'll point at the lines: <font face='Courier'>sector_df.index &lt; as_of_date</font> in the "
      "backtest; the scaler fitted inside the CV fold, not on the full set; the stop-loss exiting on "
      "<font face='Courier'>t+1</font>, not <font face='Courier'>t</font>. What I have not fixed: no "
      "purge/embargo, so training rows within one horizon of the split boundary have overlapping targets "
      "— my ICs are therefore mildly optimistic, and I know roughly which direction they'd move if fixed."),

("h2", "“What's the weakest part?”"),
("p", "The macro data. Five series are constants typed into code, so <font face='Courier'>rate_momentum</font> "
      "is identically zero on every row. FII/DII are synthesised from the NIFTY return, so a quarter of "
      "my regime composite is a re-labelled index return. Both documented, both Tier-2 roadmap items, "
      "both exist because I set a zero-paid-data constraint and those are the two places it actually bit."),

("h2", "“Show me a bug you found by measurement, not a crash.”"),
("p", "RATE_HOLD scored +1 in the regime classifier. The RBI holds rates on essentially every trading "
      "day, so the composite carried a permanent bullish term and the system printed BULLISH ~75% of the "
      "time. Nothing crashed; I found it by plotting the label distribution. General lesson — a constant "
      "signal carries no information, and scoring it positive is a bug, not conservatism — which is the "
      "same check that later found <font face='Courier'>rate_momentum</font> was identically zero."),

("h2", "“You have a bug list in your own documentation. Why?”"),
("p", "Because the alternative is that you find them first. A defect list is cheap insurance, and it "
      "tells you what I'd fix first: at least four of them would have been caught by one assertion each, "
      "which is why the test suite is Tier 1, not Tier 3."),

("h2", "“Why sectors, not stocks?”"),
("p", "Aggregation is a free noise filter — seven banks averaged are driven by rate policy, which macro "
      "features can predict; one company's month is dominated by a CEO exit. It matches the causal "
      "mechanism, maps to liquid ETFs, and stays research rather than SEBI-registrable advice. Real cost: "
      "it can never capture a single-stock opportunity."),

("h2", "“What would you do first with another month?”"),
("p", "Two things, in order. First, re-measure §9.3–9.4 once enough post-fix forecasts have matured — I "
      "changed the ground truth the ML trains on and haven't yet closed the loop on whether it helped. "
      "Second, backtest the actual system — rewrite the walk-forward loop to call the real forecast → "
      "alpha → portfolio → risk path and compare against the current 10-year, +0.02%-alpha heuristic "
      "baseline. If it beats it, I have a system. If not, I've learned something more valuable than a "
      "better number, and I'll publish that too."),

("h2", "“Tell me about a bug you found that never threw an exception.”"),
("p", "Four of them, from one deployment. A subsector's ticker was wrong (M&amp;M.NS instead of "
      "TATAMOTORS.NS) — the wrong company's history, silently, forever, because a wrong ticker string "
      "still returns a real, plausible price series. A backtest's regime snapshot was missing one "
      "dictionary key, so the classifier fell back to NEUTRAL on every single historical rebalance, "
      "meaning the bear-market hedge had never actually fired in the entire history of the backtest — "
      "again, no error, since a missing-key fallback is by definition silent. A unit mismatch between two "
      "return columns corrupted every ML training target, and I only found it because I looked directly "
      "at the mean and standard deviation of what the model was being trained to predict and asked "
      "whether those numbers were physically possible. None of these are exotic bugs — they're all the "
      "same shape: a value that's wrong but not impossible, produced by code with no assertion checking "
      "whether its own output made sense. That pattern, more than any individual fix, is what convinced "
      "me the test suite is genuinely Tier 1, not aspirational cleanup."),

# ═══════════════════════════════════════════════════════════════════
("part", (12, "Appendix",
          "Repository layout, commands, troubleshooting, glossary.")),

("h2", "12.1 Repository layout"),
("p", "Reorganised in a deployment-cleanup pass: an accidentally-vendored PyJWT copy and an unused React "
      "scaffold were deleted outright (change log §5's finding), and the PDF-generation tooling — "
      "including this document's own source — was moved out of the application root into "
      "<font face='Courier'>docs/bible/</font>, since it is real tooling but not application code."),
("code", """marketos/
  database.py, classification.py, pipeline_utils.py, market_calendar.py   FOUNDATION
  data_loader.py, contribution_engine.py, macro_engine.py, sentiment_engine.py   INGEST/ATTRIBUTE
  alpha_engine.py, ml_forecast_engine.py, model_trainer.py, forward_engine.py    SIGNALS/FORECAST
  portfolio_engine.py, risk_engine.py, risk_profiler.py, execution_engine.py     PORTFOLIO/RISK
  backtest_engine.py, performance_engine.py, feedback_evaluator.py              MEASUREMENT
  main.py, marketos_api.py, marketos_dashboard.html                            ORCHESTRATE/SERVE
  populate_backtest_cache.py                                                   OFFLINE PRECOMPUTE
  docs/bible/  (bible_content_*.py, build_bible.py, build_changelog.py, ...)    DOCUMENTATION TOOLING
  .github/workflows/daily-pipeline.yml                                        AUTOMATION (post-close cron)
  data/marketos.db, data/models/ml_horizon/, outputs/                          STATE"""),

("h2", "12.2 Commands"),
("table", ([0.42, 0.58], [
    ["Command", "What it does"],
    ["<font face='Courier'>python main.py --setup</font>", "First-time setup: 10yr data + train every "
     "model. 30–90 min."],
    ["<font face='Courier'>python main.py --daily</font>", "One full pipeline run — this is also what "
     "runs unattended on GitHub Actions every weekday after the 15:30 IST NSE close."],
    ["<font face='Courier'>python main.py --train-ml [years]</font>", "Retrain 1M/3M/6M/12M models."],
    ["<font face='Courier'>python main.py --backtest [years]</font>", "Walk-forward backtest."],
    ["<font face='Courier'>python populate_backtest_cache.py</font>", "Pre-compute the 5yr/10yr backtest "
     "windows out-of-band and populate the cache — the live API serves cache-only, since computing one "
     "in-request was what OOM'd the free-tier instance."],
    ["<font face='Courier'>python ml_forecast_engine.py diagnose</font>", "Row counts, date ranges, "
     "per-subsector coverage."],
    ["<font face='Courier'>python marketos_api.py</font>", "Serve API + dashboard locally on :5001; in "
     "production this runs under gunicorn per <font face='Courier'>render.yaml</font>."],
    ["<font face='Courier'>python docs/bible/build_bible.py</font>", "Regenerate this document."],
    ["<font face='Courier'>python docs/bible/build_changelog.py</font>", "Regenerate the companion change "
     "log documenting everything found and fixed after this bible was first written."],
])),

("h2", "12.3 Troubleshooting"),
("table", ([0.34, 0.66], [
    ["Symptom", "Cause and fix"],
    ["Training reports 0 rows", "<font face='Courier'>daily_prices</font> empty or "
     "<font face='Courier'>daily_return</font> NULL. Run <font face='Courier'>diagnose</font>, then "
     "<font face='Courier'>--setup</font>."],
    ["Pipeline halts on “NIFTY anomaly”", "±5% circuit breaker fired. Verify against a second source "
     "before overriding — never remove the guard."],
    ["NIFTY return prints 0.00%", "&lt;2 valid closes or duplicate closes (stale intraday). Re-run after "
     "15:30 IST."],
    ["Portfolio returns <font face='Courier'>SKIPPED_MARKET_CLOSED</font>", "Correct on a weekend/holiday "
     "— prior weights preserved."],
    ["Sentiment scores all 0.0", "Missing key or rate-limited; degrades to neutral after 2 retries. "
     "Check <font face='Courier'>data/sentiment_cache.json</font>."],
    ["Every 6M forecast identical", "Confirm <font face='Courier'>soft_cap()</font> is in the path, not "
     "a hard clip."],
    ["Backtest metrics change daily", "Cache key must use the earliest trading day, not today's date."],
    ["MVO falls back to Risk Parity", "Covariance matrix incomplete — usually a subsector missing 252 "
     "days of price history. Legitimate, not an error; check coverage."],
    ["Predictions all 0.0", "Feature-order mismatch — build the vector from "
     "<font face='Courier'>payload[\"features\"]</font>, not a hardcoded list."],
])),

("h2", "12.4 The full database schema"),
("p", "Twelve tables. The nine analytical ones are read-heavy and denormalised on purpose — "
      "<font face='Courier'>daily_prices</font> repeats <font face='Courier'>sector</font> and "
      "<font face='Courier'>subsector</font> on every row rather than joining out to "
      "<font face='Courier'>classification.py</font>, which removes a join from the hottest query path "
      "at the cost of redundant storage that is cheap at this row count. The three multi-tenancy tables "
      "back the user-facing risk profile and paper-portfolio features."),
("h3", "daily_prices — 306,746 rows"),
("code", """id             PK
date           Date, indexed              ticker         String(30), indexed
company_name   String(100)                sector         String(80), indexed
subsector      String(80), indexed        open/high/low/close_price  Float
volume         Float                      daily_return   Float
nifty_weight   Float"""),
("h3", "macro_data — 3,781 rows, one per calendar day"),
("code", """id             PK
date           Date, indexed, UNIQUE       repo_rate      Float, default 6.5
usdinr         Float                       brent_crude    Float
india_vix      Float                       fii_net_crore  Float
dii_net_crore  Float                       cpi_yoy        Float
gdp_growth     Float                       gst_collections Float
iip_growth     Float                       nifty_close    Float
sensex_close   Float                       nifty_return   Float
nasdaq_close   Float                       sp500_close    Float
gold_close     Float"""),
("h3", "model_versions — the training audit trail (~140 rows active as of this writing; grows daily via "
       "the automated GitHub Actions retrain)"),
("code", """id               PK
version          String(60), UNIQUE          trained_date   Date
training_start   Date                        training_end   Date
subsector        String(80)                  r_squared      Float  (actually holds Spearman IC, §3.4)
mae              Float                       directional_acc Float  (in-sample, §3.5)
feature_weights  Text (JSON, top-20)         feature_names  Text (JSON, ordered — inference depends on this)
n_samples        Integer                     is_active      Boolean
notes            Text  ("ensemble_xgb_lgb_rf | 10yr | ml_horizon")"""),
("h3", "Everything else, at a glance"),
("table", ([0.24, 0.15, 0.61], [
    ["Table", "Rows", "Columns worth knowing"],
    ["<font face='Courier'>sector_performance</font>", "1,008",
     "One row per (date, sector, subsector): return/contribution pairs at both levels, "
     "<font face='Courier'>top_company</font>, <font face='Courier'>primary_macro_driver</font>, "
     "<font face='Courier'>macro_alignment</font>, <font face='Courier'>regime_label</font> — the daily "
     "attribution output, persisted."],
    ["<font face='Courier'>daily_insights</font>", "54",
     "<font face='Courier'>what_text</font> / <font face='Courier'>why_text</font> / "
     "<font face='Courier'>implication</font> stored separately (not just the concatenated narrative), "
     "plus <font face='Courier'>regime_label</font>, <font face='Courier'>regime_score</font> "
     "(integer, legacy scale), <font face='Courier'>nifty_return</font>, "
     "<font face='Courier'>model_version</font> — so a stored insight can be traced back to exactly the "
     "regime and model that generated it."],
    ["<font face='Courier'>forward_forecasts</font>", "112",
     "<font face='Courier'>forecast_horizon</font>, <font face='Courier'>target_date</font>, "
     "base/bull/bear case returns, <font face='Courier'>confidence_score</font>, "
     "<font face='Courier'>opportunity_score</font>, <font face='Courier'>primary_catalyst</font>, "
     "<font face='Courier'>risk_factor</font> — one row per (subsector, horizon, generation date)."],
    ["<font face='Courier'>sector_growth_analytics</font>", "1,008",
     "Per (subsector, period ∈ {1M…10Y}): total/annualised return, volatility, Sharpe, max drawdown, "
     "best/worst month, % positive months, beta and correlation to NIFTY. Produced by "
     "<font face='Courier'>forward_engine.compute_sector_growth_analytics()</font> (§8.13)."],
    ["<font face='Courier'>prediction_accuracy</font>", "94,500",
     "<font face='Courier'>forecast_id</font> (FK), predicted vs actual return, "
     "<font face='Courier'>direction_correct</font>, <font face='Courier'>error_pct</font>, "
     "<font face='Courier'>evaluated_date</font> — written by "
     "<font face='Courier'>feedback_evaluator.py</font> (§8.13), analysed in §9.4."],
    ["<font face='Courier'>backtest_cache</font>", "4",
     "<font face='Courier'>cache_key</font> (UNIQUE, e.g. <font face='Courier'>backtest_3yr_2016-04-06</font>), "
     "<font face='Courier'>anchor_date</font>, three JSON blobs — "
     "<font face='Courier'>metrics_json</font>, <font face='Courier'>equity_curve_json</font>, "
     "<font face='Courier'>period_returns_json</font> — plus "
     "<font face='Courier'>consistency_warnings_json</font>. The anchor-keyed cache from §5.10."],
    ["<font face='Courier'>users</font>", "4",
     "<font face='Courier'>uuid</font>, <font face='Courier'>email</font> (unique), "
     "<font face='Courier'>password_hash</font> — unsalted SHA-256, flagged in §5.12."],
    ["<font face='Courier'>user_risk_profiles</font>", "3",
     "<font face='Courier'>user_id</font> (FK), the four questionnaire inputs, "
     "<font face='Courier'>risk_score</font> (1–100), <font face='Courier'>risk_label</font> — from "
     "<font face='Courier'>risk_profiler.py</font> (§5.9)."],
    ["<font face='Courier'>user_portfolios</font>", "646",
     "<font face='Courier'>user_id</font> (FK), <font face='Courier'>horizon</font>, "
     "<font face='Courier'>risk_label</font>, <font face='Courier'>portfolio_json</font> (full "
     "allocation), <font face='Courier'>execution_status</font> ∈ {PENDING, EXECUTED, PAPER_TRADE}."],
])),

("h2", "12.5 The complete API surface"),
("p", "Every route in <font face='Courier'>marketos_api.py</font>, in source order. "
      "<font face='Courier'>@require_auth</font> means a valid <font face='Courier'>Bearer</font> JWT is "
      "mandatory; everything else is open, gated only by the rate limiter and the bootstrap check."),
("table", ([0.30, 0.11, 0.59], [
    ["Route", "Auth", "Returns"],
    ["<font face='Courier'>GET /</font>", "—", "App metadata and links to health/docs."],
    ["<font face='Courier'>GET /dashboard</font>", "—", "Serves <font face='Courier'>marketos_dashboard.html</font> directly."],
    ["<font face='Courier'>GET /api/bootstrap-status</font>", "—", "First-time-setup progress; polled by the dashboard on cold start."],
    ["<font face='Courier'>GET /api/routes</font>", "—", "Self-describing list of every registered Flask rule."],
    ["<font face='Courier'>POST /api/auth/register</font>", "—", "Creates a user, returns a 7-day JWT."],
    ["<font face='Courier'>POST /api/auth/login</font>", "—", "Verifies password hash, returns a JWT."],
    ["<font face='Courier'>GET /api/auth/me</font>", "✓", "The authenticated user's id and email."],
    ["<font face='Courier'>GET/POST /api/risk/profile</font>", "✓", "GET reads the stored profile; POST runs the questionnaire (§5.9) and saves it."],
    ["<font face='Courier'>POST /api/execute</font>", "✓", "Runs <font face='Courier'>PaperBroker</font> (§5.9) against a supplied portfolio; returns simulated fills."],
    ["<font face='Courier'>GET /api/healthcheck</font>", "—", "Liveness only."],
    ["<font face='Courier'>GET /api/health/deep</font>", "—", "Liveness plus a DB round-trip and row-count sanity check."],
    ["<font face='Courier'>GET /api/status</font>", "—", "Pipeline date, data source (live/fallback), engine mode, data quality — the market-state snapshot (§2.17)."],
    ["<font face='Courier'>GET /api/sentiment</font>", "—", "Cached per-sector LLM sentiment (§2.7)."],
    ["<font face='Courier'>GET /api/macro</font>", "—", "Latest macro snapshot and regime classification (§2.5)."],
    ["<font face='Courier'>GET /api/alpha</font>", "—", "Ranked composite alpha scores for all 28 subsectors (§2.6)."],
    ["<font face='Courier'>GET /api/portfolio</font>", "✓", "The current allocation for a given horizon and risk profile."],
    ["<font face='Courier'>GET /api/forecasts</font>", "—", "Bull/base/bear per subsector per horizon."],
    ["<font face='Courier'>GET /api/paper-trades</font>", "—", "Logged simulated trades from <font face='Courier'>record_paper_trade()</font>."],
    ["<font face='Courier'>GET /api/risk-limits</font>", "—", "The active constraint set: caps, thresholds, current exposure."],
    ["<font face='Courier'>GET /api/performance</font>", "—", "Rolling MAE/RMSE/Sharpe/IR from <font face='Courier'>performance_engine.py</font> (§8.13)."],
    ["<font face='Courier'>GET /api/backtest</font>", "—", "Cached walk-forward results (§9.2)."],
    ["<font face='Courier'>GET /api/insights</font>", "—", "The generated daily narrative plus its regime context."],
    ["<font face='Courier'>GET /api/sectors</font>", "—", "The taxonomy — sectors, subsectors, companies, weights."],
    ["<font face='Courier'>GET /api/sector-historical-returns</font>", "—", "Per-subsector return series for charting."],
    ["<font face='Courier'>GET /api/sector-performance</font>", "—", "Multi-timeframe analytics from <font face='Courier'>sector_growth_analytics</font>."],
    ["<font face='Courier'>GET /api/macro-history</font>", "—", "Historical macro series for the VIX/crude/FII charts."],
    ["<font face='Courier'>POST /api/run/fetch</font>", "—", "Triggers an out-of-band data refresh job."],
    ["<font face='Courier'>POST /api/run/daily</font>", "—", "Triggers a full pipeline run in the background."],
    ["<font face='Courier'>GET /api/run/status</font>", "—", "Polls the status of a triggered background job."],
])),

("h2", "12.6 Glossary"),
("table", ([0.24, 0.76], [
    ["Term", "One line"],
    ["Alpha", "Return in excess of the benchmark; here, subsector minus NIFTY."],
    ["Attribution", "Decomposing an index move into per-constituent contributions that sum to the total."],
    ["Backtest", "Simulating a strategy using only information available at each historical point."],
    ["Correlation / covariance", "Normalised / raw co-movement between two series."],
    ["Cross-sectional alpha", "Return relative to peers or a benchmark, not absolute."],
    ["Directional accuracy", "How often the sign of the prediction matches the outcome's sign."],
    ["Drawdown", "Decline from a running peak; max drawdown is the worst one."],
    ["Ensemble", "Several models averaged; reduces variance when their errors are uncorrelated."],
    ["Information coefficient", "Spearman rank correlation between predictions and outcomes."],
    ["Information ratio", "Mean alpha ÷ std of alpha, annualised."],
    ["Look-ahead bias", "Using information not available at the time; silently inflates a backtest."],
    ["Markowitz / MVO", "Choosing weights to maximise return per unit of portfolio variance."],
    ["Min-max normalisation", "Rescaling to [0,1] using the cross-section's own min and max."],
    ["Purge / embargo", "Dropping training rows whose target windows overlap the test fold. Not yet done here."],
    ["Regime", "A compressed macro-environment label: BULLISH / NEUTRAL / BEARISH."],
    ["Sharpe ratio", "Excess return per unit of total volatility."],
    ["Shrinkage", "Pulling estimates toward a prior to reduce variance."],
    ["Turnover", "Fraction of the portfolio traded per rebalance; the direct driver of cost."],
    ["Walk-forward validation", "Cross-validation where every test fold is strictly after its training fold."],
])),
("rule", None),
("p", "<b>MarketOS — The Complete Build Bible.</b> Read a concept, then its module, then open the file. "
      "The code tells you what; this guide tells you why, what it measured, and what it got wrong."),
]
