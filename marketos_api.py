# marketos_api.py
# MarketOS — Flask REST API Gateway
# 
# Place this file in the SAME directory as your backend files (main.py, etc.)
# Run: python marketos_api.py
# API available at: http://localhost:5001
#
# Endpoints:
#   GET  /api/status          — Pipeline status + NIFTY live data
#   GET  /api/macro           — Macro variables + regime classification
#   GET  /api/alpha           — Alpha signal scores per subsector
#   GET  /api/portfolio       — Current portfolio allocation
#   GET  /api/forecasts       — Forward forecasts (1M, 3M, 6M)
#   GET  /api/performance     — Forecast accuracy & analytics
#   GET  /api/backtest        — Walk-forward backtest results
#   GET  /api/insights        — Latest AI-generated daily insight
#   GET  /api/sectors         — All sector/subsector structure
#   POST /api/run/fetch        — Trigger data fetch (non-blocking)
#   POST /api/run/daily        — Trigger daily pipeline (non-blocking)
#   GET  /api/healthcheck     — Server health

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
import threading
from datetime import datetime, date, timedelta
from functools import wraps
import warnings
warnings.filterwarnings("ignore")

# ── Add project root to path so backend modules resolve ───────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from flask import Flask, jsonify, request, Response
    from flask_cors import CORS
except ImportError:
    print("ERROR: Flask / flask-cors not installed.")
    print("Run: pip install flask flask-cors")
    sys.exit(1)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

import jwt
import hashlib
import uuid
import logging
from functools import wraps

# --- Setup Logging ---
logging.basicConfig(level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
                    format="%(asctime)s [%(levelname)s] %(message)s")

# --- Setup Rate Limiting ---
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    # The old default of "50 per hour / 200 per day" was far below what a
    # single legitimate dashboard session generates. The UI polls
    # /api/status every 10s (360 req/hour on its own) and each tab switch
    # fires another 2-5 calls -- so one user exhausted the hourly budget in
    # ~8 minutes and the daily budget in ~33, after which EVERY endpoint
    # returned 429 and every panel fell into its catch block showing
    # "run pipeline first". That was the dominant cause of the dashboard
    # "working once and then breaking".
    #
    # Read-only GETs are cheap now (alpha and portfolio are cached), so the
    # global ceiling is generous and exists only to stop genuine abuse.
    # Rate limiting is applied narrowly, below, where it actually protects
    # something: credential endpoints (brute force) and job triggers.
    limiter = Limiter(
        get_remote_address, app=app,
        default_limits=["3000 per hour", "20000 per day"],
    )
except ImportError:
    class DummyLimiter:
        def limit(self, *args, **kwargs):
            def decorator(f): return f
            return decorator
        def exempt(self, f):
            return f
    limiter = DummyLimiter()

# --- Security Headers ---
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# --- Bootstrap System ---
try:
    from bootstrap import BOOTSTRAP_STATE, start_bootstrap
except ImportError:
    BOOTSTRAP_STATE = {"is_running": False, "status": "error", "pipeline_ready": True}
    def start_bootstrap(): pass

def is_bootstrapping():
    return BOOTSTRAP_STATE.get("is_running", False)

@app.route("/")
@limiter.exempt
def root():
    return jsonify({
        "application": "MarketOS",
        "version": "2.0",
        "status": "running",
        "health": "/api/healthcheck",
        "docs": "/api/routes"
    })

@app.route("/dashboard")
def dashboard():
    # Serve the vanilla frontend
    try:
        with open("marketos_dashboard.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Dashboard not found: {e}", 404

@app.route("/api/bootstrap-status")
@limiter.exempt
def bootstrap_status():
    return jsonify(BOOTSTRAP_STATE)

@app.route("/api/routes")
@limiter.exempt
def get_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint != 'static':
            routes.append(rule.rule)
    return jsonify({"routes": routes})

@app.before_request
def check_bootstrap():
    if request.path in ["/", "/dashboard", "/api/bootstrap-status", "/api/healthcheck", "/api/health/deep", "/api/routes"]:
        return None
    if is_bootstrapping():
        progress = BOOTSTRAP_STATE.get("progress", "starting")
        return jsonify({
            "status": "bootstrapping",
            "message": "Initial market data is loading",
            "progress": progress
        }), 200

# ── JWT secret ──────────────────────────────────────────────────────
# Refuse to boot on a real deployment with the dev fallback secret still
# active — that fallback let anyone who has read this file forge a token
# for any user_id. RENDER/production platforms set FLASK_ENV=production (or
# you can set IS_PRODUCTION=true yourself); local dev is unaffected.
_IS_PRODUCTION = os.environ.get("FLASK_ENV") == "production" or os.environ.get("IS_PRODUCTION") == "true"
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    if _IS_PRODUCTION:
        raise RuntimeError(
            "JWT_SECRET is not set. Refusing to start in production with no "
            "signing key — set JWT_SECRET in the environment (Render: "
            "'generateValue: true' in render.yaml)."
        )
    JWT_SECRET = "super-secret-dev-key"
    print("  [auth] WARNING: JWT_SECRET not set — using an insecure dev "
          "default. Do not deploy like this.")

# ── Password hashing ────────────────────────────────────────────────
import bcrypt as _bcrypt

def hash_password(password: str) -> str:
    """bcrypt with a per-password random salt, cost factor 12."""
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt(rounds=12)).decode("utf-8")

def _looks_like_legacy_sha256(stored_hash: str) -> bool:
    # sha256 hexdigest is 64 hex chars; bcrypt hashes start with $2b$ and are ~60 chars.
    return len(stored_hash) == 64 and not stored_hash.startswith("$2")

def verify_password(password: str, stored_hash: str) -> bool:
    if _looks_like_legacy_sha256(stored_hash):
        # Old unsalted-SHA256 accounts (pre-bcrypt migration). Verify against
        # the legacy scheme so existing users aren't locked out, then the
        # caller re-hashes with bcrypt and saves it — a one-time, transparent
        # upgrade on next successful login.
        return hashlib.sha256(password.encode()).hexdigest() == stored_hash
    try:
        return _bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        return False

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"status": "error", "message": "Missing or invalid authorization token"}), 401
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user_id = payload.get("user_id")
        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "message": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"status": "error", "message": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


PLAN_RANK = {"free": 0, "pro": 1}

def _current_plan(user_id: int) -> str:
    """Reads the caller's plan, treating an expired pro plan as free."""
    from database import get_session, User
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return "free"
        if user.plan == "pro" and user.plan_expires_at and user.plan_expires_at < datetime.utcnow():
            return "free"
        return user.plan or "free"
    finally:
        session.close()

