from app import app, db

# 이 스크립트는 Render의 빌드 과정에서만 실행됩니다.
print("Starting database initialization...")
with app.app_context():
    db.create_all()
print("Database initialized successfully.")