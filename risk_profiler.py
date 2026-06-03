# risk_profiler.py
# MarketOS — SEBI-Compliant Risk Profiling Module
from datetime import datetime
from database import get_session, UserRiskProfile

def calculate_risk_score(age: int, income: str, horizon: str, drawdown: str) -> dict:
    """
    Calculates a SEBI-aligned risk score based on standard parameters.
    Returns a dict with risk_score (1-100) and risk_label (Conservative, Moderate, Aggressive).
    """
    score = 0
    
    # 1. Age Factor (Younger = Higher risk capacity)
    if age < 30:
        score += 25
    elif age <= 45:
        score += 20
    elif age <= 60:
        score += 10
    else:
        score += 5

    # 2. Income Bracket (Higher income = Higher risk capacity)
    if income == "> 50L":
        score += 25
    elif income == "15L - 50L":
        score += 20
    elif income == "5L - 15L":
        score += 10
    else:
        score += 5

    # 3. Investment Horizon (Longer = Higher risk capacity)
    if horizon == "> 5Y":
        score += 25
    elif horizon == "3-5Y":
        score += 20
    elif horizon == "1-3Y":
        score += 10
    else:
        score += 0  # < 1Y is very low capacity

    # 4. Drawdown Tolerance (Behavioral risk tolerance)
    if drawdown == "High (>20%)":
        score += 25
    elif drawdown == "Medium (10-20%)":
        score += 15
    elif drawdown == "Low (<10%)":
        score += 5
    else:
        score += 0

    # Determine Label
    if score >= 75:
        label = "Aggressive"
    elif score >= 50:
        label = "Moderate"
    else:
        label = "Conservative"
        
    return {
        "risk_score": score,
        "risk_label": label
    }

def save_risk_profile(user_id: int, age: int, income: str, horizon: str, drawdown: str):
    """
    Calculates the risk score and saves it to the database for the given user.
    """
    result = calculate_risk_score(age, income, horizon, drawdown)
    
    session = get_session()
    # Check if existing
    profile = session.query(UserRiskProfile).filter_by(user_id=user_id).first()
    
    if profile:
        profile.age = age
        profile.income_bracket = income
        profile.investment_horizon = horizon
        profile.drawdown_tolerance = drawdown
        profile.risk_score = result["risk_score"]
        profile.risk_label = result["risk_label"]
        profile.assessed_at = datetime.utcnow()
    else:
        profile = UserRiskProfile(
            user_id=user_id,
            age=age,
            income_bracket=income,
            investment_horizon=horizon,
            drawdown_tolerance=drawdown,
            risk_score=result["risk_score"],
            risk_label=result["risk_label"]
        )
        session.add(profile)
        
    session.commit()
    session.close()
    
    return result