def require_plan(min_plan: str):
    """
    Gate a route behind a subscription tier. Must be stacked UNDER
    @require_auth (auth runs first so request.user_id exists):

        @app.route(...)
        @require_auth
        @require_plan("pro")
        def handler(): ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            plan = _current_plan(request.user_id)
            if PLAN_RANK.get(plan, 0) < PLAN_RANK.get(min_plan, 0):
                return jsonify({
                    "status": "error",
                    "code": "UPGRADE_REQUIRED",
                    "message": f"This endpoint requires the '{min_plan}' plan; your plan is '{plan}'.",
                    "current_plan": plan,
                    "required_plan": min_plan,
                }), 402   # 402 Payment Required — the correct status for this
            return f(*args, **kwargs)
        return decorated
    return decorator

# ── Global pipeline job tracker ──────────────────────────────────
_job_status = {"running": False, "job": None, "started_at": None, "result": None}

# ─────────────────────────────────────────────────────────────────
# ROUTE 0 — AUTHENTICATION
# ─────────────────────────────────────────────────────────────────

@app.route("/api/auth/register", methods=["POST"])
@limiter.limit("10 per hour")   # account-creation abuse
def auth_register():
    try:
        data = request.json
        email = data.get("email")
        password = data.get("password")
        if not email or not password:
            return error("Email and password required", 400)
        
        from database import get_session, User
        session = get_session()
        existing = session.query(User).filter_by(email=email).first()
        if existing:
            session.close()
            return error("User already exists", 400)
        
        new_user = User(
            uuid=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password(password),
            plan="free",
        )
        session.add(new_user)
        session.commit()

        token = jwt.encode({
            "user_id": new_user.id,
            "exp": datetime.utcnow() + timedelta(days=7)
        }, JWT_SECRET, algorithm="HS256")

        res = {"user_id": new_user.id, "email": new_user.email, "plan": new_user.plan, "token": token}
        session.close()
        return success_auth(res)
    except Exception as e:
        return error(str(e))

@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("20 per hour")   # credential brute-force
def auth_login():
    try:
        data = request.json
        email = data.get("email")
        password = data.get("password")
        if not email or not password:
            return error("Email and password required", 400)
        
        from database import get_session, User
        session = get_session()
        user = session.query(User).filter_by(email=email).first()
        if not user or not verify_password(password, user.password_hash):
            session.close()
            return error("Invalid credentials", 401)

        # Transparent upgrade: a legacy unsalted-SHA256 hash that just
        # verified correctly gets re-hashed with bcrypt and saved, so the
        # account is protected by the strong scheme from here on without
        # ever forcing a password reset.
        if _looks_like_legacy_sha256(user.password_hash):
            user.password_hash = hash_password(password)
            session.commit()

        token = jwt.encode({
            "user_id": user.id,
            "exp": datetime.utcnow() + timedelta(days=7)
        }, JWT_SECRET, algorithm="HS256")

        res = {"user_id": user.id, "email": user.email, "plan": user.plan or "free", "token": token}
        session.close()
        return success_auth(res)
    except Exception as e:
        return error(str(e))

@app.route("/api/auth/me", methods=["GET"])
@require_auth
def auth_me():
    from database import get_session, User
    session = get_session()
    user = session.query(User).filter_by(id=request.user_id).first()
    session.close()
    if not user:
        return error("User not found", 404)
    return success_auth({
        "user_id": user.id,
        "email": user.email,
        "plan": _current_plan(user.id),
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
    })

# ─────────────────────────────────────────────────────────────────
# ROUTE 0.6 — BILLING (stub)
#
# No payment provider is wired in yet — there is no Stripe/Razorpay key in
# .env. This gives the app the plumbing (plan on the user row, a gate
# decorator, an upgrade endpoint) so wiring a real webhook later is a
# contained change: point this endpoint at a verified Stripe/Razorpay
# checkout-session webhook instead of trusting the caller directly, and
# nothing else in the codebase needs to change — every gated route already
# reads the plan from the database.
# ─────────────────────────────────────────────────────────────────

@app.route("/api/billing/status", methods=["GET"])
@require_auth
def billing_status():
    from database import get_session, User
    session = get_session()
    user = session.query(User).filter_by(id=request.user_id).first()
    session.close()
    if not user:
        return error("User not found", 404)
    return success({
        "plan": _current_plan(user.id),
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
        "gated_endpoints": {
            "free_tier_limit": "1M horizon only, on /api/portfolio and /api/forecasts",
            "pro_only": ["/api/backtest", "3M/6M/12M horizons on /api/portfolio and /api/forecasts"],
        },
        "upgrade_available": (
            os.environ.get("ENABLE_DEV_BILLING_STUB", "false").lower() == "true" and not _IS_PRODUCTION
        ),
    })

@app.route("/api/billing/upgrade", methods=["POST"])
@require_auth
def billing_upgrade():
    """
    DEV/DEMO STUB — flips the caller to 'pro' for 30 days with no payment
    taken. Wire a real provider before this is public: verify a Stripe
    checkout.session.completed webhook signature (or Razorpay's payment
    webhook) server-side, then set the plan from THAT handler instead of
    from a client-callable route like this one.
    """
    # Hard off-switch: this route grants pro for free, so it must not be
    # reachable once real users can sign up, until a real payment provider
    # replaces it. Set ENABLE_DEV_BILLING_STUB=true only in local/dev envs.
    if not (os.environ.get("ENABLE_DEV_BILLING_STUB", "false").lower() == "true" and not _IS_PRODUCTION):
        return error(
            "Billing is not yet available. This deployment does not grant "
            "the pro plan without a real payment — the dev stub is disabled.",
            503,
        )

    from database import get_session, User
    session = get_session()
    user = session.query(User).filter_by(id=request.user_id).first()
    if not user:
        session.close()
        return error("User not found", 404)
    user.plan = "pro"
    user.plan_expires_at = datetime.utcnow() + timedelta(days=30)
    session.commit()
    plan_expires = user.plan_expires_at.isoformat()
    session.close()
    return success({"plan": "pro", "plan_expires_at": plan_expires,
                    "note": "Dev stub — no payment taken. Replace with a real billing webhook before launch."})

# ─────────────────────────────────────────────────────────────────
# ROUTE 0.5 — RISK PROFILING
# ─────────────────────────────────────────────────────────────────

@app.route("/api/risk/profile", methods=["POST", "GET"])
@require_auth
def handle_risk_profile():
    from database import get_session, UserRiskProfile
    from risk_profiler import save_risk_profile
    
    if request.method == "POST":
        try:
            data = request.json
            age = data.get("age", 30)
            income = data.get("income", "15L - 50L")
            horizon = data.get("horizon", "3-5Y")
            drawdown = data.get("drawdown", "Medium (10-20%)")
            
            result = save_risk_profile(request.user_id, age, income, horizon, drawdown)
            return success_auth(result)
        except Exception as e:
            return error(str(e))
    else:
        # GET request
        session = get_session()
        profile = session.query(UserRiskProfile).filter_by(user_id=request.user_id).first()
        session.close()
        if not profile:
            return success_auth({"risk_score": None, "risk_label": "Unassessed"})
        return success_auth({
            "age": profile.age,
            "income": profile.income_bracket,
            "horizon": profile.investment_horizon,
            "drawdown": profile.drawdown_tolerance,
            "risk_score": profile.risk_score,
            "risk_label": profile.risk_label
        })

# ─────────────────────────────────────────────────────────────────
# ROUTE 0.6 — EXECUTION SANDBOX
# ─────────────────────────────────────────────────────────────────

@app.route("/api/execute", methods=["POST"])
@require_auth
def handle_execution():
    from database import get_session, UserPortfolio
    from execution_engine import PaperBroker
    import json
    
    try:
        data = request.json
        capital = float(data.get("capital", 100000.0))
        
        session = get_session()
        # Get the latest generated portfolio for this user
        portfolio_record = session.query(UserPortfolio).filter_by(user_id=request.user_id).order_by(UserPortfolio.generated_at.desc()).first()
        session.close()
        
        if not portfolio_record:
            return error("No portfolio generated yet. Please generate a portfolio first.", 400)
            
        weights = json.loads(portfolio_record.portfolio_json)
        
        broker = PaperBroker(user_id=request.user_id, initial_capital=capital)
        orders = broker.generate_orders(weights)
        result = broker.execute_paper_trades(orders)
        
        return success_auth(result)
    except Exception as e:
        return error(str(e))

# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def success(data: dict, **kwargs) -> Response:
    payload = {"status": "ok", "timestamp": datetime.utcnow().isoformat(), **kwargs}
    payload.update(data)
    return jsonify(payload)


def success_auth(data: dict) -> Response:
    """Auth-specific success wrapper. Returns {status: 'success', data: {...}}."""
    return jsonify({"status": "success", "timestamp": datetime.utcnow().isoformat(), "data": data})


def error(message: str, code: int = 500) -> Response:
    return jsonify({"status": "error", "message": message,
                    "timestamp": datetime.utcnow().isoformat()}), code


def safe_import(module_name: str):
    """Safely imports a backend module, returns None on failure."""
    try:
        import importlib
        return importlib.import_module(module_name)
    except Exception as exc:
        print(f"  [API] Warning: could not import {module_name}: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────
# ROUTE 1 — HEALTHCHECK
# ─────────────────────────────────────────────────────────────────

@app.route("/api/healthcheck")
@limiter.exempt
def healthcheck():
    return success({"message": "MarketOS API is running", "version": "2.0"})

@app.route("/api/health/deep")
@limiter.exempt
def healthcheck_deep():
    try:
        from database import get_session, MacroData, DailyPrice, ForwardForecast
        session = get_session()
        db_connected = True
        try:
            macro_ok = session.query(MacroData).count() > 0
            prices_ok = session.query(DailyPrice).count() > 0
            forecasts_ok = session.query(ForwardForecast).count() > 0
        except Exception:
            macro_ok = prices_ok = forecasts_ok = False
        session.close()
    except Exception:
        db_connected = False
        macro_ok = prices_ok = forecasts_ok = False

    return success({
        "api": True,
        "database": db_connected,
        "macro_data": macro_ok,
        "daily_prices": prices_ok,
        "forecasts": forecasts_ok,
        # Derived directly from real DB counts, not the in-memory
        # BOOTSTRAP_STATE dict — that dict only ever gets updated by the
        # background auto-bootstrap thread, which never runs at all once
        # AUTO_BOOTSTRAP=false (the correct setting once the DB is already
        # seeded, e.g. via a local `main.py --setup` / `--daily` run
        # pointed at the same DATABASE_URL). Depending on it meant this
        # field could stay false forever regardless of real DB state.
        "pipeline_ready": db_connected and macro_ok and prices_ok and forecasts_ok
    })

# ─────────────────────────────────────────────────────────────────
# ROUTE 2 — PIPELINE STATUS
# ─────────────────────────────────────────────────────────────────

@app.route("/api/status")
def pipeline_status():
    try:
        from database import ensure_tables_exist
        ensure_tables_exist()

        from pipeline_utils import get_pipeline_date, get_nifty_return_from_db
        pipeline_date = get_pipeline_date()
        nifty_ret, is_valid, nifty_level, nifty_pts = get_nifty_return_from_db(pipeline_date)

        from market_calendar import get_market_status
        mkt = get_market_status()

        from database import get_session, DailyInsight
        session = get_session()
        try:
            latest_insight = session.query(DailyInsight).order_by(
                DailyInsight.date.desc()).first()
            last_run = str(latest_insight.date) if latest_insight else None
            regime_label = latest_insight.regime_label if latest_insight else "UNKNOWN"
            regime_score = latest_insight.regime_score if latest_insight else 0
        finally:
            session.close()

        return success({
            "pipeline_date":    str(pipeline_date),
            "is_trading_day":   mkt.get("is_trading_day", False),
            "engine_mode":      mkt.get("engine_mode", "UNKNOWN"),
            "session_state":    mkt.get("session_state", "UNKNOWN"),
            "last_trading_day": str(mkt.get("last_trading_day", "")),
            "next_trading_day": str(mkt.get("next_trading_day", "")),
            "data_quality":     mkt.get("data_quality", "UNKNOWN"),
            "close_reason":     mkt.get("close_reason", ""),
            "nifty": {
                "level":        nifty_level,
                "return_pct":   nifty_ret,
                "points":       nifty_pts,
                "is_valid":     is_valid,
            },
            "last_run_date":    last_run,
            "regime_label":     regime_label,
            "regime_score":     regime_score,
            "job_running":      _job_status["running"],
        })
    except Exception as exc:
        # Return safe defaults if backend not fully set up
        return success({
            "pipeline_date":    str(date.today() - timedelta(days=1)),
            "is_trading_day":   False,
            "engine_mode":      "OFFLINE",
            "session_state":    "OFFLINE",
            "last_trading_day": "",
            "next_trading_day": "",
            "data_quality":     "OFFLINE",
            "close_reason":     "",
            "nifty": {"level": 0, "return_pct": None, "points": 0, "is_valid": False},
            "last_run_date":    None,
            "regime_label":     "UNKNOWN",
            "regime_score":     0,
            "job_running":      _job_status["running"],
            "warning":          f"Backend partially unavailable: {str(exc)[:80]}",
        })


# ─────────────────────────────────────────────────────────────────
# ROUTE 2B — SENTIMENT DATA
# ─────────────────────────────────────────────────────────────────

@app.route("/api/sentiment")
def sentiment_data():
    try:
        from sentiment_engine import get_live_sentiment_all_sectors
        # force_refresh=False so we use cache and prevent long blocking calls / timeouts
        sentiment = get_live_sentiment_all_sectors(force_refresh=False)
        return success({"sentiment": sentiment})
    except Exception as exc:
        return error(f"Sentiment engine error: {str(exc)}")

# ─────────────────────────────────────────────────────────────────
# ROUTE 3 — MACRO DATA
# ─────────────────────────────────────────────────────────────────

@app.route("/api/macro")
def macro_data():
    try:
        from macro_engine import fetch_live_macro_data, classify_macro_regime
        macro = fetch_live_macro_data()
        regime = classify_macro_regime(macro)

        # Flatten regime for JSON serialisation
        regime_out = {
            "overall_regime":   regime.get("overall_regime", "UNKNOWN"),
            "regime_score":     float(regime.get("regime_score", 0)),
            "legacy_score":     int(regime.get("legacy_score", 0)),
            "bull_bear_label":  regime.get("bull_bear_label", "NEUTRAL"),
            "volatility_regime": regime.get("volatility_regime", "NORMAL"),
            "rate_regime":      regime.get("rate_regime", "STABLE"),
            "global_regime":    regime.get("global_regime", "NEUTRAL"),
        }

        return success({"macro": macro, "regime": regime_out})
    except Exception as exc:
        return error(f"Macro engine error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 4 — ALPHA SIGNALS
# ─────────────────────────────────────────────────────────────────

_ALPHA_CACHE = {}

@app.route("/api/alpha")
def alpha_signals():
    try:
        from macro_engine import fetch_live_macro_data, classify_macro_regime
        from alpha_engine import compute_alpha_scores
        from classification import MARKET_CLASSIFICATION
        from pipeline_utils import get_pipeline_date as _gpd

        # Cache keyed on the pipeline date. Without this, EVERY visit to the
        # Alpha tab re-read ~90 days of prices for all 28 subsectors and
        # re-ran the sentiment engine -- so simply navigating away and back
        # re-did the whole computation, which on a free instance routinely
        # outran the browser's patience and left the panel showing the
        # generic "run pipeline first" catch-block message. Alpha scores
        # only change when the pipeline date changes, so caching on that is
        # both safe and exactly as fresh as the underlying data.
        _alpha_key = str(_gpd())
        if _alpha_key in _ALPHA_CACHE:
            _hit = _ALPHA_CACHE[_alpha_key]
            return success({"alpha": _hit["alpha"], "total_sectors": _hit["total"],
                            "cached": True})

        macro  = fetch_live_macro_data()
        regime = classify_macro_regime(macro)

        # Build moderated_output from SectorPerformance DB rows
        from database import get_session, SectorPerformance
        from pipeline_utils import get_pipeline_date
        pd_date = get_pipeline_date()
        session = get_session()
        try:
            rows = session.query(SectorPerformance).filter(
                SectorPerformance.date >= pd_date - timedelta(days=3)
            ).all()
        finally:
            session.close()

        # Populate moderated_sectors from DB rows so alpha engine gets macro alignment
        moderated_sectors = {}
        for r in rows:
            sec = r.sector
            if sec not in moderated_sectors:
                align = r.macro_alignment or "NEUTRAL"
                # Map alignment string to a numeric macro_score
                _align_map = {"MACRO_ALIGNED": 1.0, "NEUTRAL": 0.65, "MACRO_DIVERGENT": 0.4}
                moderated_sectors[sec] = {
                    "macro_alignment": align,
                    "macro_score": _align_map.get(align, 0.65),
                    "sector_return": float(r.sector_return_pct or 0),
                }

        # If DB had no rows, build from classification with neutral defaults
        if not moderated_sectors:
            for sec_name in MARKET_CLASSIFICATION:
                moderated_sectors[sec_name] = {
                    "macro_alignment": "NEUTRAL",
                    "macro_score": 0.65,
                    "sector_return": 0.0,
                }

        moderated_output = {
            "macro_data": macro,
            "macro_regime": regime,
            "moderated_sectors": moderated_sectors,
        }

        alpha = compute_alpha_scores(moderated_output, macro, regime, force_run=True)

        # Sort by alpha score descending
        sorted_alpha = dict(sorted(
            alpha.items(),
            key=lambda x: x[1].get("alpha_score", 0),
            reverse=True
        ))

        # Keep only the newest entry — this is keyed by date, so stale keys
        # are pure memory waste on a 512MB instance.
        _ALPHA_CACHE.clear()
        _ALPHA_CACHE[_alpha_key] = {"alpha": sorted_alpha, "total": len(alpha)}

        return success({"alpha": sorted_alpha, "total_sectors": len(alpha),
                        "cached": False})
    except Exception as exc:
        import traceback; traceback.print_exc()
        return error(f"Alpha engine error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 5 — PORTFOLIO ALLOCATION
# ─────────────────────────────────────────────────────────────────

def _load_stored_forecasts():
    """
    Rebuilds the nested {sector: {subsector: {horizon: {...}}}} structure
    build_portfolio() expects, from the forward_forecasts rows the daily
    pipeline already wrote. Returns None if nothing is stored, so callers
    can fall back to live generation.

    Note the column/key rename: the DB stores `base_case_return` while the
    engine dicts use `base_case_return_pct` (likewise bull/bear).
    """
    from database import get_session, ForwardForecast
    from sqlalchemy import func

    session = get_session()
    try:
        latest = session.query(func.max(ForwardForecast.generated_date)).scalar()
        if not latest:
            return None
        rows = session.query(ForwardForecast).filter(
            ForwardForecast.generated_date == latest
        ).all()
    except Exception as exc:
        print(f"  [portfolio] stored-forecast load failed, will regenerate: {exc}")
        return None
    finally:
        session.close()

    if not rows:
        return None

    out = {}
    for r in rows:
        out.setdefault(r.sector, {}).setdefault(r.subsector, {})[r.forecast_horizon] = {
            "horizon":              r.forecast_horizon,
            "target_date":          r.target_date,
            "base_case_return_pct": r.base_case_return,
            "bull_case_return_pct": r.bull_case_return,
            "bear_case_return_pct": r.bear_case_return,
            "confidence_score":     r.confidence_score,
            "opportunity_score":    r.opportunity_score,
            "primary_catalyst":     r.primary_catalyst,
            "risk_factor":          r.risk_factor,
            "source":               "stored",
        }
    print(f"  [portfolio] using {len(rows)} stored forecasts from {latest}")
    return out


_PORTFOLIO_CACHE = {}

# FREE_TIER_HORIZONS previously gated non-1M horizons behind the pro plan.
# Disabled for now while the core product is still being validated end to
# end — gating a not-yet-fully-working product just hides real bugs from
# the person trying to test it. The set and the plan-check plumbing
# (_current_plan, _optional_plan, require_plan) are left in place below so
# re-enabling this later is a small, contained change, not a rebuild.
FREE_TIER_HORIZONS = {"1M", "3M", "6M", "12M"}   # all horizons currently free

@app.route("/api/portfolio")
@require_auth
def portfolio():
    try:
        horizon = request.args.get("horizon", "3M")

        from database import get_session, UserRiskProfile, UserPortfolio
        session_risk = get_session()
        risk_profile = session_risk.query(UserRiskProfile).filter_by(user_id=request.user_id).first()
        risk_label = risk_profile.risk_label if risk_profile else "Aggressive"
        session_risk.close()
        
        # Caching for instant horizon switching
        from pipeline_utils import get_pipeline_date
        pd_date_str = str(get_pipeline_date())
        cache_key = f"{pd_date_str}_{horizon}_{risk_label}"
        
        if cache_key in _PORTFOLIO_CACHE:
            portfolio_out = _PORTFOLIO_CACHE[cache_key]
            session_save = get_session()
            import json
            new_portfolio = UserPortfolio(
                user_id=request.user_id,
                horizon=horizon,
                risk_label=risk_label,
                portfolio_json=json.dumps(portfolio_out.get("positions", [])),
                execution_status="PENDING"
            )
            session_save.add(new_portfolio)
            session_save.commit()
            session_save.close()
            return success({"portfolio": portfolio_out, "horizon": horizon})
            
        from macro_engine import fetch_live_macro_data, classify_macro_regime
        from ml_forecast_engine import generate_ml_forecasts
        from portfolio_engine import build_portfolio
        from risk_engine import apply_risk_rules

        macro   = fetch_live_macro_data()
        regime  = classify_macro_regime(macro)
        # Prefer forecasts the daily pipeline already computed and stored.
        # Regenerating them here meant loading all 105 model pickles (~185MB)
        # and running 28 subsectors x 3 scenarios x 3 horizons of inference
        # on every cache miss -- measured at ~32s per horizon, which is both
        # why the Portfolio tab appeared broken (the browser gave up long
        # before it answered) and a real OOM risk on a 512MB free instance.
        # Falls back to live generation only if nothing is stored yet.
        fc      = _load_stored_forecasts() or generate_ml_forecasts(macro, regime)

        # Build moderated_output for alpha (needed for portfolio)
        from database import get_session, SectorPerformance
        from pipeline_utils import get_pipeline_date
        from classification import MARKET_CLASSIFICATION
        pd_date = get_pipeline_date()
        session = get_session()
        try:
            rows = session.query(SectorPerformance).filter(
                SectorPerformance.date >= pd_date - timedelta(days=3)
            ).all()
        finally:
            session.close()

        moderated_sectors = {}
        for r in rows:
            sec = r.sector
            if sec not in moderated_sectors:
                align = r.macro_alignment or "NEUTRAL"
                _align_map = {"MACRO_ALIGNED": 1.0, "NEUTRAL": 0.65, "MACRO_DIVERGENT": 0.4}
                moderated_sectors[sec] = {
                    "macro_alignment": align,
                    "macro_score": _align_map.get(align, 0.65),
                    "sector_return": float(r.sector_return_pct or 0),
                }
        if not moderated_sectors:
            for sec_name in MARKET_CLASSIFICATION:
                moderated_sectors[sec_name] = {"macro_alignment": "NEUTRAL", "macro_score": 0.65, "sector_return": 0.0}

        moderated_output = {"macro_data": macro, "macro_regime": regime, "moderated_sectors": moderated_sectors}
        from alpha_engine import compute_alpha_scores
        alpha = compute_alpha_scores(moderated_output, macro, regime, force_run=True)

        port    = build_portfolio(fc, macro, regime, horizon=horizon, alpha_scores=alpha, force_rebalance=True, risk_label=risk_label)
        risk_p  = apply_risk_rules(port, macro, regime)

        # Transform weights dict → positions array for the dashboard
        weights = risk_p.get("weights", {})
        positions = []
        for sub, w in weights.items():
            positions.append({
                "subsector":          sub,
                "sector":             w.get("sector", ""),
                "weight":             w.get("raw_weight", w.get("adjusted_weight", 0)),
                "adjusted_weight":    w.get("adjusted_weight", 0),
                "expected_return_pct": w.get("expected_return", 0),
                "volatility_pct":     w.get("volatility", 0),
                "alpha_score":        w.get("alpha_score", 0),
            })
        # Sort by adjusted weight descending
        positions.sort(key=lambda p: p["adjusted_weight"], reverse=True)

        # Extract portfolio-level metrics directly from the engine output
        total_exp = sum(p["adjusted_weight"] for p in positions)
        exp_ret   = port.get("portfolio_return_pct", port.get("expected_return", 0))
        port_vol  = port.get("portfolio_volatility_pct", port.get("portfolio_vol", 0))
        sharpe    = port.get("sharpe_like", 0)

        regime_label = risk_p.get("regime", regime.get("overall_regime", "NEUTRAL") if isinstance(regime, dict) else "NEUTRAL")
        severity     = risk_p.get("risk_flags", {}).get("severity", "GREEN") if isinstance(risk_p.get("risk_flags"), dict) else "GREEN"

        portfolio_out = {
            "positions":           positions,
            "expected_return_pct": round(exp_ret, 2),
            "expected_return":     round(exp_ret, 2),
            "portfolio_vol_pct":   round(port_vol, 2),
            "portfolio_vol":       round(port_vol, 2),
            "sharpe_like":         round(sharpe, 3),
            "total_exposure_pct":  round(total_exp, 4),
            "regime_label":        regime_label,
            "severity":            severity,
            "rules_applied":       risk_p.get("rules_applied", risk_p.get("applied_rules", [])),
            "risk_rules_applied":  risk_p.get("rules_applied", risk_p.get("applied_rules", [])),
            "cash_pct":            risk_p.get("cash_pct", 0),
            "nifty_hedge_pct":     risk_p.get("nifty_hedge_pct", 0.0),
            "horizon":             horizon,
        }

        # Save to UserPortfolio
        import json
        session_save = get_session()
        new_portfolio = UserPortfolio(
            user_id=request.user_id,
            horizon=horizon,
            risk_label=risk_label,
            portfolio_json=json.dumps(positions),
            execution_status="PENDING"
        )
        session_save.add(new_portfolio)
        session_save.commit()
        session_save.close()
        
        _PORTFOLIO_CACHE[cache_key] = portfolio_out

        return success({"portfolio": portfolio_out, "horizon": horizon})
    except Exception as exc:
        import traceback; traceback.print_exc()
        return error(f"Portfolio engine error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 6 — FORWARD FORECASTS
# ─────────────────────────────────────────────────────────────────

def _optional_plan() -> str:
    """
    Like _current_plan(), but for routes that stay browsable by anonymous
    visitors (a normal SaaS pattern — let people see a teaser before they
    sign up) while still rewarding a logged-in pro account. No token, an
    expired token, or a free-plan token all resolve to "free"; only a
    valid token belonging to a pro-plan user resolves to "pro".
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return "free"
    try:
        payload = jwt.decode(auth_header.split(" ")[1], JWT_SECRET, algorithms=["HS256"])
        return _current_plan(payload.get("user_id"))
    except jwt.InvalidTokenError:
        return "free"

