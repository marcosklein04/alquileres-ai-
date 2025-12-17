import os
import sqlite3
import pymysql
from dotenv import load_dotenv

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