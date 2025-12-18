import os
import json
import re
from datetime import datetime
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "llama-3.3-70b-versatile"


def normalizar_fecha(texto):
    if not texto:
        return None

    # dd/mm/yyyy
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if m:
        d, mth, y = m.groups()
        return f"{y}-{mth}-{d}"

    # yyyy-mm-dd
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", texto)
    if m:
        return m.group(0)

    return None


def extraer_datos_contrato(texto_contrato: str) -> dict:
    prompt = f"""
Analizá el siguiente contrato de alquiler en Argentina.

Respondé EXCLUSIVAMENTE con un JSON válido,
sin texto adicional, sin explicaciones.

Formato EXACTO:
{{
  "inmobiliaria": string o null,
  "inquilino": string o null,
  "propietario": string o null,
  "fecha_inicio": string o null,
  "fecha_fin": string o null
}}

Reglas:
- NO mezclar inquilino con propietario
- Fechas en formato YYYY-MM-DD
- Si no estás seguro, usar null

Contrato:
\"\"\"{texto_contrato}\"\"\"
"""

    raw = None
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Sos un extractor de datos legales. Respondés solo JSON válido."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )

        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)

        data["fecha_inicio"] = normalizar_fecha(str(data.get("fecha_inicio")))
        data["fecha_fin"] = normalizar_fecha(str(data.get("fecha_fin")))

        return {"ok": True, "model": MODEL, "raw": raw, "data": data}

    except Exception as e:
        print("❌ Error IA Groq:", e)
        return {
            "ok": False,
            "model": MODEL,
            "raw": raw,
            "data": {
                "inmobiliaria": None,
                "inquilino": None,
                "propietario": None,
                "fecha_inicio": None,
                "fecha_fin": None,
            }
        }

    # Normalización final (doble seguridad)
    data["fecha_inicio"] = normalizar_fecha(str(data.get("fecha_inicio")))
    data["fecha_fin"] = normalizar_fecha(str(data.get("fecha_fin")))

    return data