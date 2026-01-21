from datetime import datetime
from flask import flash
# --- Safely parse dates ---
def parse_date(date_str, field_name):
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        if not (1900 <= date.year <= 2100):
            raise ValueError(f"{field_name} year out of valid range.")
        return date
    
    except ValueError as e:
        flash(f"Invalid {field_name}: {e}", "danger")
    return None