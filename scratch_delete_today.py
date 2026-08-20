import sqlite3
from datetime import date

db_path = "data/marketos.db"
target_date = "2026-08-07"

print(f"Connecting to {db_path}...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

tables_with_date = {
    "daily_prices": "date",
    "macro_data": "date",
    "sector_performance": "date",
    "daily_insights": "date",
    "forward_forecasts": "generated_date",
}

for table, col in tables_with_date.items():
    try:
        # Check row count first
        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (target_date,))
        count = cursor.fetchone()[0]
        print(f"Table '{table}': found {count} rows on {target_date}")
        
        if count > 0:
            cursor.execute(f"DELETE FROM {table} WHERE {col} = ?", (target_date,))
            print(f"  Deleted {count} rows from {table}")
    except Exception as e:
        print(f"  Error processing {table}: {e}")

conn.commit()
conn.close()
print("Finished cleaning today's data.")
