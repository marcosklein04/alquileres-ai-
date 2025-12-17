from openai import OpenAI
from dotenv import load_dotenv
import os
import json

# Cargar variables de entorno desde .env
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extraer_datos_contrato(texto_contrato: str) -> dict:
    """
    Envía el contrato a GPT y le pide que devuelva SOLO un JSON con:
    - inmobiliaria
    - inquilino
    - propietario
    - fecha_inicio (YYYY-MM-DD)
    - fecha_fin (YYYY-MM-DD)
    """

    prompt = f"""
    Quiero que analices el siguiente contrato de alquiler en Argentina
    y devuelvas EXCLUSIVAMENTE un JSON válido (sin texto adicional) con
    esta estructura exacta:

    {{
      "inmobiliaria": string o null,
      "inquilino": string o null,
      "propietario": string o null,
      "fecha_inicio": string o null,   // en formato YYYY-MM-DD
      "fecha_fin": string o null       // en formato YYYY-MM-DD
    }}

    Si algún dato no se puede identificar con claridad, usa null.

    Contrato:
    \"\"\"{texto_contrato}\"\"\"
    """

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",  # podés cambiar a otro modelo si querés
        messages=[
            {"role": "system", "content": "Eres un asistente experto en contratos inmobiliarios argentinos. Siempre respondes con JSON válido cuando se te solicita."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
    )

    contenido = completion.choices[0].message.content.strip()

    # Intentamos parsear el JSON devuelto
    try:
        data = json.loads(contenido)
    except json.JSONDecodeError:
        # Si por alguna razón no devuelve JSON perfecto, devolvemos campos vacíos
        data = {
            "inmobiliaria": None,
            "inquilino": None,
            "propietario": None,
            "fecha_inicio": None,
            "fecha_fin": None,
        }

    return data