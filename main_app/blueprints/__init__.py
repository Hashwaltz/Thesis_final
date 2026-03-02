def register_blueprint(app):

    # -----------------------------
    # Register HR Blueprints
    # -----------------------------
    from main_app.blueprints.hr_system.routes.hr_auth import hr_auth_bp
    from main_app.blueprints.hr_system.routes.admin import hr_admin_bp
    from main_app.blueprints.hr_system.routes.officer import hr_officer_bp
    

    
    #payroll blueprints
    from main_app.blueprints.payroll_system.routes.admin import payroll_admin_bp
    
    app.register_blueprint(hr_auth_bp)
    app.register_blueprint(hr_admin_bp)
    app.register_blueprint(hr_officer_bp, url_prefix="/hr/officer")
    app.register_blueprint(payroll_admin_bp, url_prefix="/payroll/admin")