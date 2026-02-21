# main_app/__init__.py
from flask import Flask, redirect, url_for, render_template
from main_app.extensions import db, login_manager, migrate, mail

# Import shared models
from main_app.models.user import User

# Import all HR and Payroll models so Flask-Migrate can detect them
import main_app.models.hr_models
import main_app.models.payroll_models

def create_app():
    # Use shared templates and static folders
    app = Flask(
        __name__,
        template_folder="main_app/templates",
        static_folder="static"
    )

    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # Load global config (for both HR and Payroll)
    from main_app.config import Config
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)

    # Login settings
    login_manager.login_view = "hr_auth.login"
    login_manager.login_message_category = "info"

    # -----------------------------
    # User loader (shared User model)
    # -----------------------------
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # -----------------------------
    # Register HR Blueprints
    # -----------------------------
    from main_app.blueprints.hr_system.routes.auth_routes import hr_auth_bp
    from main_app.blueprints.hr_system.routes.hr_admin_routes import hr_admin_bp
    from main_app.blueprints.hr_system.routes.hr_officer_routes import hr_officer_bp
    from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp
    from main_app.blueprints.hr_system.routes.dept_head_routes import dept_head_bp
    from main_app.blueprints.hr_system.routes.employee_routes import employee_bp
    from main_app.blueprints.hr_system.routes.api_routes import api_bp

    app.register_blueprint(hr_auth_bp, url_prefix='/hr/auth')
    app.register_blueprint(hr_admin_bp, url_prefix='/hr/admin')
    app.register_blueprint(hr_officer_bp, url_prefix="/hr/officer")
    app.register_blueprint(leave_officer_bp, url_prefix="/hr/leave_officer")
    app.register_blueprint(dept_head_bp, url_prefix="/hr/dept_head")
    app.register_blueprint(employee_bp, url_prefix="/hr/employee")
    app.register_blueprint(api_bp, url_prefix="/api/hr")

    # -----------------------------
    # Register Payroll Blueprints
    # -----------------------------
    from main_app.blueprints.payroll_system.routes.auth_routes import payroll_auth_bp
    from main_app.blueprints.payroll_system.routes.payroll_admin_routes import payroll_admin_bp
    from main_app.blueprints.payroll_system.routes.payroll_staff_routes import payroll_staff_bp
    from main_app.blueprints.payroll_system.routes.employee_routes import payroll_employee_bp
    from main_app.blueprints.payroll_system.routes.api_routes import payroll_api_bp

    app.register_blueprint(payroll_auth_bp, url_prefix='/payroll/auth')
    app.register_blueprint(payroll_admin_bp, url_prefix='/payroll/admin')
    app.register_blueprint(payroll_staff_bp, url_prefix='/payroll/staff')
    app.register_blueprint(payroll_employee_bp, url_prefix='/payroll/employee')
    app.register_blueprint(payroll_api_bp, url_prefix='/payroll/api')

    # -----------------------------
    # Root route
    # -----------------------------
    @app.route("/")
    def index():
        return render_template("main_app/index.html")
    
    @app.route("/about")
    def about():
        return render_template("main_app/about.html")
    
    @app.route("/features")
    def features():
        return render_template("main_app/features.html")

    return app
