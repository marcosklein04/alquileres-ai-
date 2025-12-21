import os
import json
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def _default_data():
    return {
        "inmobiliaria": None,
        "inquilino": None,
        "propietario": None,
        "fecha_inicio": None,
        "fecha_fin": None,
    }


def normalizar_fecha(valor):
    """
    Acepta string o None.
    Devuelve YYYY-MM-DD o None.
    """
    if not valor or not isinstance(valor, str):
        return None

    texto = valor.strip()
    if not texto:
        return None

    # dd/mm/yyyy o d/m/yyyy
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", texto)
    if m:
        d, mth, y = m.groups()
        return f"{y}-{int(mth):02d}-{int(d):02d}"

    # yyyy-mm-dd
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", texto)
    if m:
        return m.group(0)

    return None


def _extract_json(text):
    """
    Intenta extraer un JSON válido aunque venga envuelto en ```json ...```
    o con texto alrededor.
    """
    if not text:
        raise ValueError("Respuesta IA vacía")

    t = text.strip()

    # quita fences ```json ... ```
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)

    # si vino con texto extra, intentamos capturar el primer { ... } grande
    if not (t.startswith("{") and t.endswith("}")):
        m = re.search(r"(\{.*\})", t, flags=re.DOTALL)
        if m:
            t = m.group(1)

    return json.loads(t)


def extraer_datos_contrato(texto_contrato: str) -> dict:
    prompt = f"""
Analizá el siguiente contrato de alquiler en Argentina.

Respondé EXCLUSIVAMENTE con un JSON válido, sin texto adicional.

Formato EXACTO:
{{
  "inmobiliaria": string o null,
  "inquilino": string o null,
  "propietario": string o null,
  "fecha_inicio": string o null,
  "fecha_fin": string o null
}}

Reglas:
- NO mezclar inquilino con propietario.
- Fechas en formato YYYY-MM-DD (si vienen en otro formato, devolvé igualmente la fecha como string y yo la normalizo).
- Si no estás seguro, usar null.

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

        raw = (response.choices[0].message.content or "").strip()
        data = _extract_json(raw)

        # asegurar keys esperadas (evita que venga algo distinto)
        out = _default_data()
        out.update({k: data.get(k) for k in out.keys()})

        out["fecha_inicio"] = normalizar_fecha(out.get("fecha_inicio"))
        out["fecha_fin"] = normalizar_fecha(out.get("fecha_fin"))

        return {"ok": True, "model": MODEL, "raw": raw, "data": out}

    except Exception as e:
        print("❌ Error IA Groq:", repr(e))
        return {"ok": False, "model": MODEL, "raw": raw, "data": _default_data()}