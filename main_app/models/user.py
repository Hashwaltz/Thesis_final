from main_app.extensions import db, login_manager
from flask_login import UserMixin
from datetime import datetime

# ==========================
# USER MODEL
# ==========================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="employee")
    department_id = db.Column(
        db.Integer, db.ForeignKey('department.id', name='fk_user_department_id')
    )
    position = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Relationships
    managed_department = db.relationship(
        "Department",
        back_populates="head",
        uselist=False,
        foreign_keys="[Department.head_id]"
    )
    employee_profile = db.relationship(
        "Employee",
        back_populates="user",
        uselist=False
    )
    approved_leaves = db.relationship(
        "Leave",
        back_populates="approver",
        lazy=True,
        foreign_keys="[Leave.approved_by]"
    )

    # ✅ Add this relationship
    department = db.relationship(
        "Department",
        backref="users",
        foreign_keys=[department_id]
    )

    def __repr__(self):
        return f'<User {self.email}>'

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

        # ---------------------------
    # ROLE CHECK HELPERS
    # ---------------------------
    def is_admin(self):
        return self.role == "admin"

    def is_staff(self):
        return self.role == "staff"

    def is_employee(self):
        return self.role == "employee"

    def is_officer(self):
        return self.role == "officer"

    def is_department_head(self):
        return self.role == "dept_head"
