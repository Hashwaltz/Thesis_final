from flask import render_template, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, case, and_
from sqlalchemy.exc import SQLAlchemyError
  
from main_app.models.hr_models import Leave, Employee, LeaveType, Department
from main_app.helpers.decorators import leave_officer_required
from main_app.extensions import db
from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp


# =========================================================
# LEAVE OFFICER DASHBOARD (Robust Version)
# =========================================================
@leave_officer_bp.route("/leave-dashboard")
@login_required
@leave_officer_required
def leave_dashboard():
    try:
        today = datetime.now().date()
        current_month_year = datetime.now().strftime("%B %Y")

        # --- LEAVE COUNTS ---
        pending_leaves = Leave.query.filter_by(status="Pending").count()
        approved_leaves = Leave.query.filter_by(status="Approved").count()
        rejected_leaves = Leave.query.filter_by(status="Rejected").count()
        total_leaves = pending_leaves + approved_leaves + rejected_leaves

        # --- ACTIVE EMPLOYEES ---
        total_active_employees = Employee.query.filter_by(status="Active").count() or 0

        # --- REMINDERS ---
        reminders = []
        if pending_leaves > 0:
            reminders.append(f"You have {pending_leaves} pending leave requests to review.")

        # --- 📊 MONTHLY GRAPH DATA (Last 6 Months) ---
        six_months_ago = today - timedelta(days=180)
        
        # Database-agnostic date grouping using strftime (works in SQLite/MySQL/PostgreSQL)
        monthly_data = db.session.query(
            func.strftime('%Y', Leave.created_at).label('year'),
            func.strftime('%m', Leave.created_at).label('month'),
            func.count(Leave.id).label('total'),
            # Use CASE statements for status counting (database-agnostic)
            func.sum(case((Leave.status == 'Pending', 1), else_=0)).label('pending'),
            func.sum(case((Leave.status == 'Approved', 1), else_=0)).label('approved'),
            func.sum(case((Leave.status == 'Rejected', 1), else_=0)).label('rejected')
        ).filter(
            Leave.created_at >= six_months_ago,
            Leave.created_at != None
        ).group_by(
            func.strftime('%Y', Leave.created_at),
            func.strftime('%m', Leave.created_at)
        ).order_by(
            func.strftime('%Y', Leave.created_at),
            func.strftime('%m', Leave.created_at)
        ).all()
        
        monthly_labels = []
        pending_data = []
        approved_data = []
        rejected_data = []
        
        for row in monthly_data:
            try:
                year = int(row.year)
                month = int(row.month)
                month_name = datetime(year, month, 1).strftime("%b %Y")
                monthly_labels.append(month_name)
                pending_data.append(row.pending or 0)
                approved_data.append(row.approved or 0)
                rejected_data.append(row.rejected or 0)
            except (ValueError, TypeError):
                continue  # Skip malformed rows

        # --- 🏆 TOP 3 REQUESTED LEAVE TYPES ---
        top_leave_types = db.session.query(
            LeaveType.name,
            func.count(Leave.id).label('count')
        ).join(Leave, Leave.leave_type_id == LeaveType.id)\
         .filter(Leave.id != None)\
         .group_by(LeaveType.name)\
         .order_by(func.count(Leave.id).desc())\
         .limit(3).all()
        
        top_leave_list = []
        for i, (name, count) in enumerate(top_leave_types, 1):
            try:
                percentage = round((count / total_leaves) * 100, 1) if total_leaves > 0 and count else 0
                top_leave_list.append({
                    "rank": i,
                    "name": name or "Unknown",
                    "count": count or 0,
                    "percentage": percentage
                })
            except (TypeError, ZeroDivisionError):
                continue
        
        # Fill empty slots if less than 3 types exist
        while len(top_leave_list) < 3:
            top_leave_list.append({
                "rank": len(top_leave_list)+1, 
                "name": "N/A", 
                "count": 0, 
                "percentage": 0
            })

        # --- 📈 ADDITIONAL METRICS ---
        
        # Approval rate (safe division)
        approval_rate = round((approved_leaves / total_leaves) * 100, 1) if total_leaves > 0 else 0.0
        
        # Month-over-month change
        current_month = datetime.now().replace(day=1)
        last_month = (current_month - timedelta(days=1)).replace(day=1)
        
        try:
            current_month_count = Leave.query.filter(
                func.strftime('%Y', Leave.created_at) == str(current_month.year),
                func.strftime('%m', Leave.created_at) == str(current_month.month).zfill(2)
            ).count()
            
            last_month_count = Leave.query.filter(
                func.strftime('%Y', Leave.created_at) == str(last_month.year),
                func.strftime('%m', Leave.created_at) == str(last_month.month).zfill(2)
            ).count()
        except:
            current_month_count = last_month_count = 0
        
        mom_change = 0.0
        mom_trend = "stable"
        if last_month_count > 0:
            mom_change = round(((current_month_count - last_month_count) / last_month_count) * 100, 1)
            mom_trend = "up" if mom_change > 0 else "down" if mom_change < 0 else "stable"
        
        # Department breakdown (safe joins)
        try:
            dept_breakdown = db.session.query(
                Department.name,
                func.count(Leave.id).label('count')
            ).join(Employee, Employee.department_id == Department.id)\
             .join(Leave, Leave.employee_id == Employee.id)\
             .filter(Department.name != None)\
             .group_by(Department.name)\
             .order_by(func.count(Leave.id).desc())\
             .limit(3).all()
            
            dept_list = [{"name": name or "Unknown", "count": count or 0} for name, count in dept_breakdown]
        except SQLAlchemyError:
            dept_list = []
        
        # Recent pending requests (explicit relationship)
        try:
            recent_pending = Leave.query.filter_by(status="Pending")\
                .order_by(Leave.created_at.desc())\
                .limit(5).all()
            
            recent_pending_list = []
            for leave in recent_pending:
                try:
                    emp_name = leave.employee.get_full_name() if leave.employee else "Unknown Employee"
                    leave_type_name = leave.leave_type.name if leave.leave_type else "Unknown Type"
                    recent_pending_list.append({
                        "employee": emp_name,
                        "type": leave_type_name,
                        "dates": f"{leave.start_date} to {leave.end_date}" if leave.start_date and leave.end_date else "N/A",
                        "created": leave.created_at.strftime("%b %d") if leave.created_at else "N/A"
                    })
                except AttributeError:
                    continue
        except SQLAlchemyError:
            recent_pending_list = []

        return render_template(
            "hr/leave_officer/dashboard.html",
            pending_leaves=pending_leaves,
            approved_leaves=approved_leaves,
            rejected_leaves=rejected_leaves,
            total_users=total_active_employees,
            reminders=reminders,
            current_month_year=current_month_year,
            
            # Graph data
            monthly_leave_labels=monthly_labels,
            pending_data=pending_data,
            approved_data=approved_data,
            rejected_data=rejected_data,
            
            # Top 3 leave types
            top_leave_types=top_leave_list,
            
            # Additional metrics
            approval_rate=approval_rate,
            mom_change=mom_change,
            mom_trend=mom_trend,
            dept_breakdown=dept_list,
            recent_pending=recent_pending_list
        )
        
    except SQLAlchemyError as e:
        # Log error and show friendly message
        db.session.rollback()
        flash("Unable to load dashboard data. Please try again later.", "error")
        return render_template(
            "hr/leave_officer/dashboard.html",
            pending_leaves=0,
            approved_leaves=0,
            rejected_leaves=0,
            total_users=0,
            reminders=[],
            current_month_year=datetime.now().strftime("%B %Y"),
            monthly_leave_labels=[],
            pending_data=[],
            approved_data=[],
            rejected_data=[],
            top_leave_types=[{"rank": i, "name": "N/A", "count": 0, "percentage": 0} for i in range(1, 4)],
            approval_rate=0,
            mom_change=0,
            mom_trend="stable",
            dept_breakdown=[],
            recent_pending=[]
        )
    except Exception as e:
        # Catch-all for unexpected errors
        db.session.rollback()
        flash("An unexpected error occurred. Please contact support.", "error")
        return render_template(
            "hr/leave_officer/dashboard.html",
            pending_leaves=0,
            approved_leaves=0,
            rejected_leaves=0,
            total_users=0,
            reminders=[],
            current_month_year=datetime.now().strftime("%B %Y"),
            monthly_leave_labels=[],
            pending_data=[],
            approved_data=[],
            rejected_data=[],
            top_leave_types=[{"rank": i, "name": "N/A", "count": 0, "percentage": 0} for i in range(1, 4)],
            approval_rate=0,
            mom_change=0,
            mom_trend="stable",
            dept_breakdown=[],
            recent_pending=[]
        )