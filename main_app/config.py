import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'

    # SQLite database path inside main_app/instance
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), 'instance')),
        'hr_and_payroll.db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # HR System Configuration
    HR_SYSTEM_URL = 'http://localhost:5000'

    # Payroll System Configuration
    PAYROLL_SYSTEM_URL = 'http://localhost:5000'

    # API Configuration
    API_TIMEOUT = 30

    # Mail Configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    MAIL_USE_TLS = False
    MAIL_USERNAME = 'natanielashleyrodelas@gmail.com'
    MAIL_PASSWORD = 'jwrlqbebbzvvnzzs'
