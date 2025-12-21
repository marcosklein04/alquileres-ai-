import os
import sqlite3
import pymysql
from dotenv import load_dotenv
from datetime import date, datetime

load_dotenv()

DB_ENGINE = os.getenv("DB_ENGINE", "postgres").lower()
DB_PATH = os.getenv("DB_PATH", "contratos.db")


def get_db_connection():
    """
    Devuelve conexión según DB_ENGINE.
    - mysql: usa pymysql con DictCursor
    - sqlite: usa sqlite3 con row_factory=Row
    """
    if DB_ENGINE == "mysql":
        return pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "alquileres_ai"),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,  # commit manual (más control)
        )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def listar_contratos_bd():
    """
    Devuelve lista de dicts con fechas en ISO (YYYY-MM-DD o None).
    Tabla: contratos
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, inmobiliaria, inquilino, propietario,
               fecha_inicio, fecha_fin, decision_renovacion, dias_aviso
        FROM contratos
        ORDER BY fecha_fin ASC
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    items = []
    for r in rows:
        # sqlite Row o dict mysql
        fi = r["fecha_inicio"]
        ff = r["fecha_fin"]

        if isinstance(fi, date):
            fi = fi.isoformat()
        elif fi is not None:
            fi = str(fi)

        if isinstance(ff, date):
            ff = ff.isoformat()
        elif ff is not None:
            ff = str(ff)

        items.append({
            "id": r["id"],
            "inmobiliaria": r["inmobiliaria"],
            "inquilino": r["inquilino"],
            "propietario": r["propietario"],
            "fecha_inicio": fi,
            "fecha_fin": ff,
            "decision_renovacion": r.get("decision_renovacion") if isinstance(r, dict) else r["decision_renovacion"],
            "dias_aviso": r.get("dias_aviso") if isinstance(r, dict) else r["dias_aviso"],
        })

    return items


def listar_contratos_por_notificar_60d():
    """
    Trae contratos candidatos para aviso:
    - estado ACTIVO
    - notificado_60d = 0
    - fecha_fin no null
    - al menos un email (inquilino o propietario)
    - días restantes dentro del umbral (dias_aviso)
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, inmobiliaria, inquilino, propietario, fecha_inicio, fecha_fin,
               dias_aviso, decision_renovacion, email_inquilino, email_propietario, notificado_60d
        FROM contratos
        WHERE estado = 'ACTIVO'
          AND notificado_60d = 0
          AND fecha_fin IS NOT NULL
          AND (email_inquilino IS NOT NULL OR email_propietario IS NOT NULL)
        ORDER BY fecha_fin ASC
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    hoy = date.today()
    out = []

    for r in rows:
        fin = r["fecha_fin"]

        # fin puede venir como date (mysql) o string (sqlite)
        if isinstance(fin, date):
            fin_date = fin
        else:
            try:
                fin_date = datetime.strptime(str(fin), "%Y-%m-%d").date()
            except Exception:
                fin_date = None

        if not fin_date:
            continue

        dias = (fin_date - hoy).days
        umbral = r.get("dias_aviso", 60) if isinstance(r, dict) else r["dias_aviso"]
        umbral = int(umbral or 60)

        if 0 <= dias <= umbral:
            out.append({
                "id": r["id"],
                "inmobiliaria": r["inmobiliaria"],
                "inquilino": r["inquilino"],
                "propietario": r["propietario"],
                "fecha_inicio": str(r["fecha_inicio"]) if r["fecha_inicio"] else None,
                "fecha_fin": fin_date.isoformat(),
                "dias_aviso": umbral,
                "dias_restantes": dias,
                "decision_renovacion": r["decision_renovacion"],
                "email_inquilino": r.get("email_inquilino") if isinstance(r, dict) else r["email_inquilino"],
                "email_propietario": r.get("email_propietario") if isinstance(r, dict) else r["email_propietario"],
            })

    return out


def marcar_notificado_60d(contrato_id: int):
    conn = get_db_connection()
    cur = conn.cursor()

    if DB_ENGINE == "mysql":
        cur.execute(
            "UPDATE contratos SET notificado_60d=1, notificado_60d_at=NOW() WHERE id=%s",
            (contrato_id,)
        )
    else:
        cur.execute(
            "UPDATE contratos SET notificado_60d=1, notificado_60d_at=datetime('now') WHERE id=?",
            (contrato_id,)
        )

    conn.commit()
    cur.close()
    conn.close()