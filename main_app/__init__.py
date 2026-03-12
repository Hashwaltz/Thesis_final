# main_app/__init__.py
from flask import Flask, redirect, url_for, render_template
from main_app.extensions import db, login_manager, migrate, mail

# Import shared models
from main_app.models.user import User
from main_app.models.hr_models import *
from main_app.models.payroll_models import *

def create_app():
    # Use shared templates and static folders
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )

    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['DEBUG'] = True  

    # Load global config (for both HR and Payroll)
    from main_app.config import Config
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)

    # Login settings
    login_manager.login_view = "index"
    login_manager.login_message_category = "info"

    # -----------------------------
    # User loader (shared User model)
    # -----------------------------
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    # -----------------------------
    # Register Payroll Blueprints
    # -----------------------------

    from main_app.blueprints import register_blueprint
    register_blueprint(app)

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
