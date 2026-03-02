from datetime import datetime
from flask import flash


class ServiceRegistry:
    """
    Central registry for HR document services
    """

    services = []

    @classmethod
    def register(cls, name, description, icon, endpoint):
        cls.services.append({
            "name": name,
            "description": description,
            "icon": icon,
            "endpoint": endpoint
        })

    @classmethod
    def get_services(cls):
        return cls.services


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



# ----------------- CONFIG -----------------
ALLOWED_EXTENSIONS = {'xls', 'xlsx'}
UPLOAD_FOLDER = "uploads/attendance"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
