# bible_content_b.py
# MarketOS Build Bible v2 — Parts 3, 4, 5.

BLOCKS = [

# ═══════════════════════════════════════════════════════════════════
("part", (3, "Machine-learning concepts",
          "Ten concepts governing how the forecast layer is trained and evaluated. Same template: what, "
          "why here, worked example, alternatives.")),

("h2", "3.1 Supervised learning for forward returns"),
("p", "<b>What.</b> Learning a mapping from many (features, answer) pairs. Here: one row per (subsector, "
      "trading day); inputs are ~50 engineered features; the answer is the cross-sectional alpha over the "
      "next 21/63/126 trading days (§1.2)."),
("code", """One row, conceptually:
  DATE 2023-04-17, subsector = "IT Services"
  FEATURES  ret_1d, ret_5d, ret_20d, volatility_20d, momentum_60d, skew_20d,
            repo_rate, india_vix, brent_crude, fii_net_crore, dii_net_crore,
            usdinr_chg, vix_chg, nifty_5d_ret, net_liquidity, vix_regime,
            vix_percentile, crude_x_fx, rate_x_vix, nasdaq_corr_30d, ... (+lags)
  TARGET    +2.4%   (IT beat NIFTY by 2.4 points over the following quarter)"""),
("alts", [
    ["<b>Tabular supervised learning</b> (RF / Ridge / boosters)",
     "Handles a few thousand noisy rows per subsector without overfitting catastrophically; fast to "
     "train; every model in the tournament is explainable via feature importance or coefficients.",
     "Cannot model sequence — each row is independent, so genuine multi-day dynamics are only captured "
     "through the lag features you hand-engineer.",
     "*Chosen"],
    ["LSTM / temporal CNN",
     "Learns sequence structure directly, no manual lag features.",
     "With a few thousand rows per subsector and this signal-to-noise ratio, it fits the noise "
     "beautifully. Complexity is added only when a measured lift justifies it — none has been measured.",
     "Rejected, explicitly, in code comments"],
    ["Transformer / attention model",
     "State of the art on large sequence datasets.",
     "Needs orders of magnitude more data than 2,400 rows per subsector provides.",
     "Rejected"],
    ["Classical time-series (ARIMA/VAR)",
     "Well-understood inference, confidence intervals for free.",
     "Poor fit for a cross-sectional problem with dozens of exogenous macro drivers.",
     "Rejected"],
]),

("h2", "3.2 Feature engineering: lags, interactions, regime encodings"),
("p", "<b>Why here.</b> Linear models cannot discover a product term or a delayed effect on their own — "
      "you must hand it to them; tree models can, but only with enough data to find it reliably."),
("table", ([0.18, 0.38, 0.44], [
    ["Technique", "Example", "Reasoning"],
    ["Lags", "<font face='Courier'>brent_crude_chg_lag1</font>, "
     "<font face='Courier'>_lag5</font>", "Markets react with delay — a crude spike takes days to "
     "propagate into refiner margins. A lag lets the model find the delay rather than assuming it away."],
    ["Interactions", "<font face='Courier'>crude_x_fx</font>",
     "Crude rising is bad for India; crude rising <i>while</i> the rupee weakens is much worse, because "
     "the import bill is paid in dollars."],
    ["Regime encodings", "<font face='Courier'>vix_regime</font>, "
     "<font face='Courier'>vix_percentile</font>", "VIX at 18 means something different in a year that "
     "ranged 10–14 than one that ranged 16–30; the percentile captures that, the raw level does not."],
    ["Deterministic identity hash", "<font face='Courier'>sector_hash</font> via MD5",
     "Python's built-in <font face='Courier'>hash()</font> is randomised per process — a model trained "
     "in one run would see different identity features at inference in the next. A one-line bug that "
     "would be nearly impossible to diagnose from symptoms alone."],
])),
("warn", ("The inference-time approximation",
          "At training time, <font face='Courier'>fii_5d_mean</font> is a genuine rolling mean. At "
          "inference, <font face='Courier'>_build_inference_features()</font> approximates it as "
          "<font face='Courier'>fii_norm × 0.85</font>, and every lag similarly "
          "(<font face='Courier'>_lag1 ≈ x×0.9</font>, <font face='Courier'>_lag5 ≈ x×0.6</font>). This "
          "is a <b>train/serve skew</b> — the model was fitted on real statistics and predicts from "
          "synthetic stand-ins. Pragmatic, because the macro snapshot only carries today's values, but "
          "it is the prime suspect for the 2.5× optimism bias measured in Part 9. Fix is contained: "
          "compute inference features from <font face='Courier'>MacroData</font> the same way training "
          "does.")),

("h2", "3.3 Look-ahead bias and walk-forward validation"),
("p", "<b>What.</b> Standard k-fold CV, the default in every tutorial, <b>guarantees</b> look-ahead bias "
      "on time-series data — it puts future rows in the training fold."),
("code", """5-FOLD CV (WRONG)                        TIMESERIESSPLIT (correct)
  fold1 test[....]                          split1 train[1  ] test[2 ]
  fold2 test    [....]                      split2 train[1 2] test[3 ]
  fold3 test        [....]                  split3 train[1 2 3] test[4 ]
  ^ trains on 2024 to predict 2019.          ^ every test set is strictly after
    That is time travel.                       its training set."""),
("code", """for tr_idx, te_idx in tscv.split(X):
    Xtr = scaler.fit_transform(X.iloc[tr_idx])   # fit ONLY on training rows
    Xte = scaler.transform(X.iloc[te_idx])       # transform test with train stats"""),
("p", "Fitting the scaler on the whole dataset before splitting leaks the test period's mean into the "
      "training rows' standardisation — a faint but real signal about the future that inflates measured "
      "performance in a way that is invisible after the fact."),
("alts", [
    ["<b>TimeSeriesSplit, scaler fit inside the fold</b>",
     "No look-ahead by construction; one import from scikit-learn.",
     "Later folds train on more data than earlier ones, so fold-to-fold variance is uneven.",
     "*Chosen"],
    ["Fixed-window walk-forward (rolling, not expanding)",
     "Every fold trains on the same amount of data — more comparable variance across folds.",
     "Throws away history that might still be relevant, especially for slow macro relationships.",
     "Reasonable alternative, not used"],
    ["Purged k-fold with embargo",
     "The academically correct answer for overlapping targets — removes the specific leak below.",
     "More code, another parameter (embargo length) to justify.",
     "Not implemented — the acknowledged gap"],
]),
("warn", ("The gap that remains",
          "A row dated day <i>t</i> has a target spanning <i>t+1</i> to <i>t+63</i>. If the training fold "
          "ends at <i>t</i> and the test fold starts at <i>t+1</i>, the last 63 training rows have "
          "targets overlapping the test period — a subtler leak <font face='Courier'>TimeSeriesSplit</font> "
          "alone does not close. The standard remedy is <b>purge and embargo</b>: drop training rows "
          "whose target windows extend into the test set, plus a buffer. Not done here; the reported ICs "
          "in Part 9 are, if anything, mildly optimistic because of it.")),

("h2", "3.4 Evaluation metrics for a forecast"),
("table", ([0.16, 0.36, 0.48], [
    ["Metric", "Question answered", "When it misleads"],
    ["<b>R²</b>", "How much variance is explained?",
     "Routinely negative out of sample on financial data — a model can be useful with R² &lt; 0, because "
     "predicting near-zero is close to optimal in squared-error terms."],
    ["<b>Information coefficient</b> (Spearman)", "Does it rank correctly?",
     "Says nothing about magnitude. IC 0.15 with miscalibrated levels is still tradeable — this system's "
     "exact situation."],
    ["<b>Directional accuracy</b>", "How often is the sign right?",
     "Dominated by the base rate. “Always predict up” in a rising market scores well with zero skill."],
])),
("box", ("Worked — same model, three verdicts",
         "pred: +4.0, +2.5, +1.0, −0.5, −3.0  |  real: +1.6, +0.9, −0.2, +0.1, −1.1\n\n"
         "<b>Rank IC:</b> orders are 1,2,3,4,5 vs 1,2,4,3,5 — one adjacent swap. Spearman ρ = <b>0.90</b>. "
         "Excellent.\n"
         "<b>Directional accuracy:</b> (+,+)(+,+)(+,−)(−,+)(−,−) → 3/5 = <b>60%</b>, barely above a coin "
         "flip, and both errors are on the names closest to zero.\n"
         "<b>Magnitude:</b> predicted +4.0 where reality gave +1.6 — about 2.5× too loud.\n\n"
         "The verdict: use it to <i>rank</i> and size, never to promise a return.")),
("alts", [
    ["<b>Rank IC as the headline metric</b>",
     "Matches how the number is actually used — the portfolio engine ranks and sizes, it does not spend "
     "the raw prediction.",
     "Non-technical readers expect accuracy or R² and have to be taught IC.",
     "*Chosen"],
    ["R² as headline", "Familiar to anyone with a stats background.",
     "Routinely and misleadingly negative on this kind of data; would read as total failure when the "
     "model is doing its job.",
     "Rejected"],
    ["Directional accuracy as headline",
     "Intuitive — “right 65% of the time”.",
     "Inflated by the base rate in a trending sample; the 70.1% at 6M sits next to a mean realised return "
     "of +9.84%, which is most of the story.",
     "Reported, but caveated"],
]),
("warn", ("A naming trap in the codebase",
          "<font face='Courier'>_walk_forward_cv()</font> returns "
          "<font face='Courier'>(mean Spearman IC, mean directional accuracy)</font>. The caller unpacks "
          "the first into a variable named <font face='Courier'>r2</font> and writes it to "
          "<font face='Courier'>model_versions.r_squared</font>. <b>Nothing in this system has ever "
          "computed an R².</b> The substance is right — IC is the more useful metric — only the label is "
          "wrong. Say <i>information coefficient</i>, not R², when you quote it.")),

("h2", "3.5 Ensembling"),
("table", ([0.15, 0.42, 0.43], [
    ["Model", "Mechanism", "Why it is a candidate"],
    ["<b>Ridge</b>", "Linear regression + L2 penalty, shrinking coefficients toward zero.",
     "Cannot overfit badly; extrapolates sensibly. Wins <b>41 of 175</b> shipped models outright — real "
     "evidence the signal is often genuinely weak."],
    ["<b>Random forest</b>", "Many trees on bootstrap samples + random feature subsets, averaged.",
     "Captures non-linearity without being told about it. Constrained to "
     "<font face='Courier'>max_depth=5</font>, <font face='Courier'>min_samples_leaf≥10</font> "
     "specifically to stop memorising noise."],
    ["<b>XGBoost</b>", "Sequential boosting on residuals, L1/L2 regularised.",
     "Usually the strongest tabular learner. Optional import — the system runs without it."],
    ["<b>LightGBM</b>", "Leaf-wise boosting with histogram binning.",
     "Much faster than XGBoost on wide feature sets. Also optional."],
])),
("p", "The tournament scores all available candidates by walk-forward IC, then averages the top three in "
      "a <font face='Courier'>VotingRegressor</font>. If the best IC is worse than −0.05, the result is "
      "discarded for the Ridge baseline — a model with reliably negative rank correlation is actively "
      "harmful."),
("alts", [
    ["<b>Top-3 tournament ensemble, Ridge floor</b>",
     "Averaging models with partly-uncorrelated errors divides variance while leaving bias unchanged — "
     "the classic bias-variance argument for ensembling. Ridge winning 23% of slots is itself evidence "
     "against overfitting.",
     "More expensive to train (4 candidates × 5-fold CV per horizon per subsector) and to explain.",
     "*Chosen"],
    ["Single best model by CV score",
     "Simpler, half the training cost, one thing to explain.",
     "Loses the variance-reduction benefit of averaging; more sensitive to which fold happened to favour "
     "which model.",
     "Rejected"],
    ["Stacking (meta-learner on base predictions)",
     "Can outperform simple averaging if the meta-learner is well-regularised.",
     "Needs its own held-out set to avoid leakage, doubling the validation complexity for a modest gain "
     "at this sample size.",
     "Not worth it here"],
]),
("warn", ("A reporting flaw",
          "After the tournament, the chosen model is refit on <i>all</i> data and scored on that same "
          "data — <font face='Courier'>final_mae</font> and <font face='Courier'>final_dir</font> are "
          "in-sample and optimistic by construction, yet drive the user-facing confidence score. The "
          "trustworthy numbers are the cross-validated ones from the tournament, one step earlier in the "
          "same function.")),

("h2", "3.6 Shrinkage and output calibration"),
("p", "<b>Why here.</b> Raw regression output on noisy data has too much spread — extremes are "
      "extrapolations, not evidence — and a system that displays “+45% in six months” will be believed by "
      "somebody."),
("code", """soft_cap(val, cap):
    if |val| <= cap: return val
    scale = cap * 0.5
    return sign(val) * (cap + scale * ln(1 + (|val|-cap)/scale))

cap=25:  +20 -> +20.0 (untouched) | +30 -> +29.1 | +60 -> +42.3 | +120 -> +58.5
Order preserved: 30 < 60 < 120  maps to  29.1 < 42.3 < 58.5"""),
("alts", [
    ["<b>Flat shrinkage (×0.65) + soft cap + portfolio-level cap (18%)</b>",
     "Three independent, cheap, always-on layers of realism; the soft cap specifically preserves "
     "ranking, which is the one thing the model is measured to be good at.",
     "0.65 is a flat judgement call. The empirically-implied factor (Part 9) is closer to 0.40 — the "
     "shrinkage is not aggressive enough.",
     "*Chosen, under-tuned"],
    ["James–Stein shrinkage, calibrated per horizon",
     "Statistically principled — the shrinkage factor is derived from the ratio of signal to noise "
     "variance rather than guessed.",
     "Needs a reliable estimate of that ratio, which needs more out-of-sample history than currently "
     "logged in one place.",
     "Tier-2 roadmap"],
    ["Hard clip (the original design)",
     "Trivial to implement.",
     "Every high-conviction sector piles up at the identical ceiling, destroying the ranking — the "
     "model's only reliable output. Replaced for exactly this reason.",
     "Rejected, with the failure documented in code"],
]),

("h2", "3.7 Confidence scoring"),
("p", "<b>What.</b> A per-forecast number in [0,1] meant to say how much to trust this particular "
      "prediction. <b>Why here.</b> It directly scales the portfolio score "
      "(<font face='Courier'>exp_return × confidence × alpha_score</font>), so a miscalibrated confidence "
      "silently reweights the whole book."),
("code", """mae_norm  = clip(mae / 10.0, 0.10, 2.0)
conf_base = 1 / (1 + mae_norm)
dir_boost = clip((dir_acc - 0.50) * 0.8, -0.15, 0.20)
confidence = clip(conf_base + dir_boost, 0.20, 0.90)

MAE  3% -> conf 0.77 (high)   MAE 12% -> conf 0.45 (medium)   MAE 20% -> conf 0.33 (noisy)"""),
("alts", [
    ["<b>MAE-and-directional-accuracy-derived confidence</b>",
     "Ties confidence to the model's own measured error, per subsector and horizon — a genuinely "
     "noisier model is genuinely down-weighted.",
     "The MAE it is derived from is the in-sample figure from §3.5, so confidence inherits that "
     "optimism.",
     "*Chosen, inherits an upstream flaw"],
    ["Flat confidence per horizon (e.g. 1M=0.7, 6M=0.4)",
     "Simple, and at least honestly admits it is not measuring anything per-subsector.",
     "Ignores real, measured differences in how well individual subsector models perform.",
     "Rejected"],
    ["Prediction-interval width from quantile regression",
     "A statistically principled confidence interval, not a proxy.",
     "Needs quantile models trained in addition to the point-estimate models — roughly double the "
     "training cost.",
     "Roadmap"],
]),

("h2", "3.8 The horizon-synthesis problem (12M from 1M)"),
("p", "<b>What.</b> Only 1M, 3M and 6M models are trained. 12M is derived by inverting the 1M "
      "prediction into an implied daily rate and compounding it over 252 trading days."),
("code", """r_daily = sign(r) * (|1 + r/100|^(1/21) - 1)      # invert the 21-day prediction
r_12m   = ((1 + r_daily)^252 - 1) * 100                # compound to a year
guards: +/-0.436%/day  (~200%/-100% annual bound)"""),
("alts", [
    ["<b>Compound the 1M model</b>",
     "No extra training cost; reuses the model with the tightest, most reliable CV window.",
     "Assumes the current environment persists twelve months and amplifies the 1M model's error "
     "twelvefold. A documented, deliberate approximation.",
     "*Chosen"],
    ["Train a dedicated 12M model",
     "No compounding assumption; learns the horizon directly.",
     "126-day-ahead targets already need <font face='Courier'>MIN_ROWS=60</font> clean rows after "
     "dropping the last 126 — a 252-day-ahead target roughly halves the usable training set again, on "
     "data that already only spans ~2,400 rows per subsector.",
     "Rejected for data scarcity"],
    ["Compound the 6M model instead",
     "Half the compounding horizon (2× instead of 12×) — amplifies error far less.",
     "The system's actual choice was tried and rejected in a code comment: every sector hit the old hard "
     "cap and compounded to the identical 111.6%, destroying the ranking.",
     "Tried, rejected, documented"],
]),

("h2", "3.9 Scenario generation (bull / base / bear)"),
("code", """bull: VIX x0.75, repo -0.5, crude -3.0%, FII estimate +5000 Cr
bear: VIX x1.5,  repo +0.5, crude +5.0%, FII estimate -5000 Cr"""),
("p", "Bull and bear are not separate models — the <i>same</i> fitted model evaluated on perturbed macro "
      "inputs. This keeps the three scenarios internally consistent, and the bull-bear spread becomes a "
      "free diagnostic: a narrow spread means that subsector's model barely uses the macro features at "
      "all."),
("alts", [
    ["<b>Perturb inputs to one model</b>",
     "Internally consistent scenarios at zero extra training cost; spread is diagnostic.",
     "The perturbation magnitudes (VIX ×0.75, repo −0.5) are hand-picked, not derived from historical "
     "regime transitions.",
     "*Chosen"],
    ["Separate models trained on bull/bear sub-periods",
     "Each scenario reflects genuinely different historical dynamics, not just a shifted input.",
     "Splits an already-small dataset into three smaller ones.",
     "Rejected for data scarcity"],
    ["Monte Carlo over the macro feature distribution",
     "A genuine distribution of outcomes rather than three points.",
     "Needs a joint distribution model for seven correlated macro variables — real added complexity.",
     "Roadmap"],
]),

("h2", "3.10 Model versioning and reproducibility"),
("p", "<b>Why here.</b> A forecast without a recorded training window, sample count and metric is not "
      "reproducible — you cannot tell six months later whether it degraded."),
("code", """model_versions:  version, trained_date, training_start/end, subsector,
                 r_squared (actually IC), mae, directional_acc,
                 feature_weights (top 20), feature_names, n_samples, is_active"""),
("alts", [
    ["<b>A database table, one row per trained model, an <font face='Courier'>is_active</font> flag</b>",
     "Full audit trail; can compare a model against its own predecessor; supports rollback.",
     "Manual query to inspect — no dashboard for it yet.",
     "*Chosen"],
    ["MLflow / Weights &amp; Biases",
     "Purpose-built tooling: comparison UI, artifact storage, experiment tracking out of the box.",
     "Another service to run and operate for a project with one model registry and no team to share it "
     "with.",
     "Overkill at this scale"],
    ["No versioning — just overwrite the pickle",
     "Zero code.",
     "No way to know if today's model is better or worse than yesterday's, or to audit a bad forecast "
     "after the fact.",
     "Rejected"],
]),

# ═══════════════════════════════════════════════════════════════════
("part", (4, "Portfolio & risk concepts",
          "Eight concepts governing how forecasts become weights, and how weights are kept safe.")),

("h2", "4.1 Markowitz mean-variance optimisation"),
("p", "<b>What.</b> Choose weights maximising the Sharpe ratio for a given expected-return vector and "
      "covariance matrix. <b>Why here.</b> It is the textbook answer to “how much of each thing should I "
      "own”, and it is the layer where diversification becomes mathematical rather than a heuristic cap."),
("code", """maximise    (w.mu - r_f) / sqrt(w' Sigma w)
subject to  sum(w) = 1
            0 <= w_i <= 0.20
solver: scipy.optimize.minimize(method="SLSQP"), init = equal weights, r_f = 7%"""),
("alts", [
    ["<b>SciPy SLSQP</b>",
     "Handles the non-linear Sharpe objective with equality and inequality constraints directly, in a "
     "library already installed for everything else. No new dependency.",
     "A local optimiser — sensitive to the starting point, though equal-weight init is reliable for this "
     "convex-in-practice problem.",
     "*Chosen"],
    ["cvxpy, reformulated as a convex QP",
     "Provably global optimum; cleaner constraint syntax; industry-standard tooling.",
     "Requires reformulating max-Sharpe as a QP (the standard trick), which is one more layer of "
     "indirection to explain.",
     "Roadmap"],
    ["PyPortfolioOpt",
     "Packages Black-Litterman, shrinkage covariance, CLA and max-Sharpe in one library — the fastest "
     "path to a materially better optimiser.",
     "Writing it by hand was a deliberate learning choice, not a performance one — worth saying plainly "
     "rather than pretending otherwise.",
     "Obvious upgrade path, not taken"],
    ["Equal-risk-contribution / risk parity",
     "Needs no expected-return estimate at all — sidesteps MVO's well-known sensitivity to bad μ.",
     "Ignores the forecasts entirely, throwing away the one thing three engines were built to produce.",
     "Used only as the fallback"],
]),
("warn", ("MVO is an “error maximiser” — and this project's μ is uncertain",
          "MVO is famously sensitive to expected-return inputs: small changes in μ produce large changes "
          "in weights, systematically over-weighting whatever asset has the most over-estimated return. "
          "This project's μ comes from models with ~50% measured directional accuracy (Part 9) — a live "
          "concern, not a textbook footnote. Mitigations in place: the 20% box bound, the sector/theme "
          "caps applied after the solve, and the shrinkage on μ before it reaches the solver. The proper "
          "fix — Black-Litterman — is Tier 3.")),

("h2", "4.2 Constraints and concentration limits"),
("p", "<b>Why here.</b> An unconstrained max-Sharpe solution routinely puts 60% in one name — "
      "mathematically correct given the inputs, operationally indefensible given how uncertain those "
      "inputs are."),
("table", ([0.20, 0.18, 0.62], [
    ["Constraint", "Limit", "Reasoning"],
    ["Per-subsector", "20%", "A box bound inside the solver, so it is respected rather than imposed "
     "after the fact."],
    ["Per-sector", "20% base, 30% bullish, 15% bearish", "Dynamic — a bullish regime earns a wider cap. "
     "This is where the regime label actually changes an allocation."],
    ["Theme", "40%", "Banking, NBFCs and Real Estate are three sectors but one interest-rate bet; the "
     "sector cap alone would not notice that."],
    ["Top-3", "60%", "Backstop against three positions each sitting just under their individual caps."],
    ["Risk profile", "Conservative 10%/sector, 50% equity; Moderate 15%/75%",
     "Overrides the regime-derived caps whenever tighter, driven by the SEBI-style questionnaire."],
])),
("alts", [
    ["<b>Hard caps applied after the solve, plus a box bound inside it</b>",
     "Belt and braces — the solver respects the tightest individual constraint natively, and the "
     "portfolio-level caps catch combinations the solver has no visibility into (theme, top-3).",
     "Caps applied after the solve can leave weights that no longer sum to exactly 1 until renormalised, "
     "which happens after every single cap.",
     "*Chosen"],
    ["Soft penalty in the objective (e.g. quadratic penalty for exceeding a cap)",
     "One unified optimisation instead of solve-then-clip.",
     "Turns a hard business rule (“never exceed 20%”) into a tunable penalty weight that could in "
     "principle still be violated.",
     "Rejected — caps here are compliance-driven, not preferences"],
]),

("h2", "4.3 Correlation-based de-duplication"),
("p", "After the caps, any held pair correlated above 0.85 over 60 days has the lower-scoring member's "
      "weight cut by 0.75. Two subsectors correlated at 0.9 are substantially the same position; holding "
      "both is unrewarded concentration wearing a diversification costume."),
("alts", [
    ["<b>Pairwise correlation threshold + weight cut</b>",
     "Simple, fast, directly interpretable — “these two are basically one bet.”",
     "Pairwise checks miss three-way clusters where no single pair exceeds the threshold but all three "
     "together move as one.",
     "*Chosen"],
    ["Hierarchical clustering + cap per cluster",
     "Catches n-way clusters, not just pairs.",
     "Another parameter (linkage method, cluster count) and another layer to explain.",
     "Roadmap for &gt;28 subsectors"],
    ["PCA — cap exposure to the top principal component",
     "Directly caps the dominant common-risk-factor exposure, which is what correlation is really a "
     "proxy for.",
     "Principal components are not directly interpretable as “too much banking risk” to a reader.",
     "Rejected for explainability"],
]),

("h2", "4.4 The risk overlay — monotonic reduction"),
("p", "<b>Why here.</b> Eleven rules sit between the optimiser and the final weights. The structural "
      "property that matters more than any individual rule: <b>every rule multiplies by a factor strictly "
      "less than 1.0.</b> The overlay is a ratchet that only turns one way."),
("table", ([0.08, 0.42, 0.50], [
    ["Rule", "Trigger", "Action"],
    ["0", "VIX &gt;28 or STRONGLY_BEARISH", "Short NIFTY futures at 50% hedge (25% at VIX&gt;22/BEARISH) "
     "— the only rule that adds a position rather than trimming one."],
    ["1", "VIX &gt;20", "All weights ×0.75"],
    ["2", "Portfolio drawdown &gt;12%", "All weights ×0.75"],
    ["3 / 5", "Subsector 21d return &lt;−7%", "That weight ×0.70 (both rules fire together — see below)"],
    ["4", "10d vol &gt;1.5× 60d vol", "That weight ×0.85"],
    ["6", "Drawdown 6–12%", "High-vol names only ×0.85"],
    ["7", "Regime contains BEARISH", "All weights ×0.65"],
    ["8–11", "Sector/top-3 caps, severity link, diversification floor", "Structural backstops re-checked "
     "after every rule fires"],
])),
("box", ("Why stacking rules is a feature",
         "Rules 3 and 5 both fire on a −7% subsector, compounding to 0.70×0.70=0.49. That looks like "
         "double-counting; it is deliberate. A subsector triggering multiple independent risk conditions "
         "simultaneously is materially worse off than one triggering a single condition, and "
         "multiplicative stacking makes the response super-linear in the number of alarms — which is how "
         "correlated risk actually arrives.")),
("alts", [
    ["<b>Multiplicative rule stack, monotonically reducing</b>",
     "Cannot accidentally increase risk. Fully auditable — every application is logged as a "
     "human-readable string.",
     "Rules can compound in ways not individually intended (§4.4 box) — occasionally over-penalising a "
     "name that trips two related triggers.",
     "*Chosen"],
    ["A single composite risk score gating one exposure multiplier",
     "One number, easier to reason about at a glance.",
     "Loses the specific, auditable trail of which condition fired — much harder to explain a particular "
     "day's exposure cut.",
     "Rejected for auditability"],
    ["Value-at-risk (VaR) limit",
     "Industry-standard, single well-understood risk budget.",
     "Needs a return-distribution assumption (usually normal) that equities violate in the tails — "
     "exactly where VaR is asked to matter most.",
     "Not implemented"],
]),

("h2", "4.5 Position sizing"),
("code", """_score(row) = (exp_return x confidence x alpha_score) / (1 + 0.7 x volatility)
              soft *0.85 penalty if volatility > 30%"""),
("alts", [
    ["<b>Multiplicative score / (1+0.7·vol)</b>",
     "A large return the model is unsure about, or that the alpha engine dislikes, is penalised "
     "multiplicatively — not averaged away as it would be under a sum. Gentler than a straight "
     "return/vol ratio, which over-penalises moderate-vol names carrying most of the opportunity.",
     "The 0.7 coefficient and 30%/0.85 threshold are judgement calls with no statistical derivation.",
     "*Chosen"],
    ["Pure Sharpe-style score (return / vol)",
     "The textbook ratio; no extra coefficient to justify.",
     "Over-penalises moderate-volatility sectors, which in this universe carry most of the genuine "
     "opportunity.",
     "Rejected, by measurement described in the source comments"],
    ["Kelly criterion sizing",
     "Theoretically growth-optimal position sizing given a true edge and odds.",
     "Requires a much more confident, well-calibrated edge estimate than a ~0.14 IC signal provides; "
     "full Kelly on a noisy edge is known to be dangerously aggressive.",
     "Rejected — inputs are not reliable enough"],
]),

("h2", "4.6 Backtesting methodology"),
("code", """Every 30 trading days, standing at T:
  TRAIN  look back 126 days, STRICTLY before T
  TRADE  compare to previous weights, price the friction
  HOLD   30 days forward, 8% trailing stop per subsector
  SCORE  portfolio return vs NIFTY over the identical window
  STEP   T += 30"""),
("alts", [
    ["<b>Walk-forward, 30-day rebalance, 126-day lookback</b>",
     "Mirrors how the live system would actually operate; the boundary "
     "(<font face='Courier'>index &lt; as_of_date</font>) is the one line that makes the whole exercise "
     "honest.",
     "21 rebalances over 3 years is a small sample; standard errors are wide.",
     "*Chosen"],
    ["Daily rebalance backtest",
     "Far more observations, tighter statistics.",
     "The live system does not rebalance daily — this would test a strategy that was never actually "
     "built, and costs would dominate at that frequency.",
     "Rejected — does not match production"],
    ["Monte Carlo bootstrap of historical returns",
     "Generates far more scenario paths from the same history for tighter confidence intervals.",
     "Destroys the actual sequencing of macro regimes, which is exactly what the walk-forward structure "
     "is trying to respect.",
     "Roadmap, as a supplement not a replacement"],
]),
("warn", ("The backtest does not exercise the ML or alpha engines",
          "<font face='Courier'>_backtest_weights()</font> selects by trailing Sharpe "
          "(<font face='Courier'>mean(r)/vol(r)</font> over 126 days), filters negative 20-day momentum, "
          "and sizes by inverse volatility. It never calls "
          "<font face='Courier'>ml_forecast_engine</font>, <font face='Courier'>alpha_engine</font>, or "
          "sentiment. The measured +7.35% alpha (Part 9) is evidence for the <b>portfolio-construction "
          "methodology</b> — momentum/Sharpe rotation, inverse-vol sizing, turnover control, realistic "
          "costs — <b>not</b> for the ML layer, which was not in the loop. Closing this gap is roadmap "
          "item one.")),

("h2", "4.7 Transaction cost modelling"),
("table", ([0.30, 0.20, 0.50], [
    ["Component", "Rate", "Note"],
    ["STT", "0.10%", "Sell side only — the largest single component."],
    ["Stamp duty", "0.015%", "Buy side only."],
    ["Brokerage", "0.05%", "Both sides, discount-broker rate."],
    ["Exchange charge", "0.00345%", "Both sides."],
    ["SEBI fee", "0.0001%", "Both sides."],
    ["GST", "18% of fees", "Tax on the fees, not the trade value."],
    ["Slippage", "(0.02% + 10%×size)×size",
     "<b>Size-dependent</b> — quadratic in trade size, which is what separates a credible market-impact "
     "model from a decorative flat percentage."],
])),
("alts", [
    ["<b>Seven components priced individually, slippage quadratic in size</b>",
     "As close to a real Indian delivery trade as a backtest reasonably gets; the quadratic slippage "
     "term correctly makes large reallocations disproportionately expensive.",
     "Still a model, not the market — real slippage also depends on liquidity and time of day, neither "
     "modelled here.",
     "*Chosen"],
    ["Flat percentage (e.g. 0.1% per round trip)",
     "One line, common in amateur backtests.",
     "Fiction — ignores that a 20% reallocation costs far more per rupee than a 1% one. Most backtests "
     "that report implausibly high Sharpe use exactly this shortcut.",
     "Rejected, explicitly"],
    ["Historical bid-ask spread data",
     "The most accurate option, if available.",
     "Not free for 127 NSE names at daily granularity.",
     "Blocked by cost"],
]),

("h2", "4.8 Turnover control"),
("bul", [
    "<b>Rebalance skip</b> — total drift under 25% → skip entirely, zero cost.",
    "<b>Per-name filter</b> — weight change under 12% → keep the old weight, do not trade it.",
    "<b>Weight-jump limiter</b> — any weight that does change is clamped within ±10 points of its "
    "previous value.",
]),
("box", ("Worked — why this is worth more than it sounds",
         "A strategy that would otherwise turn over 40%/month: friction ≈ 0.4 × 0.20% ≈ 0.08%/month ≈ "
         "<b>0.96%/year</b> before slippage; with size-dependent slippage on the larger legs, close to "
         "the measured 1.68%/year cost drag. Against the measured 7.35% net alpha, that is roughly "
         "<b>19% of the gross edge</b> — a strategy is the signal minus the cost of acting on it, and any "
         "backtest that skips the second half is not a backtest.")),
("alts", [
    ["<b>Three-layer turnover control</b> (skip / per-name filter / jump limiter)",
     "Each layer catches a different failure mode: unnecessary whole-book churn, unnecessary single-name "
     "churn, and sudden large single-name jumps.",
     "Three thresholds (25% / 12% / 10%) to justify, none derived from an optimisation — all judgement "
     "calls.",
     "*Chosen"],
    ["A turnover penalty inside the optimiser objective",
     "Unified: the optimiser itself trades off expected Sharpe against expected cost.",
     "Needs the cost function differentiable and included in the SLSQP objective — a real rewrite of "
     "§4.1's solve.",
     "Roadmap"],
]),

# ═══════════════════════════════════════════════════════════════════
("part", (5, "Engineering & infrastructure concepts",
          "Nine concepts that have nothing to do with finance and everything to do with whether the "
          "numbers above can be trusted.")),

("h2", "5.1 Single source of truth"),
("p", "<b>What.</b> Exactly one function owns each fact the whole system depends on. <b>Why here.</b> "
      "Two modules deriving “today's date” or “NIFTY's return” independently will occasionally disagree, "
      "and the disagreement never raises an exception — it just quietly corrupts every downstream "
      "comparison."),
("alts", [
    ["<b>One module (<font face='Courier'>pipeline_utils.py</font>) owning date + benchmark</b>",
     "Structurally impossible for two engines to disagree about either fact; a fix or a guard added once "
     "protects every consumer.",
     "Every engine takes on an import dependency on this one module — a single point of failure if it "
     "breaks.",
     "*Chosen"],
    ["Each engine computes its own date/return, kept consistent by convention",
     "No shared dependency; engines are more independent.",
     "Consistency by convention is consistency until someone forgets — exactly the failure mode this "
     "project explicitly built around.",
     "Rejected"],
]),

("h2", "5.2 Idempotency"),
("p", "<b>What.</b> Running an operation twice has the same effect as running it once. <b>Why here.</b> "
      "Ingestion and table creation must be safely re-runnable after a crash without a manual cleanup "
      "step."),
("code", """import threading
_init_lock = threading.Lock()
_tables_created = False

def ensure_tables_exist():
    global _tables_created
    if _tables_created: return                      # fast path, unlocked
    with _init_lock:
        if not _tables_created:                      # re-check inside the lock
            Base.metadata.create_all(engine, checkfirst=True)
            _tables_created = True"""),
("p", "Double-checked locking: the unlocked read is the fast path taken on every call; the lock is "
      "entered only on the first. Under Flask, several worker threads import this module at once, and "
      "without the lock two can race into <font face='Courier'>create_all()</font>."),
("alts", [
    ["<b>Double-checked locking flag + <font face='Courier'>checkfirst=True</font></b>",
     "No engine can ever query a table that does not exist; safe under concurrent Flask workers; "
     "re-running any stage after a crash needs no manual step.",
     "One more piece of concurrency-aware code to get right — the exact class of bug that is easy to get "
     "subtly wrong.",
     "*Chosen"],
    ["A migration tool (Alembic)",
     "Handles schema evolution properly, not just table existence — the correct production answer.",
     "New dependency and workflow for a project whose schema barely changes.",
     "Roadmap if the schema starts changing often"],
    ["Run table creation once, manually, before deploy",
     "Zero runtime code.",
     "Breaks on the very first crash-and-restart, or on a fresh environment someone forgot to "
     "initialise.",
     "Rejected"],
]),

("h2", "5.3 Data-integrity circuit breakers"),
("p", "<font face='Courier'>data_loader.py</font> raises and halts the whole pipeline if the computed "
      "NIFTY daily move exceeds ±5%."),
("alts", [
    ["<b>Hard halt above a plausibility threshold</b>",
     "A bad tick or an unhandled split adjustment cannot silently flow into the macro table, the "
     "regime classifier, the training set, and every model trained on it. Refusing to run beats running "
     "on corrupt data, because the second failure is invisible.",
     "A genuine ≥5% NIFTY day (March 2020 happened) also halts and needs a human to confirm — a real "
     "operational cost on the rare day it is a true event, not a data error.",
     "*Chosen"],
    ["Log a warning and continue",
     "Never blocks the pipeline.",
     "The exact failure this guards against: a single corrupt row poisons every downstream model with no "
     "visible symptom for weeks.",
     "Rejected"],
    ["Cross-check against a second free data source",
     "Would distinguish a genuine crash from a bad tick automatically, without a human.",
     "No second free source with the same coverage exists; would add a dependency and its own failure "
     "modes.",
     "Not available at zero cost"],
]),

("h2", "5.4 Market-state awareness as a state machine"),
("p", "<b>Why here.</b> The NSE is closed weekends and ~15 holidays a year, and prices are not final "
      "until 15:30 IST. Naive re-runs on a Sunday compute a 0% return and feed it to the regime "
      "classifier as a real observation."),
("code", """get_market_status(date) ->
  is_trading_day, session_state, data_quality, engine_mode,
  should_rebalance, should_run_risk, should_run_alpha,   # gated
  should_run_forecast, should_run_macro                  # ALWAYS true - DB-driven"""),
("alts", [
    ["<b>A state machine returning per-engine boolean permissions</b>",
     "No engine ever has to ask “is it a weekday?” — it asks “am I permitted to run?”, and the answer "
     "already accounts for holidays, the intraday clock, and historical dates. Price-driven engines "
     "gate; database-driven ones do not, so a holiday still produces a labelled, degraded output rather "
     "than nothing.",
     "One more module every price-sensitive engine must import and check correctly.",
     "*Chosen"],
    ["Scattered <font face='Courier'>if weekday &lt; 5</font> checks per engine",
     "No shared dependency.",
     "The original design — every engine reimplementing the check slightly differently is exactly how "
     "one of them ends up wrong.",
     "Replaced, for this reason"],
]),

("h2", "5.5 Graceful degradation over hard failure"),
("code", """try:
    alpha_scores = compute_alpha_scores(...)
except Exception as e:
    print(f"  Alpha engine skipped: {e}")
    # alpha_scores stays {} - every downstream consumer handles the empty case"""),
("alts", [
    ["<b>Per-stage isolation, empty-safe downstream</b>",
     "A sentiment API outage costs only the sentiment component of the alpha score — not the day's "
     "attribution, regime, forecasts, or portfolio. Failures are visible in logs, not silent.",
     "Requires every downstream consumer to be written defensively against missing upstream data — easy "
     "to forget on a new stage.",
     "*Chosen"],
    ["Let any exception end the run",
     "Simpler code; a failure is unambiguous.",
     "A third-party rate limit silently produces zero output for the whole day, which is the worse "
     "failure because nobody notices until someone asks where today's numbers are.",
     "Rejected"],
]),

("h2", "5.6 Retrieval-augmented generation for the narrative"),
("p", "<b>What.</b> Before generating text, hand the model the numbers actually computed and instruct it "
      "to use only those. <b>Why here.</b> The daily narrative is the one user-facing surface where a "
      "language model could simply invent a plausible-sounding number."),
("alts", [
    ["<b>Anti-hallucination prefix + post-generation realism pass</b>",
     "A generated sentence containing a number not in the prefix is, by construction, a hallucination — "
     "detectable rather than merely plausible. Two independent layers: constrain the input, then "
     "sanitise the output.",
     "Does not guarantee the model uses the numbers <i>correctly</i>, only that it does not invent new "
     "ones — a subtler failure mode remains possible.",
     "*Chosen"],
    ["No constraint — free-text generation from a general prompt",
     "Simpler prompt, more natural-sounding prose.",
     "Nothing stops the model from stating a plausible but fabricated figure with full confidence.",
     "Rejected"],
    ["Template-filled sentences, no LLM at all",
     "Zero hallucination risk whatsoever; fully deterministic.",
     "Reads as robotic and cannot synthesise across several numbers the way a written narrative does.",
     "Rejected for readability"],
]),

("h2", "5.7 Caching with an explicit invalidation policy"),
("code", """cache_key = f"backtest_{lookback_years}yr_{earliest_trading_day_in_window}"
                                              # NOT today's date"""),
("alts", [
    ["<b>Anchor-keyed cache (earliest day in the window)</b>",
     "A normal daily pipeline run does not invalidate the cache, so headline backtest metrics do not "
     "silently drift day to day — which is what makes a dashboard trustworthy over time. The docstring "
     "names exactly the three changes that require <font face='Courier'>force_recompute=True</font>.",
     "Anyone extending the historical window without realising the key depends on the earliest date can "
     "accidentally serve a stale cache.",
     "*Chosen"],
    ["Key on today's date",
     "Trivially correct — always fresh.",
     "Recomputes an expensive walk-forward simulation on every single API call, and the headline number "
     "wobbles slightly every day as one more period enters the window.",
     "Rejected"],
    ["No cache — recompute every request",
     "Zero staleness risk.",
     "The walk-forward simulation is expensive; recomputing per request would make the API endpoint "
     "unusably slow.",
     "Rejected"],
]),

("h2", "5.8 API envelope and lazy imports"),
("code", """success(data) -> {"status": "ok", ...data}
error(msg)    -> {"status": "error", "message": msg}

def safe_import(name):
    try: return importlib.import_module(name)
    except Exception: return None      # imported INSIDE the request handler"""),
("alts", [
    ["<b>Uniform response envelope + lazy per-request imports</b>",
     "The frontend has exactly one response shape to handle. Boot is fast, and a broken engine breaks "
     "one endpoint instead of preventing the whole server from starting.",
     "Import errors surface at request time instead of at boot, which can delay discovering a broken "
     "dependency until a user hits that specific endpoint.",
     "*Chosen"],
    ["Import everything at module load, fail fast on boot",
     "Any broken dependency is caught immediately, before the server accepts traffic.",
     "One broken optional engine (e.g. a missing XGBoost) prevents the entire API — including unrelated "
     "endpoints — from starting.",
     "Rejected"],
]),

("h2", "5.9 Authentication and authorization"),
("code", """def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()          # unsalted

JWT_SECRET = os.environ.get("JWT_SECRET", "super-secret-dev-key") # insecure default"""),
("alts", [
    ["<b>Stateless JWT, hand-rolled, 7-day expiry</b> (as shipped)",
     "One dependency (PyJWT), no session store, trivial to reason about for a demo.",
     "SHA-256 is designed to be <i>fast</i> — a commodity GPU tests billions of candidates per second, "
     "and with no per-user salt identical passwords produce identical hashes. The JWT default secret "
     "lets anyone who has read this code forge a token for any user.",
     "*Shipped, not production-safe"],
    ["bcrypt / scrypt / argon2 + a mandatory JWT secret",
     "Deliberately slow, salted hashing that resists GPU cracking; a missing secret fails loudly at boot "
     "instead of falling back to a public default.",
     "One more dependency; marginally slower login.",
     "The correct fix — five-line change, Tier-1 roadmap"],
    ["Auth0 / Firebase Auth",
     "Outsources the entire problem, including password resets, MFA, and session management.",
     "External dependency and cost for a project that otherwise runs at zero infrastructure spend.",
     "Rejected — conflicts with the zero-cost design goal"],
]),
]
