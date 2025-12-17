from db import get_db_connection

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS contratos (
            id INT NOT NULL AUTO_INCREMENT,
            inmobiliaria VARCHAR(255) NULL,
            inquilino VARCHAR(255) NULL,
            propietario VARCHAR(255) NULL,
            fecha_inicio DATE NULL,
            fecha_fin DATE NULL,
            dias_aviso INT NOT NULL DEFAULT 60,
            estado VARCHAR(30) NOT NULL DEFAULT 'ACTIVO',
            decision_renovacion VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
            creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)

    # Si en tu conexión usás autocommit=True, esto no es necesario,
    # pero dejarlo no hace daño en la mayoría de casos.
    try:
        conn.commit()
    except Exception:
        pass

    cur.close()
    conn.close()
    print("Base de datos MySQL inicializada correctamente.")

if __name__ == "__main__":
    init_db()