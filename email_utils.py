import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# 환경 변수에서 SMTP 정보 로드 (수정)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT   = 465
SMTP_USER   = os.getenv('SMTP_USER')
SMTP_PASS   = os.getenv('SMTP_PASS')

def send_email(to_email: str, subject: str, body: str) -> bool:
    """
    to_email: 수신자 이메일
    subject: 메일 제목
    body   : 메일 본문 (plain text)
    """
    # SMTP_USER나 SMTP_PASS가 설정되지 않았을 경우를 대비
    if not SMTP_USER or not SMTP_PASS:
        print("[Email Error] SMTP_USER 또는 SMTP_PASS 환경 변수가 설정되지 않았습니다.")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To']   = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', _charset="utf-8"))

        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"[Email Error] {e}")
        return False
