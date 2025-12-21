import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DB_ENGINE = os.getenv("DB_ENGINE", "").lower().strip()  # "postgres" | "mysql" | "sqlite"
DATABASE_URL = os.getenv("DATABASE_URL")  # Railway Postgres

def get_db_connection():
    """
    Prioridad:
    1) Si existe DATABASE_URL => Postgres (Railway)
    2) Si DB_ENGINE == mysql => MySQL
    3) Caso contrario => SQLite local
    """
    if DATABASE_URL:
        import psycopg2
        import psycopg2.extras
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

    if DB_ENGINE == "mysql":
        import pymysql
        return pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "alquileres_ai"),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    conn = sqlite3.connect("contratos.db")
    conn.row_factory = sqlite3.Row
    return conn


def listar_contratos_bd():
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

    # Normalizamos a dict/strings
    out = []
    for r in rows:
        rr = dict(r)
        fi = rr.get("fecha_inicio")
        ff = rr.get("fecha_fin")
        rr["fecha_inicio"] = fi.isoformat() if hasattr(fi, "isoformat") else (str(fi) if fi is not None else None)
        rr["fecha_fin"] = ff.isoformat() if hasattr(ff, "isoformat") else (str(ff) if ff is not None else None)
        out.append(rr)
    return out