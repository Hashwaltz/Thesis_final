from flask_login import LoginManager
from main_app.models.user import User   # HR User model
from flask_login import UserMixin
from flask_login import UserMixin

class PayrollUser(UserMixin):
    """
    Lightweight proxy (NOT a SQLAlchemy model). 
    Only use this for in-memory user objects.
    Do NOT call PayrollUser.query - it's not a db.Model.
    """
    def __init__(self, id, email, first_name, last_name, role, active=True, department=None, position=None):
        self.id = id
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.role = role
        self.active = active
        self.department = department
        self.position = position

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def is_staff(self):
        """Return True if the user is a staff member (officer, dept_head, admin)."""
        return self.role.lower() in ["staff","officer", "dept_head", "admin"]

    def __repr__(self):
        return f"<PayrollUser {self.email}>"