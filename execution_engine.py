# execution_engine.py
# MarketOS — Broker Execution Sandbox
# Maps AI-generated sector weights to real-world tradable proxy ETFs
# and generates standard limit/market order payloads for broker APIs (Zerodha/Upstox).

import json
from datetime import datetime

# Proxy ETF mapping (Sector -> NSE Ticker)
ETF_MAP = {
    "Banking & Financial Services": "BANKBEES.NS",
    "IT & Tech": "ITBEES.NS",
    "FMCG & Consumption": "CONSUMBEES.NS",
    "Healthcare & Pharma": "PHARMABEES.NS",
    "Infrastructure & Real Estate": "INFRA.NS",
    "Automobiles": "AUTOBEES.NS",
    "Energy & Utilities": "CPSEETF.NS",
}
DEFAULT_ETF = "NIFTYBEES.NS" # Fallback for unmapped sectors

class PaperBroker:
    def __init__(self, user_id: int, initial_capital: float = 100000.0):
        self.user_id = user_id
        self.capital = initial_capital
        
    def generate_orders(self, portfolio_weights: list, current_prices: dict = None) -> list:
        """
        Translates percentage weights into actionable share quantities and limit orders.
        """
        orders = []
        if not current_prices:
            current_prices = {} # Mock prices if not provided
            
        for pos in portfolio_weights:
            sector = pos.get("sector")
            weight = pos.get("adjusted_weight", 0.0)
            
            if weight <= 0.01:
                continue # Ignore tiny allocations
                
            etf_ticker = ETF_MAP.get(sector, DEFAULT_ETF)
            allocated_capital = self.capital * weight
            
            # Mock price: in reality, this would fetch from a live feed
            price = current_prices.get(etf_ticker, 500.0) 
            qty = int(allocated_capital // price)
            
            if qty > 0:
                orders.append({
                    "tradingsymbol": etf_ticker,
                    "exchange": "NSE",
                    "transaction_type": "BUY",
                    "order_type": "LIMIT",
                    "quantity": qty,
                    "price": round(price, 2),
                    "product": "CNC",
                    "validity": "DAY",
                    "tag": f"MarketOS_Rebalance_{datetime.utcnow().strftime('%Y%m%d')}"
                })
                
        return orders

    def execute_paper_trades(self, orders: list) -> dict:
        """
        Simulates broker execution (fills, slippage).
        """
        fills = []
        total_cost = 0.0
        
        for order in orders:
            # Simulate 0.05% slippage on the limit price
            fill_price = round(order["price"] * 1.0005, 2)
            cost = fill_price * order["quantity"]
            
            # Statutory Charges (STT, GST, Stamp Duty)
            stt = cost * 0.001
            stamp_duty = cost * 0.00015
            txn_charge = cost * 0.0000345
            gst = (txn_charge + (cost * 0.0001)) * 0.18 # Assuming some brokerage component
            
            total_charges = stt + stamp_duty + txn_charge + gst
            total_cost += (cost + total_charges)
            
            fills.append({
                "symbol": order["tradingsymbol"],
                "qty": order["quantity"],
                "fill_price": fill_price,
                "status": "COMPLETE",
                "charges": round(total_charges, 2)
            })
            
        return {
            "status": "SUCCESS",
            "executed_at": datetime.utcnow().isoformat(),
            "capital_deployed": round(total_cost, 2),
            "cash_remaining": round(self.capital - total_cost, 2),
            "fills": fills
        }

if __name__ == "__main__":
    # Test execution engine
    test_portfolio = [
        {"sector": "Banking & Financial Services", "adjusted_weight": 0.30},
        {"sector": "IT & Tech", "adjusted_weight": 0.20},
        {"sector": "Unknown", "adjusted_weight": 0.10}
    ]
    
    broker = PaperBroker(user_id=1, initial_capital=500000.0)
    orders = broker.generate_orders(test_portfolio)
    print("Generated Orders:")
    print(json.dumps(orders, indent=2))
    
    print("\nExecution Result:")
    result = broker.execute_paper_trades(orders)
    print(json.dumps(result, indent=2))
