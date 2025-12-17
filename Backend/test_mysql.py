from db import get_connection

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT 1 AS ok;")
print(cur.fetchone())
conn.close()