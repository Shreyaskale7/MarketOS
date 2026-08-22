# changelog_content.py
# Content for MARKETOS_CHANGELOG.pdf. Same block vocabulary as
# bible_content_*.py (see build_bible.py's module docstring).
#
# Every entry follows: WHAT changed -> WHY (root cause / user need) ->
# BIBLE REF (which section this updates, corrects, or extends).

BLOCKS = [

# ═══════════════════════════════════════════════════════════════════
("part", (1, "How to read this document",
          "This is not a second bible — it assumes the first one as background and only records "
          "what changed after it was written, why, and which of its sections are now stale.")),

("h2", "1.1 What prompted this"),
("p", "The build bible (<font face='Courier'>MARKETOS_BUILD_BIBLE.pdf</font>) documents the system as "
      "designed and as it stood after the last training run recorded in its Part 9. Taking that same "
      "codebase from a personal script to a live, publicly reachable, automatically-refreshing deployment "
      "surfaced nine distinct correctness bugs, three deployment-stability failures, and a handful of "
      "product decisions that the bible does not yet reflect. This document is the record of that work."),

("h2", "1.2 How entries are structured"),
("p", "Every entry states three things: <b>what</b> changed, in plain terms; <b>why</b> — the root cause "
      "or the concrete symptom that surfaced it, since \"a bug\" without a cause is not useful to future-you; "
      "and <b>bible ref</b> — the exact section of the original document this corrects, extends, or "
      "makes newly true. Where the bible's own words are now wrong, that is stated directly rather than "
      "quietly worked around."),

("box", ("A rule carried over from the bible, applied here too",
         "<b>\"Compute it once, store it, and measure before you optimise.\"</b> Every fix in this "
         "document was found by measuring — a timed API call, a diffed number, a re-read of the actual "
         "response — not by guessing. Several \"obvious\" fixes turned out to be wrong on inspection; "
         "those are recorded too, in §6, because a document that only shows the fixes that worked is as "
         "misleading as one that shows no bugs at all.")),

# ═══════════════════════════════════════════════════════════════════
("part", (2, "Data-correctness bugs",
          "Five bugs where the system ran without error and produced a plausible-looking, wrong number. "
          "The most consequential category, because none of these would show up as a crash.")),

("h2", "2.1 NIFTY unit mismatch corrupted every ML training target"),
("p", "<b>What.</b> <font face='Courier'>ml_forecast_engine.build_training_dataset()</font> computed "
      "every subsector's forward target as <font face='Courier'>sector_return − nifty_return</font> via "
      "compounding. <font face='Courier'>daily_prices.daily_return</font> is a fraction (0.012 = 1.2%); "
      "<font face='Courier'>macro_data.nifty_return</font> is a percent (−8.30 = −8.30%). The compounding "
      "formula assumed both were fractions, so a value like −12.98 became "
      "<font face='Courier'>1.0 + (−12.98) = −11.98</font> — a negative base compounded over a 21–126 day "
      "window. Retraining after the fix produced training targets in the tens of millions of percent."),
("p", "<b>Why it wasn't caught sooner.</b> The bug only produces an obviously-wrong number when a "
      "training window happens to include one of the rare days with a >8% NIFTY move (the 2020 COVID "
      "crash). Most windows never touch such a day, so most target values looked plausible even while "
      "systematically wrong."),
("p", "<b>Fix.</b> Divide <font face='Courier'>nifty_daily_ret</font> by 100 before compounding, so both "
      "sides of the subtraction are in the same units. Verified with a synthetic 126-day window containing "
      "the real 2020-03-23 value: the buggy version returned <font face='Courier'>-100.00%</font> "
      "(floored), the fixed version returned a realistic <font face='Courier'>-17.83%</font>."),
("p", "<b>Bible ref.</b> Corrects §5.7 (\"Forecasting — ml_forecast_engine.py\", the "
      "<font face='Courier'>_compound_forward()</font> walkthrough) and invalidates the measured IC "
      "figures in §9.3 and the 2.5× optimism-bias reading in §9.4 — those numbers were computed on the "
      "corrupted targets and need re-measuring on the corrected ones."),

("h2", "2.2 Duplicated ticker: Tata Motors never existed in the training data"),
("p", "<b>What.</b> <font face='Courier'>classification.py</font> listed both \"Tata Motors\" and "
      "\"Mahindra &amp; Mahindra\" under the ticker <font face='Courier'>M&amp;M.NS</font>. Passenger "
      "Vehicles' entire return series double-weighted M&amp;M and never included Tata Motors at all."),
("p", "<b>Why.</b> A copy-paste error at some point in the taxonomy's history, never caught because "
      "the subsector still produced a plausible-looking return series — just the wrong one."),
("p", "<b>Fix.</b> Corrected to <font face='Courier'>TATAMOTORS.NS</font>; the subsector was re-fetched "
      "and every model touching it retrained."),
("p", "<b>Bible ref.</b> This is the exact bug flagged as a known limitation in §5.2 (\"Three data "
      "defects in the taxonomy, found by counting\") — that section predicted this needed fixing before "
      "deployment; this document records that it now has been."),

("h2", "2.3 ETF map silently routed 4 of 7 sectors to the wrong instrument"),
("p", "<b>What.</b> <font face='Courier'>execution_engine.ETF_MAP</font> used sector-name keys "
      "(\"IT &amp; Tech\", \"FMCG &amp; Consumption\", etc.) that do not match "
      "<font face='Courier'>classification.py</font>'s real names (\"IT &amp; Technology\", "
      "\"Consumer Goods &amp; Retail\"). A failed dict lookup silently fell through to "
      "<font face='Courier'>DEFAULT_ETF = NIFTYBEES.NS</font> — so simulating execution of an IT "
      "overweight bought the plain index instead."),
("p", "<b>Why.</b> No error was ever raised — a missing-key fallback is, by design, silent. This is "
      "exactly the failure shape the bible warns about generally: a string-keyed lookup across module "
      "boundaries with a silent default."),
("p", "<b>Fix.</b> All seven keys corrected to match the taxonomy exactly; a comment added warning that "
      "this is a hard requirement, not a convention."),
("p", "<b>Bible ref.</b> Corrects §5.9 (\"risk_engine.py, risk_profiler.py, execution_engine.py\"), which "
      "had already documented this exact bug as a finding — it is now fixed, not just diagnosed."),

("h2", "2.4 Historical regime classification was permanently NEUTRAL"),
("p", "<b>What.</b> <font face='Courier'>backtest_engine._get_macro_snapshot_for_date()</font> built a "
      "macro dict with no <font face='Courier'>nifty</font> key. "
      "<font face='Courier'>classify_macro_regime()</font> requires one and, finding none, hits its "
      "\"missing return\" safety guard and returns NEUTRAL unconditionally. Every one of the 35 quarterly "
      "rebalances in a 10-year backtest classified as NEUTRAL — including the 2020-03-23 COVID crash."),
("p", "<b>Why it mattered beyond the label.</b> The regime-aware index hedge "
      "(<font face='Courier'>if regime == \"STRONGLY_BEARISH\": hedge = 0.50</font>) was therefore "
      "<b>unreachable dead code</b> for the entire history of the backtest. Hedging was, in practice, "
      "VIX-threshold-only — the regime half of the rule had never once fired."),
("p", "<b>Fix.</b> Added the missing <font face='Courier'>nifty</font> block, sourced from the same "
      "<font face='Courier'>MacroData</font> row. Verified against five historical dates: 2020-03-23 "
      "(the crash) now correctly classifies <font face='Courier'>STRONGLY_BEARISH</font>; calm days "
      "correctly classify <font face='Courier'>BULLISH</font> or <font face='Courier'>NEUTRAL</font> "
      "depending on conditions, instead of NEUTRAL always."),
("p", "<b>Bible ref.</b> Extends §5.10 (\"Backtest — backtest_engine.py\") and directly affects the "
      "hedging discussion in §2.15 and §5.9 — the hedge overlay described there is now, for the first "
      "time, actually reachable in a historical simulation."),

("h2", "2.5 Both AI insight panels rendered the same fallback text with N/A values"),
("p", "<b>What.</b> The forward-looking insight panel showed \"NIFTY 50 gained N/A% today\", "
      "\"regime is Unknown with a score of 0/10\", \"$N/A/barrel\" — while the adjacent daily-narrative "
      "panel, built from the same underlying data, showed real numbers."),
("p", "<b>Why.</b> <font face='Courier'>build_opportunity_prompt()</font> — the forward prompt builder — "
      "never received <font face='Courier'>build_anti_hallucination_prefix()</font>'s output. Only the "
      "daily prompt did. Both the LLM and the no-API <font face='Courier'>_structured_fallback()</font> "
      "regex-matcher were searching for facts (NIFTY level, regime score, crude price) that were simply "
      "never in the forward prompt's text."),
("p", "<b>A second, related bug found while fixing this:</b> both panels called the <i>same</i> fallback "
      "function, so even once the missing facts were supplied, the two panels would have rendered "
      "word-for-word identical text whenever the LLM was unavailable — a dedicated "
      "<font face='Courier'>_forward_structured_fallback()</font> was written, structurally different "
      "(forward-looking: ranked opportunities and macro triggers, not a recap of today)."),
("p", "<b>Fix, verified.</b> The forward prompt now shares the fact prefix and additionally receives the "
      "cached sector sentiment and raw news headlines the sentiment engine already fetches, with an "
      "explicit instruction not to recap what the daily panel already covers."),
("p", "<b>Bible ref.</b> Extends §5.11 (\"Orchestration — main.py\", \"The anti-hallucination prefix\") — "
      "the bible documents the prefix mechanism as applying to \"any narrative\"; it did not, in practice, "
      "reach both narratives, and now does."),

# ═══════════════════════════════════════════════════════════════════
("part", (3, "Deployment-stability failures",
          "Four separate root causes, each independently capable of making the entire dashboard look "
          "broken. All four were live simultaneously before being found and fixed one at a time.")),

("h2", "3.1 The rate limit was smaller than the dashboard's own polling"),
("p", "<b>What.</b> The global Flask-Limiter default was <font face='Courier'>50 per hour</font>. The "
      "dashboard polled <font face='Courier'>/api/status</font> every 10 seconds — "
      "<font face='Courier'>360 requests/hour</font> from a single open tab, before any tab-switching. "
      "The hourly budget was exhausted in <b>8.3 minutes</b>; every subsequent request returned 429, and "
      "every panel's <font face='Courier'>catch</font> block rendered the generic \"run pipeline first\"."),
("p", "<b>Why this was the dominant explanation for \"it worked once, then broke.\"</b> A fresh page "
      "load (or a fresh Render instance, whose in-memory limiter resets on restart) had a full budget; "
      "eight minutes of normal use silently exhausted it, with the resulting error message actively "
      "pointing at the wrong problem."),
("p", "<b>Fix.</b> Global ceiling raised to <font face='Courier'>3000/hour</font> — reads are cheap now "
      "that alpha and portfolio are cached (§4.2, §4.3 below). Narrow limits kept only where they protect "
      "something real: login 20/hr, register 10/hr, job-trigger endpoints 6/hr. Polling interval raised "
      "10s → 60s. A 429 now surfaces as an honest rate-limit message in the console instead of falling "
      "through to the misleading fallback text."),
("p", "<b>Bible ref.</b> Corrects §5.12 (\"Serving — marketos_api.py and the dashboard\"), which "
      "documents the original 200/day, 50/hour limits as a deliberate design choice without measuring "
      "them against the dashboard's own request volume."),

("h2", "3.2 A stray return inside a try block silently killed three panels"),
("p", "<b>What.</b> <font face='Courier'>loadOverview()</font> in the dashboard had a bare "
      "<font face='Courier'>return;</font> inside the \"top opportunities\" section's empty-data branch. "
      "That statement exits the <i>entire</i> async function, not just its own section — so whenever the "
      "3M-forecast filter came up empty (which happens routinely once a tier-based horizon gate exists, "
      "see §5.1), the sector-attribution and mini-insight sections <i>after it in the code</i> never ran "
      "at all, frozen on their static \"Loading...\" placeholder indefinitely."),
("p", "<b>Why it wasn't obvious from the symptom.</b> No exception was thrown; nothing appeared in the "
      "console; the page looked like it was still working, just slow."),
("p", "<b>Fix.</b> Split into four independent functions (<font face='Courier'>loadOverviewChart</font>, "
      "<font face='Courier'>Opportunities</font>, <font face='Courier'>Sectors</font>, "
      "<font face='Courier'>Insight</font>) run via <font face='Courier'>Promise.all</font>, so a "
      "<font face='Courier'>return</font> in one is structurally unable to reach the others."),
("p", "<b>Bible ref.</b> New finding, not previously documented — the dashboard's JavaScript is outside "
      "the bible's Part 8 code annotations, which focus on the Python backend."),

("h2", "3.3 Cold sentiment cache blocked the entire dashboard for 37 seconds"),
("p", "<b>What.</b> <font face='Courier'>/api/alpha</font> called "
      "<font face='Courier'>sentiment_engine.get_live_sentiment_all_sectors()</font> synchronously. On a "
      "cold cache (which a free-tier Render instance hits constantly — it sleeps, and the in-memory cache "
      "does not survive a restart), that call makes 7 sequential LLM requests with inter-sector pauses: "
      "measured at <b>37.7 seconds</b>. The browser's own request timeout gave up well before that, and "
      "every panel depending on alpha or portfolio (which itself calls alpha) fell into its catch block."),
("p", "<b>Fix.</b> Sentiment fetching is now non-blocking by default on the web path: a cold or stale "
      "cache is served as-is (or empty, which <font face='Courier'>alpha_engine</font> already treats as "
      "neutral-50) while a background thread warms it. Measured: <b>0.003s</b> vs 37.7s. The daily "
      "pipeline (<font face='Courier'>main.py --daily</font>) explicitly opts back into blocking mode, "
      "since whatever it computes gets persisted and must be real sentiment, not a placeholder."),
("p", "<b>A second layer added on top:</b> <font face='Courier'>/api/alpha</font> is now cached, keyed "
      "on the pipeline date. Measured: <b>41.26s cold → 0.038s cached.</b>"),
("p", "<b>Bible ref.</b> Extends §2.7 (\"LLM sentiment, and how to stop a language model from lying to "
      "you\") with a fifth defence — non-blocking on the request path — alongside the four already "
      "documented (constrained output, low temperature, hard clamping, graceful degradation)."),

("h2", "3.4 Portfolio endpoint reloaded all 105 model pickles on every request"),
("p", "<b>What.</b> <font face='Courier'>/api/portfolio</font> called "
      "<font face='Courier'>generate_ml_forecasts()</font> on every cache miss — loading all 105 trained "
      "model files (~185MB) and running inference across 28 subsectors × 3 scenarios × 3 horizons. "
      "Measured at <b>~32 seconds</b>, and a real memory-pressure risk on a 512MB instance, since 185MB "
      "of pickled models is over a third of the total budget before Python, Flask and gunicorn's own "
      "footprint is counted."),
("p", "<b>Fix.</b> The endpoint now reads forecasts the daily pipeline already computed and stored in "
      "<font face='Courier'>forward_forecasts</font>, falling back to live generation only if nothing is "
      "stored. Measured: <b>0.034s</b> to load and rebuild the full nested structure for all 28 "
      "subsectors."),
("p", "<b>Bible ref.</b> Extends §5.8 (\"Portfolio — portfolio_engine.py\"), which documents the 12-step "
      "construction pipeline but did not previously address where the forecasts it consumes come from at "
      "serving time."),

("h2", "3.5 Backtest computation inside a request killed the worker with no error"),
("p", "<b>What.</b> <font face='Courier'>/api/backtest</font> computed the simulation live on a cache "
      "miss. A 5-year or 10-year run loads years of price history and simulates 15–35 rebalances; on the "
      "free instance this exceeded the available memory/time budget and the worker died mid-request, "
      "returning <b>an empty response body — no JSON, no error code the dashboard could act on.</b> The "
      "frontend's catch block then left whichever window's numbers were already on screen, so 3Y, 5Y and "
      "10Y appeared to show identical figures under three different buttons."),
("p", "<b>Fix.</b> <font face='Courier'>/api/backtest</font> now serves strictly from cache; an "
      "uncached window returns an explicit <font face='Courier'>not_cached</font> status instead of "
      "attempting the computation. <font face='Courier'>populate_backtest_cache.py</font> was added to "
      "pre-compute all windows out-of-band, from a machine with real memory, and the dashboard now clears "
      "a panel on <font face='Courier'>not_cached</font> rather than silently displaying another "
      "window's numbers."),
("p", "<b>Bible ref.</b> Extends §5.10 and the caching discussion in §2.18 (\"Single source of truth, "
      "idempotency, and caching\") — the anchor-keyed cache design described there is correct and "
      "unchanged; what was missing was ever populating it for anything beyond the original default "
      "window before serving it publicly."),

# ═══════════════════════════════════════════════════════════════════
("part", (4, "Infrastructure fixed at the source",
          "Bugs whose root cause was outside the application's own code — a retired external model, a "
          "structural DB gap, or a frontend URL that only ever worked on localhost.")),

("h2", "4.1 Groq retired every Llama model — every LLM call was silently failing"),
("p", "<b>What.</b> Both <font face='Courier'>sentiment_engine.py</font> and "
      "<font face='Courier'>main.py</font> hardcoded <font face='Courier'>llama-3.1-8b-instant</font>. "
      "Querying the account's actual model catalogue (<font face='Courier'>GET "
      "/openai/v1/models</font>) showed zero Llama models remain on Groq — every request returned "
      "<font face='Courier'>404 model_not_found</font>."),
("p", "<b>Why this was hard to see from the symptom.</b> The retry logic treated a 404 the same as a "
      "transient failure: sleep, retry, fail, per sector — turning one dead model name into a ~32-second "
      "hang across 7 sectors, which is the same class of symptom as §3.3 above, from an entirely "
      "different root cause. And the failure degraded gracefully to \"Error analyzing sentiment.\" and a "
      "no-API template narrative — both plausible-looking outputs, not crashes."),
("p", "<b>Fix.</b> Switched to <font face='Courier'>openai/gpt-oss-20b</font> (tested against the live "
      "API: 1.4–1.9s, correct JSON, real rationales citing specific news). Made the model name "
      "overridable via <font face='Courier'>GROQ_MODEL</font> so the next provider-side deprecation is an "
      "environment-variable change, not a code change and a redeploy. Added a fail-fast path: a 4xx "
      "response now aborts immediately rather than retrying an error that can never succeed."),
("p", "<b>Bible ref.</b> Corrects every reference to <font face='Courier'>llama-3.1-8b-instant</font> "
      "in §2.7, §6.8 (the technology-stack alternatives table) and the interview-defence material in "
      "Part 11 — the model name stated there is retired and no longer accurate."),

("h2", "4.2 forward_insight had no database column"),
("p", "<b>What.</b> The forward narrative was generated and printed by the pipeline, but "
      "<font face='Courier'>DailyInsight</font> had no column for it, and "
      "<font face='Courier'>/api/insights</font> read it only from "
      "<font face='Courier'>outputs/*.json</font> — files that exist on whichever machine ran the "
      "pipeline and, being gitignored, <b>never exist on the deployed instance.</b> The panel was "
      "structurally guaranteed to be empty in production, independent of every other fix in this "
      "document."),
("p", "<b>Fix.</b> Added the column, with a self-migrating <font face='Courier'>ALTER TABLE</font> "
      "guard (the same pattern already used for the <font face='Courier'>users.plan</font> columns, see "
      "§5.2 below) so existing deployments pick it up automatically on next boot. The API now reads the "
      "DB column first, falling back to the JSON file only for historical rows written before the column "
      "existed."),
("p", "<b>Bible ref.</b> Corrects §12.4 (\"The full database schema\") — the "
      "<font face='Courier'>daily_insights</font> table listing there predates this column."),

("h2", "4.3 The dashboard was hardcoded to call localhost, from any origin"),
("p", "<b>What.</b> <font face='Courier'>const API = 'http://localhost:5001';</font>, with a code "
      "comment reading \"update this URL if using ngrok or production\" that was never actioned for this "
      "deployment. Opening the dashboard at the production domain still tried to fetch data from "
      "localhost — a connection that does not exist in the visitor's browser."),
("p", "<b>Fix.</b> <font face='Courier'>const API = window.location.origin;</font> — since the dashboard "
      "is served by the same Flask app it calls, this is correct with zero configuration whether running "
      "locally or deployed, permanently."),
("p", "<b>Bible ref.</b> New finding; the frontend configuration was not previously documented in the "
      "bible as a deployment-sensitive value."),

# ═══════════════════════════════════════════════════════════════════
("part", (5, "Product and security decisions",
          "Choices made, reversed, or added during deployment that change what the system does, not just "
          "how correctly it does it.")),

("h2", "5.1 Freemium tier gating — added, then deliberately removed"),
("p", "<b>What happened, in order.</b> A free/pro plan split was added: free-tier accounts received only "
      "1M-horizon forecasts and a summary-only backtest (no equity curve). Testing the deployment against "
      "this gate surfaced that most of \"3M/6M/12M not showing\" and \"backtest curve not showing\" was "
      "the gate itself, not a bug — but since the product is still being validated end-to-end, the "
      "decision was made to remove it and revisit monetisation once the core product is confirmed working."),
("p", "<b>Why removing it was the right call, not a rollback of a mistake.</b> Gating a not-yet-fully-"
      "validated product hides real bugs from the person trying to test it. The plan-check plumbing "
      "(<font face='Courier'>_current_plan</font>, <font face='Courier'>_optional_plan</font>, "
      "<font face='Courier'>require_plan</font>) was left in place rather than deleted, so re-enabling "
      "gating later is a contained change."),
("p", "<b>Bible ref.</b> Not previously documented — freemium tiering was added and removed entirely "
      "after the bible was written."),

("h2", "5.2 Security hardening: bcrypt, mandatory JWT secret, migration-safe schema changes"),
("bul", [
    "<b>Unsalted SHA-256 → bcrypt</b> (cost 12, random salt), with a transparent one-time upgrade: an "
    "old-format hash that verifies correctly is silently re-hashed to bcrypt and saved, so no existing "
    "account needed a forced password reset.",
    "<b>JWT_SECRET</b> now refuses to boot in production if unset, rather than falling back to a "
    "hardcoded dev value — closes the \"anyone who read this file can forge a token for any user\" gap "
    "described as a finding in the bible.",
    "<b>Self-migrating schema changes.</b> <font face='Courier'>create_all(checkfirst=True)</font> only "
    "creates missing <i>tables</i>, never adds columns to an existing one — so every column added during "
    "this work (<font face='Courier'>users.plan</font>, <font face='Courier'>plan_expires_at</font>, "
    "<font face='Courier'>stripe_customer_id</font>, <font face='Courier'>daily_insights."
    "forward_insight</font>) ships with an <font face='Courier'>ALTER TABLE ADD COLUMN</font> guard that "
    "runs automatically on next boot, verified against the live production database with zero data loss.",
]),
("p", "<b>Bible ref.</b> Corrects §5.12's security findings (unsalted hashing, default JWT secret) from "
      "\"documented gap\" to \"fixed, with the fix verified\"."),

("h2", "5.3 Backtest reconfigured: monthly → quarterly rebalancing, on evidence"),
("p", "<b>What.</b> The default rebalance frequency changed from 30 trading days (monthly, 126-day "
      "training window) to 63 trading days (quarterly, 252-day window)."),
("p", "<b>Why — this was measured, not assumed.</b> A full parameter sweep across "
      "<font face='Courier'>{30, 63, 126}</font> rebalance days × <font face='Courier'>{126, 252}</font> "
      "training days showed the previous default was the <i>worst</i> of six configurations: it traded "
      "20 of 20 rebalances (0 skipped by the turnover filter), costing 3.95%/yr in friction and producing "
      "−9.07% alpha over 3 years. Quarterly/252d cut friction to 1.68%/yr. Both parameters also have a "
      "stated prior independent of the sweep result: momentum is documented in the literature to operate "
      "on 3–12 month horizons, and a 252-day Sharpe estimate is materially less noisy than a 126-day one."),
("warn", ("The honest instability finding — do not omit this when quoting the new numbers",
          "The same configuration measured <b>+4.59% alpha over 10 years (n=35)</b>, "
          "<b>+5.14% at 5 years (n=15)</b>, but <b>−2.33% at 8 years (n=27)</b> — and two identical "
          "reruns of the 10-year window measured <b>+3.00%</b> and <b>+4.59%</b> respectively. A result "
          "that changes sign with the start date, and shifts by ~1.5 points on an identical rerun, is the "
          "signature of a weak or unstable edge. The 10-year figure is quoted as the primary result "
          "specifically because it has the largest sample — not because it is the most flattering. The "
          "3-year window (n=7, Sharpe −0.475) was removed from the public dashboard entirely: seven "
          "observations cannot support a conclusion in either direction.")),
("p", "<b>Bible ref.</b> Directly supersedes the backtest configuration described in §5.10 and the "
      "measured results in Part 9 §9.2 — every number quoted there was computed at the old monthly "
      "setting and is now stale. The methodology described (walk-forward, strict "
      "<font face='Courier'>date &lt; as_of_date</font> boundary, full Indian cost stack) is unchanged "
      "and remains accurate."),

# ═══════════════════════════════════════════════════════════════════
("part", (6, "What did NOT need fixing",
          "Recorded on purpose. A document that only shows successful fixes teaches the wrong lesson — "
          "several suspected bugs turned out, on inspection, to be the system behaving correctly.")),

("h2", "6.1 Portfolio construction was never actually broken"),
("p", "It appeared broken because it was <i>slow</i> (§3.4) — the underlying construction logic, "
      "positions, and weights were correct the entire time. Direct API testing during diagnosis returned "
      "real, sensible positions (Two Wheelers 20%, Industrial &amp; Defence 20%, 9.8% expected return) "
      "well before the performance fix landed. The lesson generalised elsewhere in this document: a panel "
      "showing \"unavailable\" is not evidence the underlying computation is wrong, and each case here was "
      "checked directly against the API before assuming otherwise."),

("h2", "6.2 Forecast Accuracy panel showing empty is correct, not broken"),
("p", "<font face='Courier'>/api/performance</font> correctly returns "
      "<font face='Courier'>status: \"no_data\"</font> with an explanatory message until forecasts "
      "mature — roughly 30+ days after generation, per horizon. A freshly-seeded deployment will show "
      "this panel empty for weeks by design. The only real defect found here was cosmetic: the panel sat "
      "on a static \"Loading...\" placeholder instead of rendering that message, which is now fixed."),

("h2", "6.3 Paper Trading Ledger is architectural, not a bug — and is still open"),
("p", "<font face='Courier'>record_paper_trade()</font> writes to local "
      "<font face='Courier'>data/paper_trades/*.jsonl</font> files, never to the database. This panel "
      "will show zero trades on any deployment whose filesystem differs from the machine that ran the "
      "pipeline — which is every cloud deployment, since none of them share a filesystem with a "
      "developer's laptop. This is flagged here specifically because it is <b>the one item in this "
      "document that remains genuinely unresolved</b>: the fix is real work (moving the ledger to a DB "
      "table), not a quick correction, and has been deliberately deferred rather than rushed."),
("p", "<b>Bible ref.</b> Not previously flagged — the bible's §12.4 schema documentation does not list "
      "a table for paper trades, which is itself evidence this was always file-based, not a regression."),

("rule", None),
("p", "<b>End of change log.</b> Read alongside <font face='Courier'>MARKETOS_BUILD_BIBLE.pdf</font>: "
      "where this document states a section is corrected or superseded, treat this document as current "
      "and the referenced bible section as historical record of the reasoning at the time, not as still-"
      "accurate fact."),
]
