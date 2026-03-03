# main_app/__init__.py
from flask import Flask, redirect, url_for, render_template
from main_app.extensions import db, login_manager, migrate, mail

# Import shared models
from main_app.models.user import User

# Import all HR and Payroll models so Flask-Migrate can detect them
from main_app.models.hr_models import *
from main_app.models.payroll_models import *

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
    login_manager.login_view = "hr_auth_bp.login"
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

    from main_app.blueprints.hr_system.routes.leave_officer import leave_officer_bp

    app.register_blueprint(leave_officer_bp, url_prefix="/hr/leave_officer")


    # -----------------------------
    # Register Payroll Blueprints
    # -----------------------------

    from main_app.blueprints import register_blueprint
    register_blueprint(app)
   
    from main_app.blueprints.payroll_system.routes.payroll_staff_routes import payroll_staff_bp
    from main_app.blueprints.payroll_system.routes.employee_routes import payroll_employee_bp
    from main_app.blueprints.payroll_system.routes.auth_routes import payroll_auth_bp



    app.register_blueprint(payroll_staff_bp, url_prefix='/payroll/staff')
    app.register_blueprint(payroll_auth_bp)
    app.register_blueprint(payroll_employee_bp, url_prefix='/payroll/employee')


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
