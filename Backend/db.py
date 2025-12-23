import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()
DB_PATH = os.getenv("DB_PATH", "contratos.db")

def get_connection():
    if DB_ENGINE in ("postgres", "postgresql"):
        import psycopg2
        import psycopg2.extras
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("Falta DATABASE_URL para Postgres")
        return psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)

    if DB_ENGINE == "mysql":
        import pymysql
        return pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "alquileres_ai"),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    # sqlite por default
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_db_connection():
    return get_connection()