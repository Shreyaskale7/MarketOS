# bible_content_a.py
# MarketOS Build Bible v2 — Parts 0, 1, 2.
# Concept template: What / Why here / Worked example / Alternatives table.
# Body text is reportlab paragraph markup: escape & as &amp; and < as &lt;.
# In ("alts", ...) rows, a verdict prefixed with "*" marks MarketOS's choice.

BLOCKS = [

# ═══════════════════════════════════════════════════════════════════
("part", (0, "Foundations — start from zero",
          "What this is, what you need, and how to get it running. "
          "Assumes basic Python and a terminal. Nothing else.")),

("h2", "0.1 What this project is"),
("p", "After the NSE closes at 15:30 IST, an equity research desk answers four questions: "
      "<b>what moved, why, what moves next, what do we hold?</b> That is normally four people and a "
      "six-figure data bill."),
("p", "MarketOS is one Python program that answers all four daily for <b>130 company listings across 7 "
      "sectors and 28 subsectors</b>, on free data. It ingests prices and macro series, decomposes the "
      "NIFTY move by contributor, classifies the macro regime, ranks subsectors by expected "
      "outperformance, forecasts forward <i>relative</i> returns with ML, solves a constrained Markowitz "
      "portfolio, applies a risk overlay, and validates the whole thing on a walk-forward backtest with "
      "realistic Indian transaction costs."),
("box", ("The product is the chain of custody, not the prediction",
         "Anyone can print a number. Every number in the final portfolio here traces back through a "
         "scoring formula, to a model with a recorded out-of-sample information coefficient, trained on "
         "a dataset with a recorded window, from prices with a recorded source date — and the chain is "
         "re-scored against NIFTY on history before you are asked to believe it.")),

("h2", "0.2 The mental model"),
("p", "Ten stages, in order. Every concept in Parts 2–5 is a tool used by one of them; every module in "
      "Part 8 implements one."),
("table", ([0.06, 0.20, 0.44, 0.30], [
    ["#", "Stage", "What it does", "Module"],
    ["1", "Ingest", "Download OHLCV + macro series, compute returns, write to SQLite. Nothing downstream "
     "touches the network.", "<font face='Courier'>data_loader.py</font>"],
    ["2", "Attribute", "Decompose today's NIFTY move into per-company and per-sector contributions. "
     "The <i>what</i>.", "<font face='Courier'>contribution_engine.py</font>"],
    ["3", "Classify regime", "Six macro readings → one score in [−1, +1] → BULLISH / NEUTRAL / BEARISH. "
     "The <i>why</i>.", "<font face='Courier'>macro_engine.py</font>"],
    ["4", "Read news", "RSS headlines → LLM → sentiment in [−1, +1] with a rationale.",
     "<font face='Courier'>sentiment_engine.py</font>"],
    ["5", "Score alpha", "Momentum, mean reversion, vol expansion, macro alignment, sentiment → one "
     "composite, ranked across 28.", "<font face='Courier'>alpha_engine.py</font>"],
    ["6", "Forecast", "Per subsector × 4 horizons: forward return <i>relative to NIFTY</i>, under bull / "
     "base / bear.", "<font face='Courier'>ml_forecast_engine.py</font>"],
    ["7", "Optimise", "Expected returns + covariance → max-Sharpe weights under concentration caps.",
     "<font face='Courier'>portfolio_engine.py</font>"],
    ["8", "De-risk", "Eleven mechanical rules that can only reduce exposure.",
     "<font face='Courier'>risk_engine.py</font>"],
    ["9", "Explain", "Build a prompt from the numbers actually computed; LLM writes the narrative.",
     "<font face='Courier'>main.py</font>"],
    ["10", "Measure", "Re-run the selection logic walk-forward on history; record alpha, Sharpe, IR, "
     "drawdown, cost drag.", "<font face='Courier'>backtest_engine.py</font>"],
])),

("h2", "0.3 Prerequisites"),
("bul", [
    "<b>Python</b> — functions, classes, dicts, comprehensions, <font face='Courier'>import</font>. No ML "
    "or finance background needed; both are taught here.",
    "<b>Terminal</b> — run a command, change directory, activate a virtualenv.",
    "<b>Nice to have</b> — a rough idea of SQL and of what an HTTP API is.",
]),

("h2", "0.4 Setup"),
("code", """$ python --version                 # 3.10+
$ git clone <repo> marketos && cd marketos
$ python -m venv venv
$ venv\\Scripts\\activate            # Windows
$ source venv/bin/activate         # macOS / Linux
$ pip install -r requirements.txt

# .env  (two free-tier keys)
GROQ_API_KEY   = gsk_...
GEMINI_API_KEY = AIza...

$ python main.py --setup           # 30-90 min: 10yr of data, then trains ~500 model fits
$ python main.py --daily           # one full pipeline run
$ python marketos_api.py           # API + dashboard on :5001"""),
("p", "Pinned versions matter. <font face='Courier'>yfinance</font> changes its response shape between "
      "minor releases; <font face='Courier'>numpy 2.x</font> cannot unpickle scikit-learn models trained "
      "under 1.x."),

("h2", "0.5 Data sources"),
("table", ([0.20, 0.11, 0.41, 0.28], [
    ["Source", "Cost", "Provides", "Config"],
    ["Yahoo Finance (<font face='Courier'>yfinance</font>)", "Free",
     "10 years of daily OHLCV for 127 NSE tickers, plus NIFTY, SENSEX, India VIX, USD/INR, Brent, NASDAQ, "
     "S&amp;P 500, gold.", "None"],
    ["Google News RSS", "Free", "Top headlines per sector proxy ticker.", "Hard-coded URL"],
    ["Groq", "Free tier", "LLM: sector sentiment as strict JSON, plus the daily narrative.",
     "<font face='Courier'>GROQ_API_KEY</font>"],
    ["Google Gemini", "Free tier", "Narrative fallback when Groq is rate-limited.",
     "<font face='Courier'>GEMINI_API_KEY</font>"],
    ["RBI / MOSPI / GST Council", "Free, manual",
     "Repo rate, GDP, GST, CPI, IIP — policy series with no free real-time feed.",
     "<font face='Courier'>MANUAL_MACRO</font> constants"],
])),
("warn", ("The manual-macro trap",
          "Repo rate, GDP, GST, CPI and IIP are constants in code, back-filled as one value across the "
          "whole ten-year training set. A model learns nothing from a column that never varies — and "
          "<font face='Courier'>rate_momentum</font>, a 63-day difference of the repo rate, is "
          "<b>identically zero on every training row</b>. Any importance reported for it is noise. "
          "Real limitation; Tier-2 roadmap item.")),

("h2", "0.6 The one rule"),
("box", ("Prime directive",
         "<b>Compute it once, store it, never let two modules disagree about the date or the benchmark. "
         "Then prove it on history before believing it.</b>")),
("table", ([0.20, 0.44, 0.36], [
    ["Consequence", "Enforced by", "What it prevents"],
    ["One clock", "<font face='Courier'>pipeline_utils.get_pipeline_date()</font> — the only function "
     "allowed to decide the pipeline date.",
     "Attribution thinking it is Tuesday while risk thinks it is Wednesday. Individually plausible "
     "numbers, jointly meaningless."],
    ["One benchmark", "<font face='Courier'>pipeline_utils.get_nifty_return_from_db()</font> — the only "
     "place a NIFTY return is computed.",
     "Everything is measured relative to NIFTY. Two definitions corrupt every downstream comparison."],
    ["One database", "After ingestion, nothing touches the network for price data.",
     "Non-determinism. You can re-run yesterday exactly."],
])),

# ═══════════════════════════════════════════════════════════════════
("part", (1, "The big picture",
          "Why the problem is hard, why the obvious approach fails, and what this system bets on instead.")),

("h2", "1.1 Four walls"),
("table", ([0.24, 0.44, 0.32], [
    ["Wall", "The problem", "The response in this system"],
    ["<b>Signal-to-noise</b>",
     "Daily equity returns are ~95% noise. An out-of-sample rank correlation of 0.05 across many names "
     "is a viable strategy. Recalibrate from any domain where 95% accuracy is mediocre.",
     "Report information coefficient, not accuracy. Measured: +0.089 to +0.170 (Part 9)."],
    ["<b>Non-stationarity</b>",
     "Relationships change. A weak rupee unambiguously helped IT pre-2020; much less so post-2022. Ten "
     "years of data is several regimes glued together.",
     "Classify the regime explicitly as a feature rather than hoping the model infers it."],
    ["<b>Look-ahead bias</b>",
     "One careless line — a scaler fitted on the full set, a rolling window that includes the current "
     "bar — produces a Sharpe of 4 that loses money live. The failure is silent.",
     "Walk-forward CV with the scaler fitted inside the fold; strict <font face='Courier'>&lt;</font> on "
     "the backtest boundary; stop-loss exits on <font face='Courier'>t+1</font>."],
    ["<b>Costs</b>",
     "An Indian round trip pays STT, stamp duty, brokerage, exchange charges, SEBI fees, GST on fees, "
     "and size-dependent slippage.",
     "All seven priced explicitly. Measured drag: 1.68%/yr — 19% of the gross edge."],
])),

("h2", "1.2 Why “predict the price” fails"),
("p", "A model predicting HDFC Bank +4% next month, in a month NIFTY did +3.6%, has predicted nothing. "
      "Worse, it scores well on the metrics people reach for."),
("code", """  Model predicts   HDFCBANK  +4.0%      Reality  +3.1%
  Naive scoring    |error| 0.9%, direction correct   ->  "great model"

  Same window      NIFTY     +3.6%
  Relative reality 3.1 - 3.6 = -0.5%   it UNDERPERFORMED
  Model implied    4.0 - 3.6 = +0.4%   it said OUTPERFORM

  On the only metric that decides whether to own it instead of the index,
  the model got the SIGN WRONG while scoring 0.9% absolute error."""),
("box", ("Cross-sectional alpha — the definition everything rests on",
         "<b>target = (compounded subsector return over the next N trading days) − (compounded NIFTY "
         "return over the identical N days)</b>, in percent.\n\n"
         "Positive means it beat the index. Negative means it lost to the index even if it rose. "
         "Because the benchmark is subtracted <i>within the same window</i>, market direction cancels "
         "and the model must learn relative behaviour. Side effect: the target is roughly zero-mean, "
         "which is why directional accuracy sits near 50% and IC is the headline metric.")),

("h2", "1.3 Why subsectors, not stocks"),
("alts", [
    ["Individual stocks",
     "Captures single-name opportunities; the largest opportunity set.",
     "One company's month is dominated by a CEO exit or a single order — idiosyncratic variance no macro "
     "model can explain. Stock-specific output is investment advice, which in India needs SEBI "
     "registration.",
     "Rejected"],
    ["<b>Subsectors</b> (28)",
     "Aggregation is a free noise filter: seven private banks averaged are driven by rate policy, which "
     "macro features can predict. Matches the causal mechanism. Maps to liquid sector ETFs. Stays "
     "research, not advice.",
     "Can never capture a single-stock opportunity or express “this bank beats that bank”.",
     "*Chosen"],
    ["Sectors only (7)",
     "Maximum noise reduction; fewest models to train.",
     "Too coarse — PSU Banks and NBFCs respond to rates very differently, and merging them averages the "
     "signal away.",
     "Rejected"],
    ["Factors (value, quality, size)",
     "The academic standard; well-researched and benchmarked.",
     "Needs fundamental data — balance sheets, earnings — which is not freely available for 130 NSE "
     "names.",
     "Blocked by the zero-cost constraint"],
]),

("h2", "1.4 The pipeline"),
("code", """   yfinance (127 tickers + 8 macro series)        Google News RSS
        |                                               |
        v  INGEST      data_loader.py                   v  SENTIMENT   sentiment_engine.py
   [ SQLite: daily_prices 306,746 rows | macro_data 3,781 rows ]   [ LLM score -1..+1 per sector ]
        |                                               |
        v  ATTRIBUTE   contribution_engine.py           |
   company return x index weight -> subsector -> sector -> reconciled to NIFTY
        |                                               |
        v  REGIME      macro_engine.py                  |
   VIX / FII / DII / FX / crude / rate  ->  score in [-1,+1] -> BULLISH|NEUTRAL|BEARISH
        |                                               |
        +-----------------------+-----------------------+
                                v  ALPHA        alpha_engine.py
        0.30*momentum + 0.15*meanrev + 0.15*vol + 0.20*macro + 0.20*sentiment
                                |   -> rank 28 subsectors, threshold at 0.40
                                v  FORECAST     ml_forecast_engine.py
        per subsector x {1M,3M,6M} : ensemble of {RF, Ridge, XGBoost, LightGBM}
        trained on CROSS-SECTIONAL ALPHA ; 12M compounded from 1M ; bull/base/bear
                                |
                                v  OPTIMISE     portfolio_engine.py
        score = (ret x confidence x alpha) / (1 + 0.7 x vol)
        -> SciPy SLSQP max-Sharpe -> caps: 20% name / 20% sector / 40% theme / 60% top-3
                                |
                                v  DE-RISK      risk_engine.py
        11 rules, monotonically non-increasing exposure, + NIFTY futures hedge
                                |
                                v
        outputs/marketos_daily_YYYY-MM-DD.json  ->  Flask API  ->  dashboard

   out of band:  backtest_engine.py  ->  backtest_cache  ->  the numbers in Part 9"""),
("p", "The recurring shape is <b>cheap wide net, then expensive precise judge</b>. All 28 subsectors get "
      "a cheap composite score; only those above threshold reach the ML forecaster; only positive "
      "expected returns reach the optimiser; only its output reaches the risk layer. Each stage costs "
      "more per item and sees fewer items."),

# ═══════════════════════════════════════════════════════════════════
("part", (2, "Market & mathematical concepts",
          "Thirteen concepts. Each one: what it is, why it is here, the arithmetic, and every alternative "
          "with the reason it was not chosen.")),

("h2", "2.1 Returns and compounding"),
("p", "<b>What.</b> A simple return is <font face='Courier'>r = P_t / P_t−1 − 1</font>. Multi-day returns "
      "compound, they do not add. <b>Why here.</b> Every aggregation over time uses "
      "<font face='Courier'>(1+r).prod() − 1</font>. Getting this wrong silently misstates every "
      "cumulative figure in the system."),
("code", """+50% then -50%:
  additive   50 - 50 = 0%      "flat"
  compounded 1.50 x 0.50 - 1 = -25%   you lost a quarter

That gap is VOLATILITY DRAG. It is the mathematical reason a lower-volatility
portfolio can beat a higher-return one over time, and the reason the risk
overlay's only power is to REDUCE exposure."""),
("alts", [
    ["<b>Simple returns</b>",
     "Portfolio weights combine linearly: a 60/40 book returns 0.6·r₁ + 0.4·r₂. Since the entire system "
     "is about weighting subsectors, this is the property that matters.",
     "Do not add across time; must be compounded. Skewed, not normally distributed.",
     "*Chosen"],
    ["Log returns <font face='Courier'>ln(P_t/P_t−1)</font>",
     "Add across time, symmetric, closer to normal — the academic default.",
     "Do not combine linearly across assets. A portfolio's log return is <i>not</i> the weighted average "
     "of component log returns, which breaks the core operation.",
     "Rejected"],
]),
("p", "<b>Deviation.</b> Feature engineering uses <font face='Courier'>rolling(20).sum()</font> rather "
      "than a compounded product. Over 20 days at sub-percent daily returns the difference is negligible, "
      "the sum is far cheaper across a 2,400 × 28 panel, and a sum is linear — which Ridge can represent "
      "exactly. <b>Targets</b>, where accuracy is scored, are always compounded."),

("h2", "2.2 Index construction and weighting"),
("p", "<b>What.</b> NIFTY 50 is free-float market-cap weighted: weight ∝ shares available to trade × "
      "price. <b>Why here.</b> Weights are the bridge from company returns to index contribution, and "
      "they are the input to attribution."),
("alts", [
    ["<b>Static weights in code</b>",
     "Zero cost, zero dependency, fully auditable, and stable — attribution does not shift under you "
     "because a weight was revised.",
     "Drifts from reality as prices move and as NSE rebalances semi-annually. The seven sector weights "
     "sum to 0.95, not 1.00.",
     "*Chosen — the drift is absorbed by the normaliser in §2.3"],
    ["Live free-float weights from NSE",
     "Exact attribution that reconciles to the index without rescaling.",
     "NSE's endpoint is unofficial, rate-limited, and blocks datacentre IPs. No SLA.",
     "Blocked"],
    ["Equal weight",
     "Trivially simple, no weight data needed at all.",
     "Attribution becomes meaningless — it would claim a ₹5,000 Cr company moved the index as much as "
     "Reliance.",
     "Rejected"],
    ["Market cap from <font face='Courier'>yfinance</font>",
     "Free and roughly correct.",
     "Full market cap, not free float. Promoter holdings in Indian companies are large and vary "
     "enormously, so the error is material and unpredictable.",
     "Rejected"],
]),

("h2", "2.3 Attribution and normalisation"),
("p", "<b>What.</b> Each company's contribution to the index move is its return times its weight; "
      "contributions sum to the index return. <b>Why here.</b> This is the only layer in the system that "
      "is arithmetically exact rather than statistical — you can verify it with a calculator, which "
      "retires a whole class of silent data bugs."),
("code", """contribution_pct = daily_return_pct x weight_pct / 100

  HDFC Bank   13.1% weight  +1.20%  ->  +0.1572% of the index
  ICICI Bank   7.8%         +0.90%  ->  +0.0702%
  Reliance     9.0%         -1.50%  ->  -0.1350%
  TCS          4.6%         +0.40%  ->  +0.0184%
                                        ----------
                                        +0.1108%

Read aloud: "the index is up 0.11% because of HDFC Bank, and Reliance
took two thirds of it back." """),
("p", "Because the tracked universe is not the exact index, raw contributions do not sum to the true "
      "NIFTY return. The engine rescales by "
      "<font face='Courier'>scale = nifty_actual / sum_of_raw</font>."),
("warn", ("The flat-day scale explosion",
          "When sectors nearly cancel, the denominator approaches zero and the scale factor explodes. "
          "Observed: raw contributions summed to 0.008% on a day NIFTY moved +0.141% — a scale of "
          "<b>17.6×</b>, printing sector returns of −44% on a day nothing moved 1%.\n\n"
          "Three guards now: (1) either side under 0.0001% → do not scale; (2) <b>negative</b> scale → "
          "return raw, because multiplying by a negative inverts every sector's direction and turns "
          "gainers into losers; (3) |scale| &gt; 5 → return raw and flag LOW confidence. "
          "<b>Prefer an honestly imprecise number over a precisely wrong one.</b>")),

("h2", "2.4 Volatility and annualisation"),
("p", "<b>What.</b> Standard deviation of returns, the standard risk proxy. Annualised by ×√252, because "
      "variance scales linearly with time and standard deviation is its square root. <b>Why here.</b> "
      "Volatility drives position sizing, the risk overlay, and the covariance matrix."),
("code", """daily sigma 1.2%  ->  annualised 0.012 x sqrt(252) = 0.012 x 15.87 = 19.0%

Reading: ~2 years in 3 the annual return lands within +/-19% of its mean;
~1 year in 20 it lands more than 38% away."""),
("alts", [
    ["Rolling 20-day std",
     "Simple, responsive, one line.",
     "A large move enters the window, vol jumps, then exactly 20 days later it <i>leaves</i> and vol "
     "drops off a cliff — on a day nothing happened. Weights then swing on the calendar, not the market.",
     "Used, but only at 30% weight"],
    ["<b>EWM std, blended 70/30 with rolling</b>",
     "Old observations fade instead of dropping out, so no cliff. The 30% rolling component retains "
     "responsiveness to genuine regime shifts.",
     "The 70/30 split is a judgement call, not an optimised parameter.",
     "*Chosen"],
    ["GARCH(1,1)",
     "Models volatility clustering explicitly; the academic standard.",
     "A separate fitted model per series, plus a dependency, for a second-order improvement.",
     "Roadmap"],
    ["Realised vol from intraday bars",
     "Substantially more accurate than any close-to-close estimator.",
     "Needs tick data the project does not have.",
     "Blocked"],
    ["Implied vol (India VIX)",
     "Forward-looking rather than backward-looking.",
     "Only exists at the index level. There is no per-subsector option market in India.",
     "Used as a macro input, not for sizing"],
]),

("h2", "2.5 Momentum"),
("p", "<b>What.</b> Recent winners keep winning over 3–12 months — one of the most robust anomalies in "
      "empirical finance. <b>Why here.</b> It carries the largest weight (0.30) in the alpha composite "
      "and is the sole selection signal in the backtest's momentum filter."),
("code", """momentum = 0.6 x (20-day compounded return) + 0.4 x (60-day compounded return)
           weighted toward the recent window: 1 month matters more than 3"""),
("alts", [
    ["<b>Time-series momentum, then cross-sectional normalisation</b>",
     "Raw signal is interpretable in percent; the min-max step then makes the final score a peer ranking, "
     "which is what allocation needs.",
     "Two steps where one might do. The normalisation is doing more work than it appears to (§2.7).",
     "*Chosen"],
    ["Pure cross-sectional momentum (rank against peers directly)",
     "One step; the standard construction in academic factor work.",
     "Loses the raw magnitude, which the daily narrative quotes.",
     "Effectively equivalent after normalisation"],
    ["12-1 momentum (12 months, skipping the last)",
     "The canonical academic definition. Skipping the last month avoids short-term reversal contamination.",
     "Too slow for a system that rebalances monthly on sectors; by the time it turns, the move is done.",
     "Rejected"],
    ["Risk-adjusted momentum (return / vol)",
     "Prefers steady trends over violent ones.",
     "Partly redundant here — volatility already enters via the scoring denominator and inverse-vol "
     "sizing.",
     "Rejected as double-counting"],
]),

("h2", "2.6 Mean reversion"),
("p", "<b>What.</b> Prices that move too far from trend snap back. Dominates over days-to-weeks and again "
      "over 3–5 years; momentum dominates in between. <b>Why here.</b> It contradicts momentum on "
      "purpose."),
("code", """mean_reversion = (MA50 - current_level) / MA50 x 100
                 POSITIVE when price is BELOW its 50-day average"""),
("box", ("Two opposing signals in one composite is a crude regime filter",
         "The composite rewards a subsector trending up (high momentum) that has pulled back to its "
         "50-day average (positive mean reversion) — a healthy uptrend on a dip. It penalises one that "
         "has gone parabolic: strong momentum, but deeply negative mean-reversion score because it sits "
         "far above trend. The disagreement is the information.")),
("alts", [
    ["<b>Distance from a 50-day moving average</b>",
     "Unbounded, so magnitude survives; trivially interpretable; no parameters beyond the window.",
     "Unbounded also means one extreme name can dominate before normalisation.",
     "*Chosen"],
    ["RSI (14)",
     "Bounded 0–100, so no outlier can dominate. Universally understood.",
     "Bounded means it saturates — an RSI of 5 and an RSI of 15 look nearly the same when they are not.",
     "Viable drop-in"],
    ["Bollinger band position",
     "Volatility-adjusted: distance from trend measured in standard deviations, not percent.",
     "Arguably the better construction; would need re-tuning of the composite weights.",
     "Roadmap"],
    ["Omit mean reversion",
     "One fewer weight to justify. Nothing in the measurement record proves it helps.",
     "Loses the parabolic-move penalty, which is its real job.",
     "Untested — flagged as an ablation gap in Part 9"],
]),

("h2", "2.7 Normalisation and composite scoring"),
("p", "<b>What.</b> Rescaling signals onto a common range so they can be summed. <b>Why here.</b> "
      "Momentum spans roughly −20 to +30, mean reversion −15 to +15, the vol ratio −50 to +80. Adding "
      "raw values lets whichever signal happens to be widest that day dominate the composite."),
("code", """normalised = (x - min(x)) / (max(x) - min(x))

Momentum across 5 subsectors, one day:
  raw:  IT +18.2 | Auto +9.6 | Banks +4.1 | Pharma -2.0 | Cement -6.3
  min -6.3, max +18.2, range 24.5

  IT      1.000     <- best today, BY CONSTRUCTION
  Auto    0.649
  Banks   0.424
  Pharma  0.176
  Cement  0.000     <- worst today, BY CONSTRUCTION"""),
("box", ("The property that is both the power and the trap",
         "Min-max is <b>purely relative</b>. The best subsector always scores 1.0 and the worst always "
         "0.0 — on a day everything crashed and on a day everything rallied. The composite answers "
         "“which is best today?” and can never answer “is anything worth owning?”\n\n"
         "That is exactly why macro alignment and sentiment are <b>excluded</b> from normalisation and "
         "simply divided by 100. Those two carry absolute information: a bearish regime is bearish for "
         "everyone. Normalising a flat array of 65.0 maps it all to 0.5 and discards the fact that "
         "conditions were mediocre for all of them. The system's only absolute floor comes from those "
         "two unnormalised terms plus the 0.40 exclusion threshold.")),
("alts", [
    ["<b>Min-max, on price signals only</b>",
     "Bounded output, trivial to combine with fixed weights, robust to differing units.",
     "Purely relative; sensitive to a single outlier, which compresses everything else toward the middle.",
     "*Chosen"],
    ["Z-score <font face='Courier'>(x−μ)/σ</font>",
     "Preserves outlier magnitude instead of compressing it; what most institutional factor models use.",
     "Unbounded, so a single extreme can still swamp the composite unless you also winsorise.",
     "Used in one place — rescaling opportunity scores"],
    ["Rank transform",
     "Maximally robust — one absurd outlier changes nothing.",
     "Discards all magnitude. The gap between rank 1 and rank 2 becomes identical to the gap between "
     "rank 27 and 28.",
     "Rejected"],
    ["Winsorise, then z-score",
     "The standard institutional compromise: outliers clipped, magnitude retained.",
     "One more parameter (the clip percentile) to justify.",
     "Recommended upgrade"],
]),

("h2", "2.8 Covariance, correlation, beta"),
("p", "<b>What.</b> Covariance measures co-movement; correlation is covariance normalised to [−1, +1]; "
      "beta is a subsector's sensitivity to the index. <b>Why here.</b> An asset's real risk is not its "
      "own volatility but its contribution to <i>portfolio</i> volatility — and that depends entirely on "
      "how it moves with everything else."),
("code", """Two assets:  sigma_p^2 = w1^2 s1^2 + w2^2 s2^2 + 2 w1 w2 rho s1 s2
                                            ^^^^^^^^^^^^^^^^^^ diversification term

Both 25% vol, equal weights:
  rho = +1.0  ->  25.0%   identical twins, no diversification at all
  rho = +0.5  ->  21.7%
  rho =  0.0  ->  17.7%   sigma / sqrt(2), the classic result
  rho = -0.5  ->  12.5%   half the risk, same expected return"""),
("alts", [
    ["<b>Sample covariance, 252-day window, annualised</b>",
     "No assumptions, no dependencies, directly interpretable.",
     "Noisy: 28 assets need 406 pairwise estimates from 252 observations. Known to produce unstable "
     "optimiser weights.",
     "*Chosen"],
    ["Ledoit–Wolf shrinkage",
     "Shrinks the sample matrix toward a structured target; provably lower estimation error and much "
     "more stable weights. One import from scikit-learn.",
     "One more concept to explain; slightly less transparent.",
     "Tier-3 roadmap — cheap, clear win"],
    ["Factor-model covariance",
     "Estimates far fewer parameters; the institutional standard (Barra, Axioma).",
     "Requires a factor model, which requires fundamental data.",
     "Blocked"],
    ["Ignore covariance, use inverse-vol only",
     "Needs no estimation at all; empirically hard to beat.",
     "Cannot tell that Banking and NBFCs are the same bet.",
     "Kept as the fallback path"],
]),

("h2", "2.9 Drawdown"),
("p", "<b>What.</b> Decline from a running peak. Max drawdown is the worst such decline. <b>Why here.</b> "
      "It is the number that determines whether an investor holds on — and therefore whether the "
      "strategy's long-run return is ever actually realised. A strategy nobody can sit through has no "
      "return."),
("code", """rolling_max = cumulative.cummax()
drawdown    = (cumulative - rolling_max) / rolling_max

Measured, 5-year (quarterly rebalance, n=15):  -5.83%
Measured, 10-year (quarterly rebalance, n=35): -21.61%"""),

("h2", "2.10 The risk-free rate"),
("p", "<b>What.</b> The return available with no risk; the baseline every excess return is measured "
      "against. <b>Why here.</b> It sets the bar in the Sharpe ratio and in the MVO objective. Get it "
      "wrong and every risk-adjusted number is wrong."),
("alts", [
    ["<b>Indian 10-year G-Sec, ~6.5–7%</b>",
     "The correct baseline for a rupee-denominated Indian equity portfolio. An Indian investor's genuine "
     "no-risk alternative.",
     "Hard-coded, so it drifts as yields move.",
     "*Chosen"],
    ["US Treasury rate (~4%)",
     "The default in most tutorials and libraries.",
     "Wrong currency and wrong country. Would inflate every Sharpe ratio by roughly 0.2–0.3 — a very "
     "common and very flattering error.",
     "Rejected"],
    ["Zero",
     "Simplest; common in academic papers that report raw Sharpe.",
     "Inflates Sharpe further and makes the number incomparable to any published Indian figure.",
     "Rejected"],
]),
("warn", ("An internal inconsistency",
          "<font face='Courier'>portfolio_engine.RISK_FREE_RATE = 0.065</font>, but the MVO objective "
          "hard-codes <font face='Courier'>risk_free_rate = 0.07</font> a few lines lower, and "
          "<font face='Courier'>backtest_engine.RISK_FREE_ANNUAL = 0.065</font>. Three call sites, two "
          "values. The 50bp difference barely moves the optimiser, but it violates the project's own "
          "single-source-of-truth rule and belongs in one constant.")),

("h2", "2.11 Performance metrics"),
("table", ([0.17, 0.38, 0.45], [
    ["Metric", "Formula", "What it hides"],
    ["<b>Sharpe</b>", "(mean excess return / std of returns) × √periods per year",
     "Penalises upside volatility as much as downside. Above 2.0 in a backtest usually means a bug."],
    ["<b>Information ratio</b>", "(mean alpha / std of alpha) × √periods per year",
     "The allocator's metric — is the outperformance consistent or one lucky quarter? Says nothing about "
     "absolute risk."],
    ["<b>Max drawdown</b>", "min of (cumulative / running max − 1)",
     "A single number from a single path. Says nothing about how often you get near it."],
    ["<b>Win rate</b>", "fraction of periods positive",
     "Easily gamed. You can win 80% of months and still lose money if the other 20% are catastrophic. "
     "Always read next to max drawdown."],
])),
("box", ("Worked — Sharpe from the shipped 5-year backtest",
         "15 periods of 63 trading days (quarterly); periods per year = 252/63 = 4.\n\n"
         "Risk-free per period = 1.065<sup>63/252</sup> − 1 ≈ 1.6%. Portfolio annualised 19.11% vs NIFTY "
         "13.58% → net alpha +5.53%. Sharpe on the period-return series comes out to <b>0.864</b>, "
         "information ratio (alpha mean / alpha std) <b>0.601</b>.\n\n"
         "<b>The honest statement is “Sharpe ≈0.86 on 15 observations”</b>, since the standard error of a "
         "Sharpe estimate is roughly 1/√n — with n=15 that is a wide band. The same strategy measured over "
         "10 years (n=35, the largest available sample) comes in far weaker: Sharpe 0.375, IR 0.021, net "
         "alpha +0.02% — essentially flat. See §9.2–9.4 for the full window-instability discussion; the "
         "honest headline is the 10-year number, not the flattering 5-year one.")),
("alts", [
    ["<b>Sharpe + IR + max DD + win rate together</b>",
     "Four metrics that fail differently; reading them jointly is what catches a flattering single "
     "number.",
     "Four numbers to explain rather than one.",
     "*Chosen"],
    ["Sortino",
     "Penalises only downside deviation, which is closer to what investors actually dislike.",
     "Needs a target-return choice; less comparable to published figures.",
     "Worth adding"],
    ["Calmar (return / max DD)",
     "Directly expresses the trade-off a drawdown-averse investor cares about.",
     "Extremely unstable at small sample sizes — one bad period rewrites it.",
     "Rejected at n=21"],
]),

("h2", "2.12 The Indian macro factor set"),
("p", "<b>What.</b> Six drivers with defensible transmission mechanisms to Indian equities. <b>Why "
      "here.</b> They are the regime classifier's inputs and a large share of the ML feature set. Every "
      "one was selected because you can state <i>how</i> it reaches earnings, not because it correlated."),
("table", ([0.17, 0.10, 0.45, 0.28], [
    ["Factor", "Weight", "Transmission mechanism", "Source"],
    ["India VIX", "0.25", "Option-implied fear. Rising VIX → FII de-risking → large-cap selling. The most "
     "real-time signal available.", "yfinance <font face='Courier'>^INDIAVIX</font>"],
    ["NIFTY momentum", "0.25*", "Actual price action. *Declared but never added to the composite — see "
     "the warning in §2.13.", "yfinance <font face='Courier'>^NSEI</font>"],
    ["FII flows", "0.15", "Foreign institutions are the marginal buyer in Indian large caps; their "
     "selling moves the index directly.", "<b>Synthetic proxy</b>"],
    ["DII flows", "0.10", "Domestic mutual-fund SIP inflows are the structural counterweight to FII "
     "selling.", "<b>Synthetic proxy</b>"],
    ["USD/INR", "0.10", "Depreciation signals macro stress and imported inflation; helps IT and Pharma "
     "exporters, hurts the import bill.", "yfinance <font face='Courier'>INR=X</font>"],
    ["Brent crude", "0.10", "India imports ~85% of its crude. Higher crude widens the current account "
     "deficit and feeds inflation.", "yfinance <font face='Courier'>BZ=F</font>"],
    ["Repo rate", "0.05", "Bank net interest margins, real-estate project IRRs, auto EMIs. Low weight "
     "because it changes about six times a year.", "Manual constant"],
])),

("h2", "2.13 Regime classification"),
("p", "<b>What.</b> Compressing the macro environment into one score in [−1, +1] and a label. <b>Why "
      "here.</b> It gates the alpha threshold, the sector cap, the hedge ratio and the exposure "
      "multiplier — this is where macro actually changes an allocation."),
("p", "<b>Design principle.</b> Each signal is normalised to [−1, +1] <i>independently</i> first, then "
      "combined with fixed weights. A signal in unfamiliar units (crore of flow) then cannot dominate one "
      "in familiar units (VIX points)."),
("code", """Worked, from outputs/marketos_daily_2026-08-13.json:

  VIX 11.42 (deep calm)      +1.0  x 0.25 = +0.250
  NIFTY -0.16% (flat)         0.0  x 0.25 =  0.000
  FII -325 Cr (near flat)     0.0  x 0.15 =  0.000
  DII +880 Cr (near flat)     0.0  x 0.10 =  0.000
  USD/INR +0.05% (stable)     0.0  x 0.10 =  0.000
  Brent -2.02% (falling)     +1.0  x 0.10 = +0.100
  Repo held at 5.25%          0.0  x 0.05 =  0.000
                                             ------
  composite                                  +0.350

  > +0.10  ->  BULLISH, confidence WEAK (|0.35| < 0.40), risk LOW_MEDIUM

That is exactly what the shipped JSON records. Re-derivable by hand."""),
("box", ("The bias that had to be engineered out",
         "The original classifier scored RATE_HOLD as <b>+1</b>. The RBI holds rates on essentially every "
         "trading day, so the composite carried a permanent positive term and the system printed BULLISH "
         "roughly three days in four. Nothing crashed; every individual number looked reasonable. It was "
         "found by plotting the label distribution and noticing it did not look like a market.\n\n"
         "Fix: HOLD scores <b>0.0</b>, and only actual policy <i>moves</i> score. General lesson: "
         "<b>a constant signal carries no information, and encoding it as positive is a bug, not "
         "conservatism.</b> The same check later exposed <font face='Courier'>rate_momentum</font> as "
         "identically zero.")),
("warn", ("Two defects in the shipped classifier",
          "<b>(1) The NIFTY term is computed but never summed.</b> "
          "<font face='Courier'>WEIGHTS[\"nifty\"] = 0.25</font> is declared and "
          "<font face='Courier'>nifty_score</font> is computed across five branches, but the "
          "<font face='Courier'>regime_score</font> expression adds vix, fii, dii, fx, crude and rate "
          "only. Effective weights total <b>0.75</b>, so every stored regime score is compressed toward "
          "zero by ~25%. The “NIFTY fell more than 1% → force NEUTRAL” override is currently the only "
          "path by which price action reaches the label.\n\n"
          "<b>(2) Docstring and code disagree.</b> The docstring says VIX 30 / FII 25 / FX 15 / crude 15 "
          "/ rate 15 with thresholds ±0.50. The code implements 25/15/10/10/05 (+DII 10, +dead NIFTY 25) "
          "with thresholds +0.10 and −0.20. Trust the arithmetic, not the prose above it.")),
("alts", [
    ["<b>Weighted threshold rules</b>",
     "Fully explainable — you can hand-derive any label from seven numbers. No training data needed. "
     "Deterministic and instantly auditable.",
     "Thresholds are hand-set judgement calls. No statistical basis for the cutoffs. Brittle if the "
     "distribution of a signal shifts.",
     "*Chosen — explainability outweighs sophistication for a gating signal"],
    ["Hidden Markov model",
     "Learns regimes and transition probabilities from data; gives a probability rather than a hard "
     "label.",
     "Regimes come out unlabelled — you still have to decide which discovered state means “bearish”. "
     "Much harder to explain to a user.",
     "Roadmap"],
    ["k-means / Gaussian mixture clustering",
     "Data-driven and simple to fit.",
     "Ignores time ordering entirely, which for regimes is the whole point.",
     "Rejected"],
    ["A supervised classifier on future returns",
     "Directly optimises the thing you care about.",
     "Circular — you would be predicting returns to gate a return predictor, and it needs its own "
     "walk-forward validation.",
     "Rejected"],
]),
]
