# init_db.py

from app import app, db

print("Starting database initialization...")
with app.app_context():
    db.create_all()
print("Database initialized successfully.")