import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'govhrpay-thesis-system'

    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), 'instance')),
        'hr_and_payroll.db'
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ⭐ LAN Network Stability Settings
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_PERMANENT = True

    # HR System Configuration
    HR_SYSTEM_URL = 'http://192.168.137.15:5000'
    PAYROLL_SYSTEM_URL = 'http://192.168.137.15:5000'

    API_TIMEOUT = 30

    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    MAIL_USE_TLS = False
    MAIL_USERNAME = 'natanielashleyrodelas@gmail.com'
    MAIL_PASSWORD = 'jwrlqbebbzvvnzzs'