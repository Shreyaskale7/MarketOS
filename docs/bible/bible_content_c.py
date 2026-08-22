# bible_content_c.py
# MarketOS Build Bible v2 — Parts 6, 7, 8.

BLOCKS = [

# ═══════════════════════════════════════════════════════════════════
("part", (6, "The technology stack",
          "Every dependency as a choice against its alternatives. A decision you cannot justify against "
          "an alternative is a default, not a decision.")),

("h2", "6.1 Language and runtime"),
("alts", [
    ["<b>Python 3.10+</b>",
     "The entire numerical/ML ecosystem lives here; the project is one process end to end.",
     "Slower than compiled languages — irrelevant at this scale (a daily batch job, not a trading engine).",
     "*Chosen"],
    ["R", "Arguably stronger built-in statistics.", "Weaker serving/web ecosystem; would need a second "
     "language for the API.", "Rejected"],
    ["Julia", "Faster numerics.", "Thin financial-data ecosystem; smaller hiring pool.", "Rejected"],
]),

("h2", "6.2 Market data"),
("alts", [
    ["<b>yfinance (Yahoo)</b>",
     "Free, no key, ~10yr of daily OHLCV, covers NSE tickers and global macro series in one interface.",
     "No SLA; occasional silent schema changes; adjusted-close semantics not always documented.",
     "*Chosen"],
    ["NSE's own API", "Official, most accurate.", "Unofficial access is aggressively rate-limited and "
     "blocks datacentre IPs.", "Rejected"],
    ["Alpha Vantage (free tier)", "Documented, stable API.", "25 calls/day — unusable for 127 tickers.",
     "Rejected"],
    ["Zerodha Kite Connect", "Excellent, low-latency, official.", "₹2,000/month plus a funded broking "
     "account.", "Rejected — violates the zero-cost goal"],
]),

("h2", "6.3 Database"),
("alts", [
    ["<b>SQLite via SQLAlchemy ORM</b>",
     "Zero configuration, one file, transactional, fast enough — 306,746 price rows query in "
     "milliseconds.",
     "Single-writer; will not scale past one process without care.",
     "*Chosen"],
    ["PostgreSQL", "The production answer; already supported — <font face='Courier'>database.py</font> "
     "rewrites <font face='Courier'>postgres://</font> URLs automatically.",
     "Needs a hosted instance and a connection string to switch to.",
     "One environment variable away"],
    ["Parquet + DuckDB", "Materially faster analytical scans.", "Loses transactional writes, which the "
     "daily ingestion needs.", "Rejected"],
    ["A dedicated time-series DB (InfluxDB)", "The textbook answer for this row shape.",
     "Overkill at 300K rows; another service to operate.", "Rejected"],
]),

("h2", "6.4 ML libraries"),
("alts", [
    ["<b>scikit-learn, optional XGBoost/LightGBM</b>",
     "RF, Ridge, TimeSeriesSplit, StandardScaler, VotingRegressor all in one import; the boosters are "
     "optional so the project installs and runs without them.",
     "No first-class quantile regression or statistical significance testing.",
     "*Chosen"],
    ["PyTorch / TensorFlow", "Would enable LSTMs/transformers.", "Overfits at this row count (§3.1); adds "
     "a heavy dependency for no measured benefit.", "Rejected"],
    ["statsmodels", "Proper significance tests, confidence intervals.", "A genuine gap in the current "
     "build — worth adding alongside, not instead of, scikit-learn.", "Roadmap addition"],
]),

("h2", "6.5 Optimiser"),
("alts", [
    ["<b>SciPy <font face='Courier'>minimize</font>, SLSQP</b>",
     "Handles the non-linear Sharpe objective with constraints, already installed.",
     "Local optimiser; hand-written objective rather than a purpose-built portfolio library.",
     "*Chosen"],
    ["cvxpy", "Provably global optimum after reformulating to a convex QP.", "One more concept (the QP "
     "reformulation) to explain and maintain.", "Roadmap"],
    ["PyPortfolioOpt", "Packages Black-Litterman, shrinkage covariance, CLA out of the box.", "Writing it "
     "by hand was a learning choice, not a performance one.", "Obvious upgrade, not taken"],
]),

("h2", "6.6 API framework"),
("alts", [
    ["<b>Flask + flask-cors + Flask-Limiter</b>",
     "~25 read-mostly JSON endpoints, one file, no build step.",
     "No async, no automatic request validation, no generated docs.",
     "*Chosen"],
    ["FastAPI", "Async, Pydantic validation, free OpenAPI docs.", "A rewrite of the routing layer for a "
     "project where none of the endpoints are latency-critical.", "Better choice today, not the one made"],
    ["Django REST", "Admin panel and auth system out of the box.", "Brings a full framework this project "
     "partly reimplements piecemeal.", "Rejected — too heavy"],
]),

("h2", "6.7 Frontend"),
("alts", [
    ["<b>Single-file HTML dashboard</b>",
     "1,481 lines, no build step, opens from disk — ideal for development and demos.",
     "Maintained alongside a second React implementation; the two will drift.",
     "*Chosen for demos"],
    ["Vite + React", "Componentised, the deployable path, better long-term maintainability.",
     "Needs a build step; currently duplicates the dashboard's panels.", "*Also shipped, for deployment"],
    ["Consolidate to one", "Removes the drift risk entirely.", "Not yet done.", "Tier-3 roadmap"],
]),

("h2", "6.8 LLM provider"),
("alts", [
    ["<b>Groq (llama-3.1-8b-instant), Gemini fallback</b>",
     "Sub-second inference on a free tier; OpenAI-compatible, so the client is ordinary HTTP.",
     "Smaller model than the README claims (documentation drift, flagged in Part 8); free-tier rate "
     "limits.",
     "*Chosen"],
    ["OpenAI / Anthropic", "Stronger reasoning and instruction-following.", "Paid — conflicts with the "
     "zero-cost goal.", "Rejected"],
    ["Ollama, local", "No rate limit, no data leaves the machine.", "Needs local compute the deployment "
     "target may not have.", "Rejected for deployability"],
    ["FinBERT, local classifier", "Purpose-built for financial sentiment; no API dependency at all.",
     "No written rationale, which the daily narrative currently relies on.", "Worth benchmarking"],
]),

("h2", "6.9 Scheduling"),
("alts", [
    ["<b>APScheduler, in-process</b>", "One dependency, cron-like trigger inside the same process.",
     "Does not survive a process crash — a crashed server simply stops running the daily job.",
     "*Chosen"],
    ["cron / systemd timers", "Survive a process crash; the OS restarts the job independently.",
     "Needs OS-level access to configure, which not every deployment target grants.", "More robust, not "
     "used"],
    ["Celery + Redis", "The distributed answer.", "Unwarranted operational overhead for one job a day.",
     "Rejected"],
]),

("h2", "6.10 What was deliberately left out"),
("bul", [
    "<b>No paid data</b> — a design goal, not a workaround. Every limitation that follows from it (no "
    "free-float weights, no real FII/DII, no intraday bars) is disclosed rather than hidden.",
    "<b>No live broker connection</b> — order payloads are generated and simulated only; wiring a real "
    "account would convert a research tool into an execution system with regulatory obligations.",
    "<b>No deep learning</b> — §3.1 explains why the data does not support it yet.",
    "<b>No intraday</b> — daily close only; a different cost model and latency budget entirely.",
    "<b>No test suite</b> — the largest infrastructure gap, named directly in Part 9.",
]),

# ═══════════════════════════════════════════════════════════════════
("part", (7, "Build it from zero: the complete walkthrough",
          "The order to build this in, and why. Each milestone ends with something runnable and a number "
          "you can quote.")),

("h2", "7.0 Three decisions to make before any code"),
("num", [
    "<b>Unit of prediction</b> — company, subsector, or sector. This fixes the schema, the model count, "
    "and what you can ever claim. See §1.3.",
    "<b>Target definition</b> — absolute return or relative to a benchmark. This determines whether your "
    "metrics are meaningful or flattering. See §1.2.",
    "<b>The benchmark</b> — fix it once, compute it in exactly one place, never let a second definition "
    "in. See §5.1.",
]),
("box", ("Build order principle",
         "<b>Build the boring, correct, measurable version before the impressive one.</b> The temptation "
         "is to start with the ML, because it is the interesting part. Don't. Build the database, "
         "taxonomy and calendar first — every later stage reads from them, and a schema mistake there "
         "costs a rewrite. Then build attribution, the one component you can verify by hand — it catches "
         "data bugs that would otherwise surface as mysteriously bad model performance three milestones "
         "later.")),

("h2", "7.1 Milestones"),
("table", ([0.10, 0.24, 0.40, 0.26], [
    ["M#", "Goal", "Build", "Ship when"],
    ["M0", "Skeleton", "Schema (§4.2), taxonomy with macro-sensitivity maps (§8.2), NSE calendar (§5.4), "
     "single pipeline date + benchmark (§5.1).",
     "<font face='Courier'>python database.py</font> creates tables; the calendar correctly flags a "
     "holiday."],
    ["M1", "Ingestion + attribution", "Batch OHLCV fetch with the ±5% circuit breaker (§5.3) from day "
     "one; contribution engine with the normalisation guards (§2.3).",
     "Sector contributions sum to the actual NIFTY return, and you have hand-verified one day."],
    ["M2", "Regime + sentiment + alpha", "Six-signal regime classifier (§2.13) — check the label "
     "distribution before shipping; sentiment with the JSON/clamp/cache defences (§8.5); the five-signal "
     "alpha composite (§2.7).",
     "The regime label distribution over the last 100 days is one you can defend."],
    ["M3", "ML forecast layer", "Build the target function first, test it alone (§1.2); walk-forward CV "
     "with the scaler inside the fold (§3.3); the model tournament (§3.5).",
     "Mean CV information coefficient is positive at every horizon and you can state it."],
    ["M4", "Portfolio + risk", "MVO with the inverse-vol fallback built at the same time, not later "
     "(§4.1); the eleven monotonic risk rules (§4.4); the risk-profile questionnaire.",
     "Weights sum to one, no constraint is violated, and the fallback path has been exercised "
     "deliberately."],
    ["M5", "Backtest", "Walk-forward with a strict <font face='Courier'>&lt;</font> boundary (§4.6); the "
     "full Indian cost stack (§4.7); turnover control (§4.8); anchor-keyed cache (§5.7).",
     "You can point at the line enforcing the boundary and state the cost model's components from "
     "memory."],
    ["M6", "Serving", "10-stage orchestrator with per-stage isolation (§5.5); Flask API with the uniform "
     "envelope (§5.8); dashboard.",
     "The API survives one engine deliberately being made to throw."],
])),
("box", ("Build the evaluation before the model",
         "Write <font face='Courier'>_walk_forward_cv()</font> first, run it on a Ridge baseline, and "
         "write that number down. Every later model change is then measured against a fixed prior number "
         "on a fixed split — not assessed by whether the printed forecasts look plausible. Without that "
         "baseline you cannot tell an improvement from a coincidence.")),
("box", ("The three questions your backtest must survive",
         "<b>1. Where is the look-ahead?</b> Point at the line. Here: "
         "<font face='Courier'>sector_df[sector_df.index &lt; as_of_date]</font>.\n"
         "<b>2. What did it cost?</b> If the answer is an invented flat percentage, the backtest is "
         "decorative.\n"
         "<b>3. How many independent observations?</b> Not trading days — <i>rebalances</i>. This "
         "system's 3-year backtest has 21.")),

# ═══════════════════════════════════════════════════════════════════
("part", (8, "The codebase, annotated",
          "The concepts above, in the actual code, with the reasoning behind the lines that matter.")),

("h2", "8.1 database.py"),
("code", """_base = "/data" if os.path.exists("/data") else "."     # detect a mounted persistent volume
_db_path = os.getenv("DATABASE_URL")
if _db_path and _db_path.startswith("postgres://"):
    _db_path = _db_path.replace("postgres://", "postgresql://", 1)   # SQLAlchemy 2.x dropped this scheme"""),
("p", "The <font face='Courier'>/data</font> probe detects the convention on Render/Railway/Fly.io and "
      "relocates writes there, because a container filesystem is ephemeral. The "
      "<font face='Courier'>postgres://</font> rewrite exists because these platforms inject that scheme "
      "while modern SQLAlchemy requires <font face='Courier'>postgresql://</font>; without it the app "
      "boots locally and dies in production with a driver error."),
("h3", "Nine analytical tables"),
("table", ([0.24, 0.14, 0.62], [
    ["Table", "Rows shipped", "Purpose"],
    ["<font face='Courier'>daily_prices</font>", "306,746", "One row per ticker per day, with the "
     "sector/subsector/weight denormalised in — deliberately, to remove a join from the hottest query "
     "path."],
    ["<font face='Courier'>macro_data</font>", "3,781", "One row per calendar day, 14 macro series."],
    ["<font face='Courier'>model_versions</font>", "1,730 (175 active)", "The audit trail: IC, MAE, "
     "directional accuracy, training window, top-20 feature importances, per model."],
    ["<font face='Courier'>forward_forecasts</font>", "112", "Bull/base/bear per subsector per horizon."],
    ["<font face='Courier'>prediction_accuracy</font>", "94,500", "Predicted vs realised, for the "
     "feedback loop (§9.4)."],
    ["<font face='Courier'>backtest_cache</font>", "4", "Anchor-keyed cached walk-forward results (§5.7)."],
])),

("h2", "8.2 classification.py — the domain-knowledge layer"),
("code", """"PSU Banks": {
    "subsector_weight_in_sector": 0.35,
    "macro_sensitivity": {"repo_rate": "HIGH_POSITIVE", "fii_flows": "MEDIUM_POSITIVE", ...},
    "companies": {"State Bank of India": {"ticker": "SBIN.NS", "sector_weight": 0.089}, ...}
}

STRICT_SECTOR_DRIVER_MAP = {                 # domain knowledge overrides a data-driven ranking
    "Energy & Oil & Gas": "brent_crude",     # NOT whichever macro var moved most that day
    "IT & Technology":    "usdinr",
    ...
}"""),
("p", "580 lines of pure data: 7 sectors, 28 subsectors, 130 entries. Encoding domain knowledge as data "
      "rather than branching logic means a new subsector is a dictionary entry, not a code change — and a "
      "domain expert who does not write Python can audit the assumptions directly. The strict driver map "
      "exists because without it, Energy's “primary driver” on a volatile-rupee day would be reported as "
      "the rupee, which is domain-nonsense: Energy is driven by crude, and the rupee is second-order."),
("warn", ("Three data defects, found by counting",
          "130 entries resolve to only <b>127 unique tickers</b>. "
          "<font face='Courier'>MPHASIS.NS</font> appears under both “LTIMindtree” and “Mphasis” — a "
          "documented substitution that still double-counts one company across two subsectors. "
          "<b><font face='Courier'>M&amp;M.NS</font> is listed as both “Tata Motors” and “Mahindra &amp; "
          "Mahindra”</b> — Tata Motors is actually <font face='Courier'>TATAMOTORS.NS</font>; this "
          "subsector's entire return series double-weights M&amp;M and omits Tata Motors. "
          "<font face='Courier'>EICHERMOT.NS</font> appears under both “Eicher Motors” and “VE Commercial "
          "Vehicles” — defensible (VECV is an Eicher JV with no separate listing) but should be one entry "
          "at combined weight.\n\nSeparately, the seven sector weights sum to <b>0.95</b>, not 1.00.")),

("h2", "8.3 data_loader.py — the synthetic-flows decision"),
("code", """fii_net_crore = (nifty_return - usdinr_return) * 1500
dii_net_crore = -0.75 * fii_net_crore + nifty_return * 1000 + 800"""),
("p", "Real FII/DII flows are published by NSDL/SEBI with no free programmatic feed, so they are "
      "synthesised from a plausible economic story: foreign flows correlate with index direction and "
      "inversely with rupee weakness; domestic flows lean against foreign flows plus a positive SIP "
      "drift."),
("warn", ("What the synthesis costs",
          "<font face='Courier'>fii_net_crore</font> is a linear function of "
          "<font face='Courier'>nifty_return</font>. FII and DII together carry 25% of the regime "
          "composite's weight — so a quarter of that score is a re-labelled index return. The same "
          "quantities are also ML training features, so any importance the model assigns to “flows” is "
          "really importance assigned to same-day index momentum. Not classical look-ahead — the target "
          "is forward-looking — but the honest framing matters: <i>“these are proxies I built because "
          "the real series is not free; replacing them with NSDL data is my highest-value data "
          "upgrade.”</i>")),
("code", """nifty_ret_saved = macro_df['nifty_return'].copy()          # BUG FIX: save before reindex
macro_df = macro_df.reindex(date_range).ffill().bfill()     # levels: fine to forward-fill
macro_df['nifty_return'] = nifty_ret_saved.reindex(date_range)  # returns: restore, stay NaN on non-trading days"""),
("p", "Forward-filling macro <i>levels</i> across a weekend is correct — Saturday's repo rate is Friday's. "
      "Forward-filling a <i>return</i> is not: it manufactures a fake “market did nothing” observation on "
      "a day the market did not exist. A level and a change are never interchangeable under "
      "interpolation."),

("h2", "8.4 contribution_engine.py"),
("code", """def company_contribution_pct(return_pct, weight_pct):
    return return_pct * weight_pct / 100.0

coverage = valid / max(len(companies), 1)
if coverage < 0.5:
    print(f"WARNING: {sub_name} - {valid}/{len(companies)} cos ({coverage:.0%} coverage)")"""),
("p", "Contribution (index points attributable) and weighted return (how the subsector itself performed) "
      "are computed and returned separately — they answer different questions and are constantly "
      "confused. Coverage is surfaced as a first-class number rather than silently averaging whatever "
      "data arrived, so a reader can discount a suspicious reading instead of trusting it blindly."),

("h2", "8.5 sentiment_engine.py — constraining an LLM's output"),
("code", """data = {"model": "llama-3.1-8b-instant", "temperature": 0.1,
        "response_format": {"type": "json_object"}}
score = max(-1.0, min(1.0, score))                    # hard clamp regardless of what the model returned
# 2 retries w/ backoff -> {"score": 0.0, "label": "NEUTRAL"} on total failure
# 12h disk cache: reproducible re-runs, survives process restart"""),
("p", "Four independent defences on the only non-deterministic component that touches a portfolio-facing "
      "number: JSON-constrained output, low temperature for near-determinism, a hard clamp that does not "
      "trust the model to respect a range described only in prose, and safe degradation to neutral rather "
      "than a crash."),
("warn", ("Documentation drift",
          "The README advertises Groq LLaMA-3.3-70B; the code requests "
          "<font face='Courier'>llama-3.1-8b-instant</font> — a smaller model chosen for free-tier "
          "latency, adequate for coarse three-bucket sentiment but not what is claimed.")),

("h2", "8.6 macro_engine.py"),
("p", "1,764 lines, three-quarters of it the human-readable explanation attached to each signal bucket — "
      "not padding: it is what the LLM narrative prompt is assembled from, and generating the score, the "
      "label and the sentence at the same decision point guarantees they cannot disagree."),
("code", """if nifty_change < -1.0 and overall in ["BULLISH", "STRONGLY_BULLISH"]:
    overall, regime_score = "NEUTRAL", min(regime_score, 0.10)   # sanity backstop"""),
("p", "Whatever the macro components compute, the system will not print BULLISH on a day the index fell "
      "more than 1%. Because of the missing NIFTY term (§2.13), this override is currently the <i>only</i> "
      "channel through which price action reaches the label."),

("h2", "8.7 alpha_engine.py"),
("code", """mac_norm = mac_raw / 100.0     # NOT min-max normalised - see §2.7
sen_norm = sen_raw / 100.0     # NOT min-max normalised - see §2.7

if _regime_label in ("BEARISH","RISK_OFF","STRONG_BEAR"): _active_threshold = 0.45
elif _regime_label in ("MILD_BEARISH",):                  _active_threshold = 0.48   # stricter than BEARISH
else:                                                      _active_threshold = 0.40"""),
("p", "Raising the threshold in a bearish regime is intentional — fewer subsectors pass, which is the "
      "conservative direction. But MILD_BEARISH (0.48) is stricter than full BEARISH (0.45), almost "
      "certainly a transposition and a good example of why threshold tables belong in tests."),
("p", "On a non-trading day, momentum/mean-reversion/vol are zeroed and alpha is scored from macro "
      "alignment and sentiment alone — the output degrades and is labelled rather than crashing or going "
      "stale."),

("h2", "8.8 ml_forecast_engine.py"),
("code", """def _compound_forward(r_series, base_series, n):
    for i in range(len(vals) - n):
        window   = vals[i+1 : i+1+n]        # strictly forward — never includes today
        b_window = b_vals[i+1 : i+1+n]      # NIFTY over the IDENTICAL window
        result[i] = (prod(1+window)-1)*100 - (prod(1+b_window)-1)*100"""),
("p", "Three details carry the correctness of the whole system: the slice starts at "
      "<font face='Courier'>i+1</font>; the benchmark window is byte-identical to the feature window, so "
      "the market's move cancels exactly; and the final <font face='Courier'>n</font> rows become NaN and "
      "are dropped, correctly, because the future has not happened yet."),
("warn", ("A field that is hardcoded",
          "Every forecast is emitted with <font face='Courier'>\"directional_accuracy\": round(0.5, 3)</font> "
          "— a literal, not the model's measured value sitting in "
          "<font face='Courier'>payload[\"directional_acc\"]</font> a few lines above. Confidence scoring "
          "is unaffected (it reads the correct variable); this is a display bug a single assertion would "
          "have caught.")),

("h2", "8.9 portfolio_engine.py"),
("code", """def _score(row):
    raw = (row["exp_return"] * row["confidence"] * row["alpha_score"]) / (1.0 + 0.7*row["volatility"])
    if row["volatility"] > 30.0: raw *= 0.85
    return max(raw, 0.0)      # never negative -> this system cannot go short"""),
("box", ("Why the fallback ladder exists",
         "Selection thresholds relax progressively (0.45→0.42→0.40→0.0 on alpha; 5%→0%→equal-weight on "
         "expected return) rather than erroring when a bearish regime legitimately excludes 26 of 28 "
         "subsectors. This is the right structural answer, and the tuning is not there yet: the shipped "
         "3M portfolio for 2026-08-13 holds 5 subsectors across only 2 sectors, against a "
         "<font face='Courier'>MIN_SECTORS</font> of 5 — the ladder rescued the run from emptiness but "
         "did not reach the diversification floor.")),

("h2", "8.10 risk_profiler.py and execution_engine.py"),
("code", """age <30 -> 25 | <=45 -> 20 | <=60 -> 10 | else 5      # capacity
income >50L -> 25 | ...                                # capacity
horizon >5Y -> 25 | ...                                # need
drawdown tolerance >20% -> 25 | ...                    # willingness
total >=75 Aggressive | >=50 Moderate | else Conservative"""),
("p", "Four dimensions, twenty-five points each, mirroring the standard SEBI-adviser suitability "
      "framework: two for capacity, one for need, one for willingness. The label then forces the "
      "portfolio engine's caps regardless of what the optimiser or regime wanted."),
("warn", ("The ETF map does not match the taxonomy",
          "<font face='Courier'>execution_engine.ETF_MAP</font> is keyed on sector names that do not "
          "exist in <font face='Courier'>MARKET_CLASSIFICATION</font> — “IT &amp; Tech” vs "
          "“IT &amp; Technology”, and similarly for three more. <b>Four of seven sectors silently fall "
          "back to <font face='Courier'>NIFTYBEES.NS</font></b>, and simulated execution of an IT "
          "overweight buys the index. A string-keyed lookup across module boundaries with a silent "
          "default is worth being generally suspicious of — the failure is invisible precisely because "
          "the default is sensible.")),

("h2", "8.11 backtest_engine.py"),
("code", """cum_sub = (1 + sub_rets).cumprod()
drawdown = (cum_sub - cum_sub.cummax()) / cum_sub.cummax()
if (drawdown <= -0.08).any():
    hit = (drawdown <= -0.08).values.argmax()
    if hit + 1 < len(sub_rets):
        sub_rets.iloc[hit+1:] = 0.0        # exit AFTER the trigger day, not on it"""),
("p", "That <font face='Courier'>+1</font> is the difference between a simulation and a fantasy: zeroing "
      "from the trigger day itself would exit at a price only knowable at that day's close — a one-day "
      "look-ahead large enough to turn a losing strategy into a winning one in a backtest."),

("h2", "8.12 main.py and marketos_api.py"),
("p", "1,243-line orchestrator, ten stages, each independently wrapped (§5.5). "
      "<font face='Courier'>marketos_api.py</font> serves ~25 endpoints behind a uniform envelope (§5.8), "
      "a bootstrap gate so requests during the 30–90 minute first-time setup get a status instead of an "
      "exception, and security headers (<font face='Courier'>X-Frame-Options: DENY</font>, HSTS) plus "
      "rate limiting at 200/day and 50/hour with a no-op shim if the limiter package is absent."),

("h2", "8.13 The four modules not covered above"),
("p", "Every other module in the repo gets its own annotated section. These four are smaller, secondary, "
      "or superseded — but they are real, they run, and an interviewer who has read the repo listing can "
      "ask about any of them."),

("h3", "forward_engine.py — the rule-based forecast fallback and growth analytics"),
("p", "Two separable jobs live in this 1,440-line file. The first, "
      "<font face='Courier'>generate_forward_forecasts()</font>, is the forecaster "
      "<font face='Courier'>main.py</font> falls back to when no trained "
      "<font face='Courier'>data/models/ml_horizon/*.pkl</font> exists — a hand-written scoring function "
      "over macro features rather than a fitted model, so the pipeline produces <i>something</i> on a "
      "fresh checkout before <font face='Courier'>--train-ml</font> has ever run. The second, "
      "<font face='Courier'>compute_sector_growth_analytics()</font>, is unconditional and always runs: "
      "it computes total return, annualised return, volatility, Sharpe, max drawdown, best/worst month, "
      "beta and correlation to NIFTY for every subsector across seven windows — 1M, 3M, 6M, 1Y, 3Y, 5Y, "
      "10Y — and is what populates the 1,008 rows in "
      "<font face='Courier'>sector_growth_analytics</font> (§9.1)."),
("code", """timeframes = {"1M": 30, "3M": 90, "6M": 180,
              "1Y": 365, "3Y": 365*3, "5Y": 365*5, "10Y": 365*10}
# for each subsector: pull DailyPrice back 11 years, weight by nifty_weight,
# compound into total_return_pct, annualise, compute vol/Sharpe/drawdown/beta"""),
("p", "This is also the source of the sector-level Sharpe and beta figures shown on the dashboard's "
      "historical panel — separate from, and computed differently than, the walk-forward backtest's "
      "portfolio-level Sharpe in §9.2. Conflating the two in conversation is an easy mistake to make and "
      "worth guarding against: one describes a subsector standing alone over history, the other describes "
      "the constructed portfolio under simulated trading."),
("h3", "model_trainer.py — the superseded per-sector trainer"),
("p", "This was the original training path, later replaced in the live pipeline by "
      "<font face='Courier'>ml_forecast_engine.py</font> (§5.7), and it is worth reading for one reason: "
      "its <font face='Courier'>select_best_model()</font> reports both in-sample and out-of-sample "
      "Spearman correlation side by side, and prints the gap as an explicit overfit percentage —"),
("code", """for name, model in {'ridge': ..., 'gbm': ..., 'rf': ...}.items():
    # ... walk-forward CV ...
    overfit = (r2_is - r2_oos) / r2_is if r2_is > 0 else 0
    print(f"{name}: IS={r2_is:.3f} | OOS={r2_oos:.3f} | Overfit={overfit*100:.1f}%")"""),
("p", "That printed overfit percentage never made it into "
      "<font face='Courier'>ml_forecast_engine.py</font>'s tournament, which reports only the "
      "out-of-sample number. It is a genuinely good diagnostic — the gap between in-sample and "
      "out-of-sample correlation is a direct read on how much a candidate model is memorising versus "
      "generalising — and reviving it in the current trainer is a small, cheap addition with real "
      "diagnostic value, distinct from anything on the Part 10 roadmap because it costs almost nothing "
      "to add."),
("h3", "performance_engine.py — Sharpe, information ratio and drawdown as reusable primitives"),
("p", "Four small, independently testable functions — "
      "<font face='Courier'>_compute_sharpe()</font>, <font face='Courier'>_compute_information_ratio()</font>, "
      "<font face='Courier'>_compute_max_drawdown()</font>, <font face='Courier'>_compute_mae_rmse()</font> "
      "— that <font face='Courier'>backtest_engine.py</font> deliberately does <i>not</i> import and "
      "instead reimplements inline. This module exists to score <b>live prediction history</b> — the "
      "<font face='Courier'>prediction_accuracy</font> table — on a rolling basis via "
      "<font face='Courier'>compute_performance_summary()</font>, which is a different question from "
      "scoring a walk-forward simulation, and keeping the two separate rather than sharing one function "
      "means a bug in one cannot silently corrupt the other's numbers. The trade-off, visible if you "
      "diff the two Sharpe implementations, is that they can drift out of sync — a genuine, minor "
      "maintenance cost of the separation."),
("h3", "feedback_evaluator.py — the shortest file with the most consequential number"),
("p", "89 lines. <font face='Courier'>evaluate_forecast_accuracy()</font> is what turns a "
      "<font face='Courier'>forward_forecasts</font> row into a "
      "<font face='Courier'>prediction_accuracy</font> row once its target date has passed: it pulls "
      "actual subsector prices over the forecast window, compounds them, compares sign and magnitude "
      "against the stored prediction, and writes direction-correct and error-percent. This is, "
      "structurally, the single most important piece of infrastructure for keeping the system honest — "
      "it is the only code path that closes the loop from prediction back to outcome. It is also the "
      "source of the 94,500-row table analysed in §9.4, and re-reading its loop confirms something worth "
      "stating plainly: it evaluates <i>whichever forecasts have matured as of whenever it is run</i>, "
      "with no built-in schedule of its own. The fact that all 94,500 stored rows share one "
      "<font face='Courier'>evaluated_date</font> means this function was run once, in bulk, over a large "
      "backlog of already-matured forecasts — not run daily as new forecasts matured one at a time. "
      "Wiring it into the daily scheduler alongside <font face='Courier'>--daily</font> is a one-line "
      "change and turns this from a one-off audit into the live accuracy feed the confidence scores in "
      "§9.3 deserve."),
]
