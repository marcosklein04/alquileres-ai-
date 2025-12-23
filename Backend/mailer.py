import os
import requests


def send_email(to: str, subject: str, body: str):
    provider = os.getenv("EMAIL_PROVIDER", "resend").lower()

    if provider != "resend":
        raise RuntimeError("EMAIL_PROVIDER no soportado. Usá EMAIL_PROVIDER=resend")

    api_key = os.getenv("RESEND_API_KEY")
    mail_from = os.getenv("MAIL_FROM", "onboarding@resend.dev")
    mail_from_name = os.getenv("MAIL_FROM_NAME", "Alquileres AI")

    if not api_key:
        raise RuntimeError("Falta RESEND_API_KEY en variables de entorno")

    # Resend acepta From en formato "Nombre <email>"
    from_header = f"{mail_from_name} <{mail_from}>" if mail_from_name else mail_from

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": from_header,
        "to": [to],
        "subject": subject,
        # Para mantenerlo simple: body texto plano
        "text": body,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)

    if resp.status_code >= 300:
        raise RuntimeError(f"Resend error {resp.status_code}: {resp.text}")