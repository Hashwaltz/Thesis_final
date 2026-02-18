# run.py
from main_app import create_app
from main_app.extensions import db, migrate

app = create_app()

# Initialize Flask-Migrate
migrate.init_app(app, db)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
