def register_blueprint(app):

    from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp

    app.register_blueprint(payroll_admin_bp, url_prefix="/payroll/admin")