from main_app.extensions import db
from main_app import create_app
from main_app.models.hr_models import Employee, JobHistory

app = create_app()


def generate_initial_job_history():
    with app.app_context():
        employees = Employee.query.all()

        job_history_objs = []

        for emp in employees:
            # 🔍 Check if INITIAL APPOINTMENT already exists
            existing = JobHistory.query.filter_by(
                employee_id=emp.id,
                effective_date=emp.date_hired
            ).first()

            if existing:
                print(f"⚠️ Skipping {emp.get_full_name()} (already has initial appointment)")
                continue

            # ✅ Create initial job history
            job_entry = JobHistory(
                employee_id=emp.id,
                effective_date=emp.date_hired,
                end_date=None,  # still active
                position_id=emp.position_id,
                department_id=emp.department_id,
                employment_type_id=emp.employment_type_id,
                salary=emp.salary,
                status=emp.status or "Active",
                remarks="Initial appointment"
            )

            job_history_objs.append(job_entry)

        # 🚀 Bulk insert
        if job_history_objs:
            db.session.bulk_save_objects(job_history_objs)
            db.session.commit()
            print(f"✅ {len(job_history_objs)} JobHistory records created!")
        else:
            print("ℹ️ No new job history records to insert.")


if __name__ == "__main__":
    generate_initial_job_history()