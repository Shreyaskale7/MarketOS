import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# Define custom Canvas for headers/footers with dynamic page numbers
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        if self._pageNumber == 1:
            # Drawing simple background decorations for cover page
            self.setFillColor(colors.HexColor("#0D1117")) # Dark charcoal theme
            self.rect(0, 0, 8.5*inch, 11*inch, fill=1, stroke=0)
            
            # Draw decorative top line
            self.setFillColor(colors.HexColor("#38BDF8")) # Accent cyan
            self.rect(0, 10.7*inch, 8.5*inch, 0.3*inch, fill=1, stroke=0)
            self.restoreState()
            return

        # Running headers for subsequent pages
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(54, 10.4*inch, "MARKETOS — DEEP DIVE INTERVIEW PREPARATION GUIDE")
        
        # Header bottom line
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 10.3*inch, 8.5*inch - 54, 10.3*inch)

        # Footers
        self.line(54, 54, 8.5*inch - 54, 54)
        self.drawString(54, 40, "Confidential — Private Study Reference")
        
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5*inch - 54, 40, page_str)
        self.restoreState()

def create_interview_pdf(filename="marketos_interview_book.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    
    # Custom Palette
    PRIMARY = colors.HexColor("#0F172A")    # Deep slate
    ACCENT = colors.HexColor("#0284C7")     # Vivid blue
    TEXT_DARK = colors.HexColor("#1E293B")  # Soft charcoal
    BG_LIGHT = colors.HexColor("#F8FAFC")   # Ice white/slate-50
    BORDER_COLOR = colors.HexColor("#CBD5E1")
    
    # Typography Styles
    title_style = ParagraphStyle(
        'CoverTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=32,
        leading=38,
        textColor=colors.HexColor("#F8FAFC"),
        alignment=0,
        spaceAfter=15
    )
    
    subtitle_style = ParagraphStyle(
        'CoverSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=14,
        leading=20,
        textColor=colors.HexColor("#94A3B8"),
        spaceAfter=40
    )
    
    metadata_style = ParagraphStyle(
        'CoverMeta',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=16,
        textColor=colors.HexColor("#38BDF8")
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=PRIMARY,
        spaceBefore=18,
        spaceAfter=10,
        keepWithNext=True
    )
    
    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=ACCENT,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=TEXT_DARK,
        spaceAfter=10
    )

    code_style = ParagraphStyle(
        'Code_Custom',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0F172A"),
        backColor=colors.HexColor("#F1F5F9"),
        borderColor=colors.HexColor("#E2E8F0"),
        borderWidth=0.5,
        borderPadding=6,
        spaceAfter=10
    )

    callout_style = ParagraphStyle(
        'Callout_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#0369A1"),
        backColor=colors.HexColor("#F0F9FF"),
        borderColor=colors.HexColor("#BAE6FD"),
        borderWidth=1,
        borderPadding=8,
        spaceAfter=10
    )

    qa_question_style = ParagraphStyle(
        'QA_Question',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#B45309"),
        backColor=colors.HexColor("#FEF3C7"),
        borderColor=colors.HexColor("#FDE68A"),
        borderWidth=0.5,
        borderPadding=6,
        spaceAfter=4,
        keepWithNext=True
    )

    qa_answer_style = ParagraphStyle(
        'QA_Answer',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=TEXT_DARK,
        spaceAfter=12
    )

    story = []

    # ─────────────────────────────────────────────────────────────────
    # COVER PAGE
    # ─────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 2.5*inch))
    story.append(Paragraph("MARKETOS", title_style))
    story.append(Paragraph("The Engineering, Data Science & Portfolio Operations Study Manual", subtitle_style))
    story.append(Spacer(1, 1.5*inch))
    
    meta_text = """
    <b>AUTHOR:</b> Antigravity AI Agent<br/>
    <b>TARGET ROLE:</b> Quantitative Developer / Python Financial Engineer<br/>
    <b>COMPILATION DATE:</b> July 2026<br/>
    <b>SYSTEM REVISION:</b> v5 (High-Sharpe Architecture)<br/>
    """
    story.append(Paragraph(meta_text, metadata_style))
    story.append(PageBreak())

    # Helper function to add a standard Section Header
    def add_section_header(title, num):
        story.append(Spacer(1, 10))
        story.append(Paragraph(f"{num}. {title}", h1_style))
        story.append(Spacer(1, 4))

    # Helper function to add QA Box
    def add_qa(question, answer):
        story.append(Paragraph(f"<b>INTERVIEW QUESTION:</b> {question}", qa_question_style))
        story.append(Paragraph(f"<b>BEST PRACTICE ANSWER:</b> {answer}", qa_answer_style))

    # ─────────────────────────────────────────────────────────────────
    # SECTION 1: ARCHITECTURE
    # ─────────────────────────────────────────────────────────────────
    add_section_header("Overall Architecture & System Topology", "1")
    story.append(Paragraph(
        "MarketOS is designed as a modular financial micro-pipeline orchestrator. "
        "The system decouples data ingestion, intelligence modeling, mathematical optimization, and "
        "service gateway components. This modularity ensures that failures in yfinance ingestion or "
        "Groq sentiment scraping do not block historical calculations, allowing the backend to fall back "
        "gracefully to the last known database state.",
        body_style
    ))
    
    story.append(Paragraph(
        "<b>Architectural Map:</b><br/>"
        "User Interface (HTML/CSS Dashboard) ──► HTTP Requests ──► Flask REST API Gateway ──► "
        "SQLAlchemy Core ──► SQLite DB (data/marketos.db)<br/>"
        "<i>Orchestrator Cron:</i> main.py ──► Ingestion Engine (yfinance) + NLP Engine (Groq LLaMA-3.3) ──► Model Inferences ──► MVO Optimizer ──► SQLite Writes.",
        callout_style
    ))

    add_qa(
        "How would you scale this architecture if we transitioned from 130 stocks to 10,000 global tickers with real-time updates?",
        "To scale to 10,000 global tickers in real-time, I would shift from a synchronous pipeline to an event-driven, distributed message architecture. "
        "I would replace yfinance with a persistent WebSocket connection (like Dhan API or Tickertape) publishing raw tick data to Apache Kafka. "
        "A distributed stream processing framework like Apache Spark Streaming would consume tick messages, compute rolling technical indicators, "
        "and load data into a high-throughput time-series database (such as TimescaleDB or InfluxDB). "
        "The ML models would run inferences asynchronously via Celery worker pools, and we would cache the active state in Redis."
    )

    add_qa(
        "How do you handle cold starts in this architecture when the system is deployed with a completely empty database?",
        "On cold start, the database bootstrap module ('bootstrap.py') catches 'empty database' signals on startup. "
        "It automatically triggers a safe backfill sequence that downloads the full 10-year historical dataset from yfinance "
        "and immediately trains the Ridge and Random Forest model horizons (1M/3M/6M) to generate baseline forecasts before starting the API. "
        "We enforce safe try-except boundaries with exponential backoff on downloads so that a single failed network call doesn't halt the cold start process."
    )

    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────
    # SECTION 2: DATA FLOW
    # ─────────────────────────────────────────────────────────────────
    add_section_header("Deep-Dive Data Flow & Synchronization", "2")
    story.append(Paragraph(
        "Each daily execution triggers a sequential 10-stage processing run. "
        "Data synchronization is critical: we use a single source of truth for time ('get_pipeline_date()') to "
        "guarantee zero look-ahead bias and avoid standard date misalignment errors during joins.",
        body_style
    ))

    story.append(Paragraph(
        "<b>Ingestion & Processing Lifecycle:</b><br/>"
        "1. yfinance download ──► 2. Date index alignments ──► 3. Left-join with MacroData (with ffill to prevent dropping rows) "
        "──► 4. Headline RSS parsing ──► 5. LLM prompt assembly ──► 6. Sentiment score mapping (-1.0 to 1.0) "
        "──► 7. Ensemble ML return prediction ──► 8. Portfolio quadratic MVO ──► 9. Transaction limit filters (±10% turnover) ──► 10. Database commits.",
        callout_style
    ))

    add_qa(
        "Your pipeline downloads data daily. What happens if yfinance undergoes a rate-limit lockout mid-run?",
        "I implemented a multi-tiered fallback mechanism. First, our HTTP/scraping layer includes retry decorators with "
        "exponential backoff. Second, if yfinance blocks us completely, the pipeline catches the download error, "
        "switches the system status to 'FALLBACK' mode, loads the last cached historical database record, and runs the forecasting "
        "on the existing data. This keeps the service running and guarantees near 100% API uptime."
    )

    add_qa(
        "Why is alignment via 'LEFT JOIN' with forward-fill (ffill) so critical for financial pipelines?",
        "Macroeconomic statistics (like CPI, IIP, or GDP growth) are released monthly or quarterly, while stock prices are generated daily. "
        "An inner join would completely discard any daily rows where macro statistics are absent, leaving us with zero data. "
        "By doing a LEFT JOIN on stock dates, followed by a forward-fill (ffill), we propagate the last known macro statistics forward, "
        "preserving every single daily transaction while safely matching the macro regime state."
    )

    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────
    # SECTION 3: TECHNOLOGY STACK
    # ─────────────────────────────────────────────────────────────────
    add_section_header("Technology Selection Rationale & Trade-Offs", "3")
    
    # Simple Table for Tech Stack
    tech_data = [
        [Paragraph("<b>Component</b>", body_style), Paragraph("<b>Technology</b>", body_style), Paragraph("<b>Engineering Rationale</b>", body_style)],
        [Paragraph("Backend", body_style), Paragraph("Flask", body_style), Paragraph("Lightweight, low overhead, perfect for microservice-scale REST APIs.", body_style)],
        [Paragraph("Database", body_style), Paragraph("SQLite", body_style), Paragraph("Serverless, zero-config, ACID-compliant. File-based reading is faster than TCP at small scale.", body_style)],
        [Paragraph("ORM", body_style), Paragraph("SQLAlchemy", body_style), Paragraph("Database engine agnostic. Safely parameterizes queries, eliminating SQL injection risk.", body_style)],
        [Paragraph("Auth", body_style), Paragraph("PyJWT", body_style), Paragraph("Stateless, signed tokens. Reduces database reads on protected routes.", body_style)]
    ]
    t = Table(tech_data, colWidths=[1.2*inch, 1.2*inch, 4.0*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), BG_LIGHT),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    add_qa(
        "Why use SQLite over PostgreSQL for a quantitative pipeline?",
        "For a startup prototype or research pipeline covering 130 companies and 10 years of daily data, SQLite is superior. "
        "The entire database file is under 50MB and resides in-memory or on the local fast NVMe disk. "
        "This completely eliminates Postgres network handshake latencies (approx 1-3ms per query), making bulk batch insertions 2-3x faster. "
        "SQLite is zero-configuration and runs seamlessly inside isolated Docker containers without needing a separate Postgres service database container. "
        "Once our volume grows past 10GB or requires concurrent multi-client writes, we can seamlessly migrate to PostgreSQL by updating SQLAlchemy's connection string."
    )

    add_qa(
        "Why not use a NoSQL database like MongoDB for storing time-series financial data?",
        "Financial market systems require absolute transactional integrity (ACID properties) and relational structures. "
        "Prices must map exactly to tickers, sectors, dates, and historical orders. MongoDB has high document storage overhead, "
        "lacks strict relational schema enforcement out-of-the-box, and does not perform range-based multi-table joins efficiently. "
        "SQL databases let us execute highly optimized relational queries and index scans, ensuring complete numeric precision and consistency."
    )

    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────
    # SECTION 4: ML MODELS
    # ─────────────────────────────────────────────────────────────────
    add_section_header("Machine Learning Forecasting Architecture", "4")
    story.append(Paragraph(
        "The ml_forecast_engine uses a <b>VotingRegressor</b> ensembling <b>RandomForestRegressor</b> and "
        "<b>Ridge Regression</b>. Rather than relying on a single complex model, this ensemble exploits "
        "diverse structural patterns to capture both linear and non-linear relationships.",
        body_style
    ))

    add_qa(
        "Explain the Bias-Variance trade-off in the context of your Ridge and Random Forest ensemble.",
        "1. Random Forest has low bias (it can fit highly complex, non-linear interactions) but high variance (it tends to overfit to noise, "
        "and tree models struggle to extrapolate trends outside their training bounds).\n"
        "2. Ridge Regression has higher bias (assumes linear relationships) but very low variance due to L2 regularization, "
        "which penalizes high weight coefficients and handles collinear features gracefully.\n"
        "3. By combining them in a VotingRegressor, we average their predictions. This cancels out the high variance of the tree model "
        "while relaxing the linear bias of Ridge, yielding extremely robust generalizations."
    )

    add_qa(
        "What is L2 Regularization in Ridge, and how does it prevent overfitting?",
        "Ridge regression minimizes the sum of squared residuals PLUS a penalty term proportional to the sum of squared coefficients: "
        "Penalty = alpha * sum(w_j^2). This is L2 regularization. It forces feature coefficients to shrink continuously toward zero but "
        "never allows them to reach exactly zero (unlike L1 Lasso). This suppresses features that are heavily collinear (e.g., highly correlated "
        "technical indicators) and prevents any single feature from dominating the prediction, which drastically reduces overfitting to noisy data."
    )

    add_qa(
        "Why not use an LSTM or Transformer model instead of tabular ensembles?",
        "LSTMs and Transformers require vast volumes of high-frequency data to train effectively. For end-of-day tabular datasets, "
        "deep neural networks are extremely prone to overfitting due to the low signal-to-noise ratio of daily prices, and they are difficult to interpret. "
        "Furthermore, they suffer from high inference latency and representational drift. Standard ensemble models (Ridge + RF) "
        "train in seconds, are highly interpretable through feature weights, and consistently generalize better on noisy tabular macro-financial series."
    )

    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────
    # SECTION 5: METRICS
    # ─────────────────────────────────────────────────────────────────
    add_section_header("Quantitative Metrics & Backtesting Validation", "5")
    story.append(Paragraph(
        "Performance evaluation in MarketOS goes beyond basic RMSE/MAE. "
        "We must measure risk-adjusted returns and ensure that our model does not leak information from the future.",
        body_style
    ))

    add_qa(
        "What is the difference between Sharpe Ratio and Information Ratio?",
        "The Sharpe Ratio evaluates the excess return of the portfolio relative to the risk-free rate, divided by the total volatility of the portfolio. "
        "It measures absolute risk-adjusted return.\n"
        "The Information Ratio evaluates the excess return of the portfolio relative to a specific benchmark (e.g., NIFTY), divided by the "
        "standard deviation of those active excess returns (tracking error). It measures active manager skill and consistency relative to the index."
    )

    add_qa(
        "Explain Walk-Forward Validation and why standard K-Fold cross-validation fails for financial time series.",
        "Standard K-Fold cross-validation shuffles data and splits it randomly. In time series, this leaks future information "
        "into the training set (e.g. training on day t+1 to predict day t), causing extreme look-ahead bias and artificially high accuracy. "
        "Walk-Forward validation preserves chronological order. It trains on a window (e.g., Year 1-3), tests on Year 4, then expands the training "
        "window to include Year 4, and tests on Year 5. This mirrors real-world trading and yields realistic performance expectations."
    )

    add_qa(
        "What is Maximum Drawdown, and how does your risk engine mitigate it?",
        "Maximum Drawdown is the largest peak-to-trough decline in portfolio value before a new peak is reached. "
        "Our risk engine actively mitigates drawdown in two ways. First, if a subsector exhibits sudden extreme volatility, "
        "a high-volatility penalty reduces its expected return in the MVO. Second, we integrate a portfolio-level volatility cap "
        "of 26.0% and scale down risk allocations when the India VIX (fear index) spikes, shifting assets to defensive consumption sectors."
    )

    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────
    # SECTION 6: API ENDPOINTS
    # ─────────────────────────────────────────────────────────────────
    add_section_header("REST API Gateway & Schema Compliance", "6")
    story.append(Paragraph(
        "The API gateway (marketos_api.py) acts as a high-security boundary. "
        "It enforces payload validation, rate-limiting, and state-aware REST status codes.",
        body_style
    ))

    add_qa(
        "How would you secure your endpoints against unauthorized external access?",
        "I implemented JWT (JSON Web Tokens) stateless authentication via a custom '@require_auth' decorator. "
        "Clients must send a 'Authorization: Bearer <JWT_TOKEN>' header on all protected routes. "
        "The server decodes this token using a secure 'JWT_SECRET' environment variable. "
        "If the token is missing, expired, or tampered with, we block access immediately and return a '401 Unauthorized' JSON status code."
    )

    add_qa(
        "What are the benefits and drawbacks of a REST API vs WebSockets for financial applications?",
        "REST is stateless, reliable, and perfectly suited for request-response cycles like fetching daily historical statistics, "
        "backtest metrics, or starting daily pipelines. Its drawback is that it requires polling, which is inefficient for real-time tick updates. "
        "WebSockets provide a persistent, bi-directional connection, which is ideal for streaming live price ticks and immediate order executions. "
        "However, WebSockets are stateful, harder to load balance, and consume more server connections. Decoupling them (REST for static metadata, "
        "WebSockets for streaming ticks) is the industry standard."
    )

    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────
    # SECTION 7: DATABASE SCHEMA
    # ─────────────────────────────────────────────────────────────────
    add_section_header("Database Design & Performance Invariants", "7")
    story.append(Paragraph(
        "The schema represents a structured relational mapping designed to minimize join latency. "
        "We store stock metrics, historical backtests, user settings, and ML training parameters.",
        body_style
    ))

    add_qa(
        "How would you optimize index performance on your 'daily_prices' table if it reaches 100 million rows?",
        "At 100 million rows, full table scans would collapse the API. I would build a composite index on '(ticker, date)'. "
        "This allows range queries (e.g. fetching 60 days of prices for SBIN.NS) to execute via index scans in sub-millisecond times. "
        "I would also implement database partitioning (e.g., partition tables by Year or Sector) so that queries for active "
        "dates only hit small, localized index blocks, drastically reducing I/O and memory overhead."
    )

    add_qa(
        "Explain the schema relationship between your Users, UserRiskProfile, and UserPortfolio tables.",
        "It is a classic one-to-many relationship chain. The 'users' table holds the primary user record (id PK, email, password_hash). "
        "The 'user_risk_profiles' table has a foreign key 'user_id' referencing 'users.id'. Each user has a historical sequence of "
        "risk evaluations (as their age or income changes). Similarly, 'user_portfolios' holds records of MVO runs, with a 'user_id' "
        "referencing 'users.id'. This allows us to track portfolio evolution, transaction histories, and risk metrics over time."
    )

    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────
    # SECTION 8: SECURITY
    # ─────────────────────────────────────────────────────────────────
    add_section_header("System Security, Hardening & Vulnerabilities", "8")
    story.append(Paragraph(
        "Security is paramount in financial systems. The API gateway must be hardened "
        "against common web vulnerabilities (OWASP Top 10) to protect private analytical data.",
        body_style
    ))

    add_qa(
        "How do you prevent SQL Injection attacks in your API routes?",
        "By utilizing SQLAlchemy ORM. Instead of building raw SQL string queries (e.g., f'SELECT * FROM users WHERE email=\"{user_input}\"'), "
        "SQLAlchemy automatically parameterizes all queries under the hood (e.g., 'session.query(User).filter_by(email=email).first()'). "
        "This separates the SQL query logic from the input data, rendering SQL injection completely impossible."
    )

    add_qa(
        "How would you protect against Cross-Site Scripting (XSS) and Session Hijacking?",
        "1. XSS: Ensure all user-supplied fields (like RSS headlines or feedback comments) are properly sanitized and escaped on the frontend. "
        "We also enforce an 'after_request' security header 'X-Content-Type-Options: nosniff'.\n"
        "2. Session Hijacking: When deploying in production, the JWT token must not be stored in the browser's insecure localStorage. "
        "Instead, it should be sent as an HTTP-only, secure, SameSite=Strict cookie. This completely prevents malicious client-side JS "
        "from reading the token, mitigating XSS token theft."
    )

    story.append(PageBreak())

    # ─────────────────────────────────────────────────────────────────
    # SECTION 9 & 10: CHALLENGES & ROADMAP
    # ─────────────────────────────────────────────────────────────────
    add_section_header("Engineering Challenges & Roadmaps", "9 & 10")
    
    story.append(Paragraph("<b>The Dynamic Regime-Switching Problem:</b>", h2_style))
    story.append(Paragraph(
        "Financial systems frequently break down because historical correlation models are static. "
        "A model trained during a 3-year bull market fails catastrophically when the VIX spikes or "
        "macro interest rates rise. In MarketOS, I engineered a dynamic regime-switching risk classifier "
        "that calculates a weighted score across 5 factors (India VIX, FII/DII inflows, USD/INR velocity, Brent Crude, and repo rate). "
        "This score dynamically adjusts the composite Alpha threshold from 0.45 (during calm periods) "
        "to a tighter 0.60 (during volatile regimes), which automatically forces the MVO optimizer to drop weak signals "
        "and scale back portfolio risk exposure BEFORE losses accumulate.",
        body_style
    ))

    add_qa(
        "What are the major mathematical limitations of Markowitz Mean-Variance Optimization (MVO)?",
        "MVO is highly sensitive to input parameters. A minor change in expected returns or estimated covariance can "
        "cause the optimizer to output extreme, highly concentrated weights (e.g. allocating 100% of the capital "
        "to a single high-momentum sector). This is known as the 'estimation error maximizer.' "
        "To solve this, I implemented three critical constraints: a 20% hard cap on any single sector weight, a 40% "
        "cap on thematic groupings, and a minimum requirement of 5 active sectors. This guarantees strict diversification "
        "even when expected return forecasts are volatile."
    )

    add_qa(
        "How would you improve the portfolio optimization logic if you had an extra month?",
        "I would implement the Black-Litterman optimization model. Instead of relying solely on raw statistical expected returns "
        "(which are highly noisy), Black-Litterman blends market equilibrium returns with subjective views (the ML forecasts "
        "weighted by their confidence scores). This anchors the optimizer to the broader market, resulting in much more stable, "
        "highly diversified allocations and eliminating the extreme concentration risk of traditional Markowitz MVO."
    )

    # Build the document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Success: Professional study PDF generated at '{filename}'.")

if __name__ == "__main__":
    create_interview_pdf()