def _filter_forecasts_by_plan(rows: list) -> tuple:
    """Free tier sees 1M only; pro sees every horizon. Returns (visible, locked_count)."""
    if _optional_plan() == "pro":
        return rows, 0
    visible = [r for r in rows if r.get("horizon") in FREE_TIER_HORIZONS]
    return visible, len(rows) - len(visible)

@app.route("/api/forecasts")
def forecasts():
    try:
        from database import get_session, ForwardForecast
        from pipeline_utils import get_pipeline_date
        pd_date = get_pipeline_date()

        # Load most recent forecasts from DB (last 7 days)
        session = get_session()
        try:
            since = pd_date - timedelta(days=7)
            rows = session.query(ForwardForecast).filter(
                ForwardForecast.generated_date >= since
            ).order_by(ForwardForecast.generated_date.desc()).all()
        finally:
            session.close()

        if not rows:
            # Fall back to generating live forecasts
            from macro_engine import fetch_live_macro_data, classify_macro_regime
            from ml_forecast_engine import generate_ml_forecasts
            macro  = fetch_live_macro_data()
            regime = classify_macro_regime(macro)
            fc     = generate_ml_forecasts(macro, regime)

            out = []
            for sector, horizons in fc.items():
                for horizon, data in horizons.items():
                    if isinstance(data, dict):
                        out.append({
                            "sector":           sector,
                            "horizon":          horizon,
                            "base_case_return": data.get("base_case_return", 0),
                            "bull_case_return": data.get("bull_case_return", 0),
                            "bear_case_return": data.get("bear_case_return", 0),
                            "confidence_score": data.get("confidence_score", 0),
                            "opportunity_score": data.get("opportunity_score", 5),
                            "primary_catalyst": data.get("primary_catalyst", ""),
                            "risk_factor":      data.get("risk_factor", ""),
                            "generated_date":   str(pd_date),
                        })
            visible, locked = _filter_forecasts_by_plan(out)
            return success({"forecasts": visible, "source": "live", "count": len(visible),
                            "locked_by_plan": locked})

        out = [{
            "id":               r.id,
            "sector":           r.sector,
            "subsector":        r.subsector,
            "horizon":          r.forecast_horizon,
            "base_case_return": r.base_case_return,
            "bull_case_return": r.bull_case_return,
            "bear_case_return": r.bear_case_return,
            "confidence_score": r.confidence_score,
            "opportunity_score": r.opportunity_score,
            "primary_catalyst": r.primary_catalyst,
            "risk_factor":      r.risk_factor,
            "generated_date":   str(r.generated_date),
        } for r in rows]

        visible, locked = _filter_forecasts_by_plan(out)
        return success({"forecasts": visible, "source": "database", "count": len(visible),
                        "locked_by_plan": locked})
    except Exception as exc:
        return error(f"Forecasts error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 6.5 — PAPER TRADES & RISK LIMITS
# ─────────────────────────────────────────────────────────────────

@app.route("/api/paper-trades")
def paper_trades():
    try:
        from portfolio_engine import evaluate_paper_trades, PAPER_TRADE_DIR
        import glob
        import json
        
        summary = evaluate_paper_trades() or {"total_trades": 0, "status": "NO_TRADES"}
        
        trades_list = []
        if os.path.isdir(PAPER_TRADE_DIR):
            files = sorted(glob.glob(os.path.join(PAPER_TRADE_DIR, "paper_trades_*.jsonl")))
            for fp in files:
                with open(fp, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            trades_list.append(json.loads(line))
        
        return success({
            "summary": summary,
            "trades": trades_list[-20:]
        })
    except Exception as exc:
        return error(f"Paper trades error: {str(exc)}")


@app.route("/api/risk-limits")
def risk_limits():
    try:
        from risk_engine import (
            MAX_DRAWDOWN_THRESHOLD,
            MAX_SINGLE_SECTOR_WEIGHT,
            MAX_CORRELATED_EXPOSURE,
            MIN_SECTORS_HELD,
            check_correlation_exposure
        )
        from pipeline_utils import get_pipeline_date
        pd_date = get_pipeline_date()
        
        weights_dict = {}
        try:
            fname = f"outputs/marketos_daily_{pd_date}.json"
            if os.path.exists(fname):
                with open(fname, 'r') as f:
                    data = json.load(f)
                    weights = data.get("portfolio", {}).get("risk_adjusted", {}).get("3M", {}).get("weights", {})
                    weights_dict = {k: v.get("adjusted_weight", 0.0) for k, v in weights.items()}
        except Exception:
            pass
            
        corr_warnings = check_correlation_exposure(weights_dict)
        
        return success({
            "limits": {
                "max_drawdown_threshold": MAX_DRAWDOWN_THRESHOLD,
                "max_single_sector_weight": MAX_SINGLE_SECTOR_WEIGHT,
                "max_correlated_exposure": MAX_CORRELATED_EXPOSURE,
                "min_sectors_held": MIN_SECTORS_HELD
            },
            "correlation_warnings": corr_warnings,
            "current_weights": weights_dict
        })
    except Exception as exc:
        return error(f"Risk limits error: {str(exc)}")


@app.route("/api/performance")
def performance():
    try:
        from performance_engine import compute_performance_summary
        lookback = int(request.args.get("lookback_days", 365))
        result = compute_performance_summary(lookback_days=lookback)

        # Make serialisable (numpy types → python)
        def _clean(obj):
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [_clean(i) for i in obj]
            elif hasattr(obj, "item"):  # numpy scalar
                return obj.item()
            return obj

        return success({"performance": _clean(result)})
    except Exception as exc:
        return error(f"Performance engine error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 8 — BACKTEST
# ─────────────────────────────────────────────────────────────────

@app.route("/api/backtest")
def backtest():
    try:
        years = int(request.args.get("years", 3))
        force = request.args.get("force", "false").lower() == "true"

        from backtest_engine import run_backtest
        # Serve ONLY from cache by default. Computing a backtest inside a
        # web request loads years of price history and simulates 15-35
        # rebalances; on a 512MB instance that killed the worker outright --
        # years=5 and years=10 returned an EMPTY response (no JSON, no
        # error), which the dashboard could only render as a stuck panel.
        # Populate the cache out-of-band with populate_backtest_cache.py.
        # ?force=true still allows an explicit recompute for local use.
        if not force:
            from backtest_engine import _load_cached_backtest
            results = _load_cached_backtest(years)
            if results is None:
                return success({
                    "backtest": {
                        "status": "not_cached",
                        "message": (
                            f"No cached {years}-year backtest. Backtests are "
                            f"pre-computed out-of-band because running one "
                            f"inside a request exceeds this instance's memory "
                            f"budget. Run: python populate_backtest_cache.py "
                            f"with DATABASE_URL pointed at this database."
                        ),
                        "metrics": {},
                        "equity_curve": [],
                    },
                    "years": years,
                })
        else:
            results = run_backtest(lookback_years=years, force_recompute=True)

        def _clean(obj):
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [_clean(i) for i in obj]
            elif hasattr(obj, "item"):
                return obj.item()
            elif hasattr(obj, "isoformat"):
                return obj.isoformat()
            return obj

        cleaned = _clean(results)

        # Free-tier truncation (equity curve / per-period weights hidden)
        # disabled for now — see the FREE_TIER_HORIZONS comment above.
        # Full backtest detail, including the equity curve, is returned to
        # everyone while the core product is still being validated.

        return success({"backtest": cleaned, "years": years})
    except Exception as exc:
        return error(f"Backtest engine error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 9 — AI INSIGHTS
# ─────────────────────────────────────────────────────────────────

@app.route("/api/insights")
def insights():
    try:
        from database import get_session, DailyInsight
        limit = int(request.args.get("limit", 5))
        session = get_session()
        try:
            rows = session.query(DailyInsight).order_by(
                DailyInsight.date.desc()).limit(limit).all()
        finally:
            session.close()

        out = []
        for r in rows:
            date_str = str(r.date)
            # Prefer the DB column. This previously read ONLY from
            # outputs/marketos_daily_<date>.json, which exists on the machine
            # that ran the pipeline and never on Render (ephemeral filesystem,
            # and those artefacts are gitignored) -- so the deployed
            # "Forecast Intelligence" panel was structurally guaranteed to be
            # empty. The JSON path is kept as a fallback for rows written
            # before the forward_insight column existed.
            forward_insight = getattr(r, "forward_insight", None) or ""
            if not forward_insight:
                json_path = os.path.join("outputs", f"marketos_daily_{date_str}.json")
                if os.path.exists(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f_json:
                            forward_insight = json.load(f_json).get("forward_insight", "")
                    except Exception:
                        pass

            out.append({
                "date":           date_str,
                "what_text":      r.what_text,
                "why_text":       r.why_text,
                "implication":    r.implication,
                "regime_context": r.regime_context,
                "full_insight":   r.full_insight,
                "forward_insight": forward_insight,
                "regime_label":   r.regime_label,
                "regime_score":   r.regime_score,
                "nifty_return":   r.nifty_return,
                "top_sector":     r.top_sector,
            })

        return success({"insights": out, "count": len(out)})
    except Exception as exc:
        return error(f"Insights error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 10 — SECTOR STRUCTURE
# ─────────────────────────────────────────────────────────────────

@app.route("/api/sectors")
def sectors():
    try:
        from classification import MARKET_CLASSIFICATION
        out = {}
        for sector, data in MARKET_CLASSIFICATION.items():
            subsectors_data = {}
            for sub_name, sub_data in data.get("subsectors", {}).items():
                subsectors_data[sub_name] = {
                    "subsector_weight_in_sector": sub_data.get("subsector_weight_in_sector", 0),
                    "macro_sensitivity": sub_data.get("macro_sensitivity", {}),
                    "companies": sub_data.get("companies", {})
                }
            out[sector] = {
                "nifty_weight": data.get("sector_nifty_weight", 0),
                "macro_drivers": data.get("macro_drivers", []),
                "subsectors": list(data.get("subsectors", {}).keys()),
                "subsectors_details": subsectors_data
            }
        return success({"sectors": out})
    except Exception as exc:
        return error(f"Sectors error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────
# ROUTE 11 — SECTOR PERFORMANCE HISTORY
# ─────────────────────────────────────────────────────────────────

@app.route("/api/sector-historical-returns")
def sector_historical_returns():
    try:
        from database import engine
        import pandas as pd
        from datetime import timedelta
        from pipeline_utils import get_pipeline_date
        
        pd_date = get_pipeline_date()
        
        # Load all prices for last 3 years
        since_date = pd_date - timedelta(days=3 * 365 + 30)
        q = f"SELECT date, subsector, sector, daily_return FROM daily_prices WHERE date >= '{since_date}'"
        df = pd.read_sql(q, engine)
        if df.empty:
            return success({"returns": []})
        df['date'] = pd.to_datetime(df['date']).dt.date
            
        # Group by date and subsector to get average daily return
        sub_daily = df.groupby(['date', 'sector', 'subsector'])['daily_return'].mean().reset_index()
        
        # Pivot so dates are index, subsectors are columns
        pivot = sub_daily.pivot_table(index='date', columns=['sector', 'subsector'], values='daily_return').fillna(0)
        
        # Calculate cumulative returns
        cum_ret = (1 + pivot).cumprod()
        
        # Get dates for 3M, 1Y, 3Y
        dates = pivot.index.tolist()
        if not dates: return success({"returns": []})
        last_date = dates[-1]
        
        def get_closest_date(target_date):
            valid = [d for d in dates if d <= target_date]
            return valid[-1] if valid else dates[0]
            
        date_3m = get_closest_date(last_date - timedelta(days=90))
        date_1y = get_closest_date(last_date - timedelta(days=365))
        date_3y = get_closest_date(last_date - timedelta(days=365*3))
        
        results = []
        for (sec, sub) in cum_ret.columns:
            val_now = cum_ret.loc[last_date, (sec, sub)]
            val_3m = cum_ret.loc[date_3m, (sec, sub)]
            val_1y = cum_ret.loc[date_1y, (sec, sub)]
            val_3y = cum_ret.loc[date_3y, (sec, sub)]
            
            ret_3m = (val_now / val_3m) - 1 if val_3m > 0 else 0
            ret_1y = (val_now / val_1y) - 1 if val_1y > 0 else 0
            ret_3y = (val_now / val_3y) - 1 if val_3y > 0 else 0
            
            results.append({
                "sector": sec,
                "subsector": sub,
                "ret_3m": ret_3m * 100,
                "ret_1y": ret_1y * 100,
                "ret_3y": ret_3y * 100
            })
            
        # Sort by 1Y return descending
        results.sort(key=lambda x: x["ret_1y"], reverse=True)
        return success({"returns": results})
    except Exception as e:
        return error(str(e))


@app.route("/api/sector-performance")
def sector_performance():
    try:
        from database import get_session, SectorPerformance, DailyPrice
        from pipeline_utils import get_pipeline_date
        from classification import MARKET_CLASSIFICATION
        days = int(request.args.get("days", 30))
        pd_date = get_pipeline_date()
        since = pd_date - timedelta(days=days)

        session = get_session()
        try:
            rows = session.query(SectorPerformance).filter(
                SectorPerformance.date >= since
            ).order_by(SectorPerformance.date.desc()).all()
        finally:
            session.close()

        out = [{
            "date":            str(r.date),
            "sector":          r.sector,
            "subsector":       r.subsector,
            "sector_return":   r.sector_return_pct,
            "subsector_return": r.subsector_return_pct,
            "macro_alignment": r.macro_alignment,
            "regime_label":    r.regime_label,
            "top_company":     r.top_company,
        } for r in rows]

        # ── FALLBACK: if SectorPerformance has < 5 days of data, compute
        #    historical sector returns from DailyPrice table for the chart ──
        unique_dates_in_sp = len(set(r["date"] for r in out))
        if days > 1 and unique_dates_in_sp < 5:
            # Build subsector→sector map from classification
            sub_to_sector = {}
            for sec_name, sec_data in MARKET_CLASSIFICATION.items():
                for sub_name in sec_data.get("subsectors", []):
                    sub_to_sector[sub_name] = sec_name

            session = get_session()
            try:
                price_rows = session.query(DailyPrice).filter(
                    DailyPrice.date >= since,
                    DailyPrice.daily_return.isnot(None)
                ).all()
            finally:
                session.close()

            if price_rows:
                # Aggregate: per date+subsector → weighted return
                from collections import defaultdict
                day_sub = defaultdict(lambda: {"ret_sum": 0.0, "wt_sum": 0.0})
                for pr in price_rows:
                    key = (str(pr.date), pr.subsector)
                    day_sub[key]["ret_sum"] += float(pr.daily_return or 0) * float(pr.nifty_weight or 0.001)
                    day_sub[key]["wt_sum"]  += float(pr.nifty_weight or 0.001)

                # Build sector-level aggregation per date
                day_sector = defaultdict(lambda: {"ret_sum": 0.0, "n": 0})
                backfill = []
                existing_keys = set((r["date"], r["subsector"]) for r in out)
                for (dt, sub), agg in day_sub.items():
                    if (dt, sub) in existing_keys:
                        continue
                    sec = sub_to_sector.get(sub, "Other")
                    sub_ret = (agg["ret_sum"] / agg["wt_sum"]) if agg["wt_sum"] > 0 else 0
                    day_sector[(dt, sec)]["ret_sum"] += sub_ret
                    day_sector[(dt, sec)]["n"] += 1
                    backfill.append({
                        "date":            dt,
                        "sector":          sec,
                        "subsector":       sub,
                        "sector_return":   0,  # filled below
                        "subsector_return": round(sub_ret * 100, 4),
                        "macro_alignment": "NEUTRAL",
                        "regime_label":    "—",
                        "top_company":     None,
                    })

                # Fill in sector-level avg return
                for rec in backfill:
                    key = (rec["date"], rec["sector"])
                    ds = day_sector.get(key)
                    if ds and ds["n"] > 0:
                        rec["sector_return"] = round(ds["ret_sum"] / ds["n"] * 100, 4)

                out.extend(backfill)
                # Sort by date descending
                out.sort(key=lambda r: r["date"], reverse=True)

        return success({"sector_performance": out, "count": len(out)})
    except Exception as exc:
        import traceback; traceback.print_exc()
        return error(f"Sector performance error: {str(exc)}")


# ─────────────────────────────────────────────────────────────────
# ROUTE 12 — TRIGGER PIPELINE JOBS (async)
# ─────────────────────────────────────────────────────────────────

def _run_job(job_fn):
    """Runs a job in a background thread."""
    global _job_status
    _job_status["running"] = True
    _job_status["started_at"] = datetime.utcnow().isoformat()
    try:
        result = job_fn()
        _job_status["result"] = "success"
    except Exception as exc:
        _job_status["result"] = f"error: {str(exc)}"
    finally:
        _job_status["running"] = False


# ─────────────────────────────────────────────────────────────────
# ROUTE 12b — MACRO HISTORY (for dashboard charts)
# ─────────────────────────────────────────────────────────────────

@app.route("/api/macro-history")
def macro_history():
    try:
        from database import get_session, MacroData
        from pipeline_utils import get_pipeline_date
        days = int(request.args.get("days", 30))
        pd_date = get_pipeline_date()
        since = pd_date - timedelta(days=days)

        session = get_session()
        try:
            rows = session.query(MacroData).filter(
                MacroData.date >= since
            ).order_by(MacroData.date.asc()).all()
        finally:
            session.close()

        out = [{
            "date":         str(r.date),
            "nifty_close":  r.nifty_close,
            "nifty_return": r.nifty_return,
            "india_vix":    r.india_vix,
            "brent_crude":  r.brent_crude,
            "usdinr":       r.usdinr,
            "fii_net_crore": r.fii_net_crore,
            "dii_net_crore": r.dii_net_crore,
            "gold_close":   r.gold_close,
        } for r in rows if r.nifty_close and r.nifty_close > 0]

        return success({"macro_history": out, "days": days, "count": len(out)})
    except Exception as exc:
        return error(f"Macro history error: {str(exc)}")


@app.route("/api/run/fetch", methods=["POST"])
@limiter.limit("6 per hour")    # expensive job trigger
def run_fetch():
    if _job_status["running"]:
        return error("A job is already running. Please wait.", 409)
    try:
        from data_loader import run_data_loader
        t = threading.Thread(target=_run_job, args=(run_data_loader,), daemon=True)
        t.start()
        return success({"message": "Data fetch started in background"})
    except Exception as exc:
        return error(f"Could not start fetch job: {str(exc)}")


@app.route("/api/run/daily", methods=["POST"])
@limiter.limit("6 per hour")    # expensive job trigger
def run_daily():
    if _job_status["running"]:
        return error("A job is already running. Please wait.", 409)
    try:
        import main as m
        t = threading.Thread(target=_run_job, args=(m.run_daily_pipeline,), daemon=True)
        t.start()
        return success({"message": "Daily pipeline started in background"})
    except Exception as exc:
        return error(f"Could not start daily pipeline: {str(exc)}")


@app.route("/api/run/status")
def run_status():
    return success({"job": _job_status})


# ─────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────

# ── Production startup ────────────────────────────────────────
try:
    from database import ensure_tables_exist
    ensure_tables_exist()
    print("  [OK] Database tables verified")
    # Trigger zero-touch background bootstrapping
    start_bootstrap()
except Exception as e:
    print(f"  [WARNING] Database/Bootstrap warning: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n  MarketOS API — port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
