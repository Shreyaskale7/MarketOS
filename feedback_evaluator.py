# feedback_evaluator.py
# MarketOS — Daily Prediction Accuracy Tracker
# Runs every morning, checks if yesterday's directional forecast was correct

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from database import get_session, ForwardForecast, DailyPrice, PredictionAccuracy

def evaluate_forecast_accuracy():
    """
    For each forecast whose target_date has passed,
    compare predicted direction vs actual return.
    Updates PredictionAccuracy table.
    """
    today = datetime.today().date()
    
    session = get_session()
    try:
        # Find forecasts that matured (target_date <= today) and not yet evaluated
        from sqlalchemy import and_
        evaluated_ids = [r.forecast_id for r in session.query(PredictionAccuracy).all()]
        
        matured = session.query(ForwardForecast).filter(
            ForwardForecast.target_date <= today
        ).all()
        
        new_evals = []
        for forecast in matured:
            if forecast.id in evaluated_ids:
                continue  # already evaluated
            
            # Get actual return for this sector over the forecast period
            try:
                from sqlalchemy import func
                prices = session.query(DailyPrice).filter(
                    DailyPrice.subsector == forecast.subsector,
                    DailyPrice.date >= forecast.generated_date,
                    DailyPrice.date <= today
                ).all()
                
                if len(prices) < 5:
                    continue
                
                # Compute actual cumulative return
                price_df = pd.DataFrame([{
                    'date': p.date,
                    'daily_return': p.daily_return or 0,
                    'nifty_weight': p.nifty_weight or 0.001
                } for p in prices])
                
                daily_avg = price_df.groupby('date')['daily_return'].mean()
                actual_cumulative = ((1 + daily_avg).prod() - 1) * 100
                
                predicted_return  = forecast.base_case_return or 0
                direction_correct = np.sign(predicted_return) == np.sign(actual_cumulative)
                error_pct         = abs(predicted_return - actual_cumulative)
                
                new_evals.append({
                    'forecast_id':      forecast.id,
                    'sector':           forecast.sector,
                    'horizon':          forecast.forecast_horizon,
                    'predicted_return': round(predicted_return, 3),
                    'actual_return':    round(actual_cumulative, 3),
                    'direction_correct': direction_correct,
                    'error_pct':        round(error_pct, 3),
                    'evaluated_date':   today,
                })
            except Exception as e:
                continue
        
        if new_evals:
            session.bulk_insert_mappings(PredictionAccuracy, new_evals)
            session.commit()
            print(f"Evaluated {len(new_evals)} matured forecasts")
        else:
            print("No new forecasts to evaluate today")
        
        return new_evals
    
    except Exception as e:
        session.rollback()
        print(f"Evaluation error: {e}")
        return []
    finally:
        session.close()


def get_accuracy_summary():
    """Returns accuracy stats by sector and horizon"""
    session = get_session()
    try:
        records = session.query(PredictionAccuracy).all()
        if not records:
            return {"message": "No evaluated forecasts yet. Predictions need time to mature."}
        
        df = pd.DataFrame([{
            'sector':            r.sector,
            'horizon':           r.horizon,
            'direction_correct': r.direction_correct,
            'error_pct':         r.error_pct,
        } for r in records])
        
        summary = df.groupby(['sector', 'horizon']).agg(
            total=('direction_correct', 'count'),
            direction_accuracy=('direction_correct', 'mean'),
            avg_error=('error_pct', 'mean')
        ).round(3)
        
        print("\n=== FORECAST ACCURACY SUMMARY ===")
        print(summary.to_string())
        
        overall_dir_acc = df['direction_correct'].mean()
        print(f"\nOverall directional accuracy: {overall_dir_acc*100:.1f}%")
        
        return summary.to_dict()
    
    finally:
        session.close()


if __name__ == "__main__":
    print("Running forecast accuracy evaluation...")
    evaluate_forecast_accuracy()
    get_accuracy_summary()
