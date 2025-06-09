import sys
import io
import os
from dotenv import load_dotenv
from datetime import datetime

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


app = Flask(__name__)
app.config['SECRET_KEY']                     = os.getenv('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI']        = 'sqlite:///vitamin_chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_AS_ASCII']                  = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

@login_manager.user_loader
def load_user(user_id):
    # SQLAlchemy 2.0 권장 방식
    return db.session.get(User, int(user_id))

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
                    {
                        "role": "system", 
                        "content": (
                            "당신은 사용자의 증상을 분석하여, 필요한 영양소를 먼저 제시하고 그 이유를 설명한 뒤, 구체적인 제품을 추천하는 '영양학 컨설턴트'입니다. "
                            "답변은 반드시 아래의 논리적 순서를 따라야 합니다. "
                            "어떠한 마크다운이나 특수 기호(예: #, *, - 등)도 절대 사용하지 말고, 오직 일반 텍스트와 자연스러운 줄바꿈만으로 답변을 구성해주세요."
                        )
                    },
                    {
                        "role": "user", 
                        "content": (
                            f"{age}세 {gender} 사용자가 \"{user_msg}\" 증상을 겪고 있습니다.\n\n"
                            "아래의 4단계 순서에 맞춰 답변을 생성해주세요:\n\n"
                            "1: 증상에 필요한 비타민/영양소 종류를 먼저 나열합니다.\n"
                            "2: 왜 그 영양소들이 필요한지 이유를 간략하게 설명합니다.\n"
                            "3: 위 영양소들이 포함된 제품들을 저함량, 중함량, 고함량으로 나누어 각각 2~3개씩 추천합니다.\n"
                            "4: 각 제품의 브랜드, 제품명, 주요 성분, 복용량/주기를 명확히 기재합니다.\n\n"
                            "--- 답변 예시 형식 ---\n"
                            "OO세 OOO님의 '{user_msg}' 증상에 따라, 다음과 같은 영양소 섭취가 도움이 될 수 있습니다.\n\n"
                            "추천 영양소: 비타민 A, 루테인, 지아잔틴\n\n"
                            "추천 이유: 비타민 A는 시력 유지에 필수적이며, 루테인과 지아잔틴은 눈의 피로를 줄여주고 황반을 보호하는 역할을 합니다.\n\n"
                            "제품 추천:\n\n"
                            "저함량 제품:\n"
                            "브랜드: [브랜드명]\n"
                            "제품명: [제품명]\n"
                            "주요 성분: [주요 성분]\n"
                            "복용량/주기: [복용량 및 주기 정보]\n\n"
                            "(이어서 중함량, 고함량 제품 추천...)"
                        )
                    }
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
                        print(error_message)
                        yield error_message

            return Response(generate_stream(stream, conv_id), mimetype='text/plain')

        except Exception as e:
            db.session.rollback()
            error_message = f"API 호출 오류: {str(e)}"
            print(error_message)
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
    print(f"Internal Server Error: {e}")
    return jsonify(error="서버 내부에서 오류가 발생했습니다. 잠시 후 다시 시도해주세요."), 500

