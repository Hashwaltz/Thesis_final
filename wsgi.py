# wsgi.py
from main_app import create_app
from main_app.extensions import db, migrate

app = create_app()

# This is what registers `flask db` commands
migrate.init_app(app, db)
