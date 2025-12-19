import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(to_email: str, subject: str, html: str, text: str | None = None):
    host = os.getenv("GMAIL_SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("GMAIL_SMTP_PORT", "587"))
    user = os.getenv("GMAIL_SMTP_USER")
    password = os.getenv("GMAIL_SMTP_PASS")
    from_name = os.getenv("MAIL_FROM_NAME", "Alquileres AI")

    if not user or not password:
        raise RuntimeError("Faltan credenciales SMTP: GMAIL_SMTP_USER / GMAIL_SMTP_PASS")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{user}>"
    msg["To"] = to_email

    if text:
        msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [to_email], msg.as_string())