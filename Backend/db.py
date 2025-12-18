import os
import sqlite3
import pymysql
from dotenv import load_dotenv

import pymysql

def get_db_connection():
    return pymysql.connect(
        host="localhost",
        user="alquileres_user",
        password="alquileres123",
        database="alquileres_ai",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

load_dotenv()

DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()

def get_connection():
    if DB_ENGINE == "mysql":
        return pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "alquileres_ai"),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
    else:
        conn = sqlite3.connect("contratos.db")
        conn.row_factory = sqlite3.Row
        return conn

def get_db_connection():
    return get_connection()


DB_PATH = "contratos.db"

def listar_contratos_bd():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # AJUSTÁ el nombre de la tabla si es distinto
    cur.execute("""
        SELECT
            id,
            inmobiliaria,
            inquilino,
            propietario,
            fecha_inicio,
            fecha_fin
        FROM contracts
        ORDER BY id DESC
    """)

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

from datetime import date

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

    items = []
    for r in rows:
        fi = r["fecha_inicio"]
        ff = r["fecha_fin"]

        # normalizar a string ISO
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