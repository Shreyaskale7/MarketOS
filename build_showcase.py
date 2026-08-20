import os
import shutil

# Paths
source_dir = r"c:\MarketOS VIP"
showcase_dir = r"c:\MarketOS_Showcase"

# 1. Create the new directory outside of MarketOS VIP
if not os.path.exists(showcase_dir):
    os.makedirs(showcase_dir)
    print(f"Created Showcase Directory at {showcase_dir}")

# 2. Copy the safe frontend files
safe_files = [
    "marketos_dashboard.html",
    # Add any other css/js files here if they exist separately
]

for file in safe_files:
    src_path = os.path.join(source_dir, file)
    dst_path = os.path.join(showcase_dir, file)
    if os.path.exists(src_path):
        shutil.copy2(src_path, dst_path)
        print(f"Copied {file} to Showcase")

# 3. Create the Showcase README.md
readme_content = """# MarketOS: LLM-Driven Quantitative Finance Pipeline

> **🔒 Core Engine Closed-Source Notice**
> *Please note: This repository serves as a frontend and architectural showcase for MarketOS. The core analytical engines (Alpha Generation, Markowitz Optimization, LLM Sentiment processing, and Walk-Forward Backtesting) are currently maintained in a private repository as proprietary intellectual property for an upcoming commercial launch. I am happy to discuss the architecture, engineering challenges, and high-level ML implementation during interviews.*

## Overview
MarketOS is a fully autonomous financial intelligence pipeline designed to replicate institutional-grade quantitative research for 130 NSE-listed equities across 28 subsectors. It uses a 10-stage analytical engine to process live market data, evaluate macroeconomic regimes, quantify market sentiment using Generative AI, and execute mathematical portfolio optimization.

## Core Machine Learning & AI Implementations:
1. **Generative AI NLP Pipeline:** Integrated Groq's LLaMA-3.3-70B model to scrape and process real-time Google News RSS feeds. The LLM acts as an active feature-engineer, reading unstructured news and converting sector-level market psychology into a normalized mathematical sentiment score (-1.0 to +1.0) in milliseconds.
2. **Deterministic Mathematical Optimization:** Implemented Markowitz Mean-Variance Optimization (MVO) using `scipy.optimize`. The engine calculates the Efficient Frontier and outputs Sharpe-maximized portfolio weights with strict concentration caps, dynamically adjusting risk based on the Macro Regime.
3. **Walk-Forward Validation:** Engineered a rigorous walk-forward backtesting system (37 monthly periods) to validate the ML models and Alpha signals entirely out-of-sample. The engine accounts for transaction costs and slippage, eliminating look-ahead bias.

## Technical Stack:
*   **Languages & Frameworks:** Python, Flask, REST API
*   **Data Science & ML:** `scikit-learn`, `scipy`, `pandas`, `numpy`
*   **Generative AI:** Groq API (LLaMA-3.3-70B)
*   **Database & Infrastructure:** SQLite (SQLAlchemy ORM), `yfinance` API
*   **Frontend:** HTML/Vanilla CSS, JavaScript, Chart.js (Glassmorphism UI)

## Verified 5-Year Out-Of-Sample Results:
*   **Portfolio Return:** +14.20% annualised (vs +6.36% NIFTY benchmark)
*   **Information Ratio:** 1.100 (Institutional grade)
*   **Win Rate:** 70.3%
*   **Net Alpha:** +7.84% over benchmark

## Dashboard Architecture
*(See attached screenshots for the Live Dashboard, Markowitz Donut Charts, and AI Generated Briefings).*
"""

readme_path = os.path.join(showcase_dir, "README.md")
with open(readme_path, "w", encoding="utf-8") as f:
    f.write(readme_content)
print(f"Generated proprietary README.md at {readme_path}")

print("\nShowcase Setup Complete!")
print("You can now open GitHub Desktop, add the C:\\MarketOS_Showcase folder as a new repository, and push it publicly!")
