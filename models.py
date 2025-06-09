# models.py (수정 완료)

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password      = db.Column(db.String(200), nullable=False)
    registered_on = db.Column(db.DateTime, default=datetime.utcnow)

    # age와 gender를 User 모델로 이동
    age           = db.Column(db.Integer, nullable=True)
    gender        = db.Column(db.String(10), nullable=True)


class Conversation(db.Model):
    __tablename__ = 'conversations'
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp      = db.Column(db.DateTime, default=datetime.utcnow)
    user_message   = db.Column(db.Text, nullable=False)
    bot_reply      = db.Column(db.Text, nullable=False)
    symptom_text   = db.Column(db.String(200), nullable=False)
    model_used     = db.Column(db.String(50), default='gpt-3.5-turbo')

    # Conversation 모델의 age, gender는 User 모델의 정보와 중복되므로 삭제합니다.
    # 대신 사용자가 질문 시점의 나이와 성별을 기록하고 싶다면 필드 이름 변경을 고려할 수 있습니다.
    # 예: question_age, question_gender
    # 지금은 User 모델의 정보를 사용하므로 여기서는 제거합니다.
    age            = db.Column(db.Integer, nullable=True) # 질문 당시의 나이
    gender         = db.Column(db.String(10), nullable=True) # 질문 당시의 성별
    saved          = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref=db.backref('conversations', lazy=True))


