import sys
import io
import os
from dotenv import load_dotenv
from datetime import datetime
import logging

# Windows 터미널/PowerShell에서 한글 로그가 깨지지 않도록 UTF-8로 래핑
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# .env 파일에서 환경 변수 로드
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_

from models import db, User, Conversation
from email_utils import send_email
from flask_login import (
    LoginManager, login_user, logout_user, login_required,
    current_user
)


# [수정된 부분] Flask 앱을 생성할 때, instance 폴더를 인식하도록 인자를 추가합니다.
app = Flask(__name__, instance_relative_config=True)

# Gunicorn 로거와 연결하여 Render 로그에 잘 표시되도록 설정
if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

app.config['SECRET_KEY']                     = os.getenv('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI']        = 'sqlite:///vitamin_chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_AS_ASCII']                  = False

db.init_app(app)

# [수정된 부분] 앱 컨텍스트 안에서 데이터베이스를 생성하기 전에,
# 데이터베이스 파일이 저장될 'instance' 폴더가 없을 경우를 대비해 생성해줍니다.
with app.app_context():
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass # 이미 폴더가 있는 경우엔 아무것도 하지 않음
    db.create_all()

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ... (이후의 모든 코드는 이전과 동일합니다) ...
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        if User.query.filter_by(email=email).first():
            flash("이미 사용 중인 이메일입니다.", "warning")
            return redirect(url_for('register'))
        hashed_pw = generate_password_hash(password)
        db.session.add(User(email=email, password=hashed_pw))
        db.session.commit()
        flash("✅ 회원가입 완료. 로그인해 주세요.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, password):
            flash("⚠️ 이메일 또는 비밀번호가 올바르지 않습니다.", "danger")
            return redirect(url_for('login'))
        login_user(user)
        return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("로그아웃되었습니다.", "info")
    return redirect(url_for('login'))

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    if request.method == 'POST':
        data = request.get_json()
        user_msg = data.get('message', '').strip()
        age = data.get('age')
        gender = data.get('gender')

        if not user_msg or age is None or not gender:
            return Response("증상, 나이, 성별을 모두 입력해주세요.", status=400)

        if current_user.age != age or current_user.gender != gender:
            current_user.age = age
            current_user.gender = gender
            db.session.commit()

        try:
            conv = Conversation(
                user_id=current_user.id, timestamp=datetime.utcnow(),
                user_message=user_msg, bot_reply="", symptom_text=user_msg,
                model_used="gpt-3.5-turbo", age=age, gender=gender
            )
            db.session.add(conv)
            db.session.commit()
            conv_id = conv.id

            stream = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "당신은 영양 전문가 겸 소비자 가이드 작성자입니다. ..."},
                    {"role": "user", "content": f"{age}세 {gender} 사용자가 ..."}
                ],
                stream=True
            )

            def generate_stream(response_stream, conversation_id):
                full_reply = ""
                with app.app_context():
                    try:
                        for chunk in response_stream:
                            content = chunk.choices[0].delta.content or ""
                            full_reply += content
                            yield content
                        
                        db_conv = db.session.get(Conversation, conversation_id)
                        if db_conv:
                            db_conv.bot_reply = full_reply
                            db.session.commit()
                        
                        yield f"__CONV_ID__{conversation_id}"

                    except Exception as e:
                        db.session.rollback()
                        error_message = f"스트림 처리 중 오류: {str(e)}"
                        app.logger.error(error_message)
                        yield error_message

            return Response(generate_stream(stream, conv_id), mimetype='text/plain')

        except Exception as e:
            db.session.rollback()
            error_message = f"API 호출 오류: {str(e)}"
            app.logger.error(error_message)
            return Response(error_message, status=500)

    # GET 요청 처리
    logs = Conversation.query.filter_by(user_id=current_user.id).order_by(Conversation.timestamp).all()
    return render_template('chat.html', logs=logs, user_age=current_user.age, user_gender=current_user.gender)

@app.route('/send_email', methods=['POST'])
@login_required
def route_send_email():
    data = request.get_json()
    cid = data.get('conv_id')
    conv = db.session.get(Conversation, cid)
    if not conv or conv.user_id != current_user.id:
        return jsonify(success=False, error="해당 대화 내역을 찾을 수 없습니다."), 404
    subject = f"[비타민 추천 결과] {conv.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
    success = send_email(current_user.email, subject, conv.bot_reply)
    return jsonify(success=success)

@app.route('/save_note', methods=['POST'])
@login_required
def route_save_note():
    data = request.get_json()
    cid = data.get('conv_id')
    conv = db.session.get(Conversation, cid)
    if not conv or conv.user_id != current_user.id:
        return jsonify(success=False, error="해당 대화 내역을 찾을 수 없습니다."), 404
    conv.saved = True
    db.session.commit()
    return jsonify(success=True)

@app.route('/history')
@login_required
def history():
    query = Conversation.query.filter_by(user_id=current_user.id)
    search_term = request.args.get('q', '').strip()
    if search_term:
        query = query.filter(
            or_(
                Conversation.user_message.ilike(f'%{search_term}%'),
                Conversation.bot_reply.ilike(f'%{search_term}%')
            )
        )
    logs = query.order_by(Conversation.timestamp.desc()).all()
    return render_template('history.html', logs=logs)

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))


@app.errorhandler(500)
def handle_internal_server_error(e):
    app.logger.error(f"Internal Server Error: {e}", exc_info=True)
    return jsonify(error="서버 내부에서 오류가 발생했습니다. 잠시 후 다시 시도해주세요."), 500
